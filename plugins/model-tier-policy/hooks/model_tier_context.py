#!/usr/bin/env python3
"""Re-injects the model tier policy into context on a schedule.

Wired to UserPromptSubmit (per turn), SessionStart (launch, resume, and post-compact restarts), and PostCompact. The
always-loaded rules file can drift far up the context window in a long session; this keeps the policy in recent context,
which is what makes forgetting structurally impossible.

Injected context is attached to the turn's user message and stays in the transcript, so a full reminder on every turn
accumulates — in a premium-tier session it spends exactly the budget it exists to protect. So the full text lands on
turn 1 and every `reminder_interval` turns after (default 10), and a one-line marker carries the turns in between.
SessionStart and PostCompact always re-anchor with the full text.
"""

import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from model_tier_guard import load_config, live_model, orchestrator_active, project_dir
except Exception:  # pragma: no cover - guard missing means policy is not installed
    sys.exit(0)

ANCHOR_EVENTS = ("SessionStart", "PostCompact", "SessionResume")
# How close together two firings of the same event must be to count as one event handled by two installed copies.
DEDUPE_WINDOW_SECONDS = 10

PREMIUM = """[model tier policy — active tier: {model} (premium)]
You plan; you do not implement. Think, decide, review, delegate, and talk to the user.
- Write the plan to `.claude/plans/<slug>.plan.md`, then hand executors the path — never paste file contents into a brief.
- Delegate every procedural step: Agent(subagent_type="{executor}", model="opus", prompt=...). Use "{runner}" (Sonnet)
  for bulk mechanical work and "{scout}" (Opus, read-only) for investigation.
- Implementation too entangled to plan? "{senior}" (Fable) writes code — rare and deliberate; prefer a plan and an
  executor.
- End every brief with a return cap: "at most 15 lines — what changed (file:line), what you verified, what contradicted
  the plan. No file contents, no transcripts, no diffs."
- Always pin a subagent's model. Unpinned agents inherit the premium tier.
- Your orientation budget is {budget} reads this turn; past that, send a scout.
Premium context is the scarce resource: spend it on decisions, never on data. Edits, shell, and workflows are denied by
hook — the denial tells you how to re-issue as a delegation."""

PREMIUM_BRIEF = (
    "[model tier policy — {model} (premium): plan and delegate; procedural tools are hook-denied. "
    'Delegate with Agent(subagent_type="{executor}", model="opus", ...) and cap every return. '
    "Full policy: .claude/rules/model-tier-policy.md]"
)

ORCHESTRATOR = """[model tier policy — orchestrator session ({model})]
You coordinate; you do not implement. Your surface is tickets, plans, dispatch, tracking, and status — nothing else.
- Decompose work into tickets (GitHub issues) and plan files (`.claude/plans/<slug>.plan.md`); the plan file is the
  contract you hand out.
- Dispatch with pinned models: "{executor}" (Opus) implements, "{senior}" (Fable) for entangled work, "{scout}" (Opus,
  read-only) investigates, "{runner}" (Sonnet) sweeps, "build-runner" (Sonnet) proves refs one at a time,
  "code-reviewer" reads the green diff (Fable first pass, opus follow-ups), "{architect}" (Fable) decides. Cap every
  return.
- Read tickets and plans, never source or logs. Your scarce resource is longevity: a coordinator that hoards context
  dies of compaction mid-project.
Edits, shell, and workflows are denied by hook; ticket writes are allowed. The denial tells you how to delegate."""

ORCHESTRATOR_BRIEF = (
    "[model tier policy — orchestrator session ({model}): coordinate and dispatch; procedural tools are hook-denied, "
    "ticket writes allowed. Full policy: .claude/rules/model-tier-policy.md]"
)

WORKER = """[model tier policy — active tier: {model}]
You are the executor tier: do the procedural work yourself rather than delegating it upward.
Escalate to Agent(subagent_type="{architect}", model="fable") only at a real fork — an architectural choice with lasting
consequences, a design you cannot converge on, or a repeated failure whose cause you cannot name. It returns a decision,
not code. When a decision alone would not unblock you — the design and the code must be found together, or the change is
hard to reverse — escalate to Agent(subagent_type="{senior}", model="fable") instead, which returns working code plus the
judgment calls behind it. Neither is for work that is merely tedious.
Escalation briefs are distilled: the question, options already ruled out and why, constraints, the decision needed.
Under 40 lines, no source dumps."""

WORKER_BRIEF = (
    "[model tier policy — {model}: executor tier, do the work yourself. "
    'Escalate to "{architect}" (fable) for a decision, "{senior}" (fable) only when a decision alone would not '
    "unblock the work. Full policy: .claude/rules/model-tier-policy.md]"
)


def turn_number(session_id, anchor, dedupe_key):
    """Turn counter for this session. Anchor events reset it so the next reminder is a full one.

    Returns None when this is a duplicate firing of an event already handled. If the policy is installed at both user
    and project scope, two copies of this hook run per event; without the check they would inject the reminder twice
    and advance the counter at twice the rate, so the full text would land every 5 turns instead of every 10.

    A duplicate is recognized by the *other copy's* script path, not by timing alone: without a prompt_id every
    UserPromptSubmit shares one dedupe key, and a timing-only check would swallow real turns arriving inside the
    window — no reminder, and a stalled counter. The same copy firing again is always a new event.
    """
    path = os.path.join(tempfile.gettempdir(), "claude-model-tier-ctx-%s.json" % re.sub(r"\W", "", session_id)[:64])
    state = {}
    try:
        state = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        pass

    now = time.time()
    script = os.path.abspath(__file__)
    if (
        state.get("key") == dedupe_key
        and state.get("script") not in (None, script)
        and now - float(state.get("ts") or 0) < DEDUPE_WINDOW_SECONDS
    ):
        return None  # the other installed copy already injected for this event

    count = 1 if anchor else int(state.get("turns", 0)) + 1
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"turns": count, "key": dedupe_key, "ts": now, "script": script}, fh)
    except Exception:
        pass
    return count


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)

    if os.environ.get("MODEL_TIER_POLICY", "").lower() in ("off", "0", "false"):
        sys.exit(0)

    root = project_dir(payload)
    cfg = load_config(root)
    if not cfg.get("enabled", True):
        sys.exit(0)

    model = payload.get("model") or live_model(payload.get("transcript_path")) or ""
    if isinstance(model, dict):  # SessionStart may deliver a model object
        model = model.get("id") or model.get("model") or ""
    if not model:
        sys.exit(0)

    try:
        premium = re.compile(cfg["premium_model_pattern"], re.IGNORECASE)
    except re.error:
        sys.exit(0)

    event = payload.get("hook_event_name", "UserPromptSubmit")
    anchor = event in ANCHOR_EVENTS
    try:
        interval = int(cfg.get("reminder_interval", 10))
    except (TypeError, ValueError):
        interval = 10

    dedupe_key = "%s|%s" % (event, payload.get("prompt_id") or "")
    turn = turn_number(payload.get("session_id") or "session", anchor, dedupe_key)
    if turn is None:
        sys.exit(0)  # another installed copy already injected the reminder for this event

    full = True if interval <= 1 else turn % interval == 1

    if premium.search(model):
        template = PREMIUM if full else PREMIUM_BRIEF
        context = template.format(
            model=model,
            executor=cfg["executor_agent"],
            runner=cfg["runner_agent"],
            scout=cfg["scout_agent"],
            senior=cfg["senior_agent"],
            budget=cfg.get("read_budget", 8),
        )
    elif orchestrator_active(cfg):
        template = ORCHESTRATOR if full else ORCHESTRATOR_BRIEF
        context = template.format(
            model=model,
            executor=cfg["executor_agent"],
            runner=cfg["runner_agent"],
            scout=cfg["scout_agent"],
            senior=cfg["senior_agent"],
            architect=cfg["architect_agent"],
        )
    else:
        template = WORKER if full else WORKER_BRIEF
        context = template.format(model=model, architect=cfg["architect_agent"], senior=cfg["senior_agent"])

    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

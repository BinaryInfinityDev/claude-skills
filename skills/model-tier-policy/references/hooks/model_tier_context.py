#!/usr/bin/env python3
"""Re-injects the model tier policy into context on every turn.

Wired to UserPromptSubmit (per turn), SessionStart (launch, resume, and post-compact restarts), and PostCompact. The
always-loaded rules file can drift far up the context window in a long session; this keeps the policy no more than one
turn old, which is what makes forgetting structurally impossible.

The reminder is deliberately short. A reminder that costs real premium tokens defeats its own purpose.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from model_tier_guard import load_config, live_model, project_dir
except Exception:  # pragma: no cover - guard missing means policy is not installed
    sys.exit(0)

PREMIUM = """[model tier policy — active tier: {model} (premium)]
You plan; you do not implement. Think, decide, review, delegate, and talk to the user.
- Write the plan to `.claude/plans/<slug>.plan.md`, then hand executors the path — never paste file contents into a brief.
- Delegate every procedural step: Agent(subagent_type="{executor}", model="opus", prompt=...). Use "{runner}" (Sonnet)
  for bulk mechanical work and "{scout}" (Opus, read-only) for investigation.
- End every brief with a return cap: "at most 15 lines — what changed (file:line), what you verified, what contradicted
  the plan. No file contents, no transcripts, no diffs."
- Always pin a subagent's model. Unpinned agents inherit the premium tier.
- Your orientation budget is {budget} reads this turn; past that, send a scout.
Premium context is the scarce resource: spend it on decisions, never on data. Edits, shell, and workflows are denied by
hook — the denial tells you how to re-issue as a delegation."""

WORKER = """[model tier policy — active tier: {model}]
You are the executor tier: do the procedural work yourself rather than delegating it upward.
Escalate to Agent(subagent_type="{architect}", model="fable") only at a real fork — an architectural choice with lasting
consequences, a design you cannot converge on, or a repeated failure whose cause you cannot name. Not for something you
could resolve by reading code, routine design with an obvious convention, or work that is merely tedious.
Escalation briefs are distilled: the question, options already ruled out and why, constraints, the decision needed.
Under 40 lines, no source dumps. It returns a decision, not an implementation."""


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

    if premium.search(model):
        context = PREMIUM.format(
            model=model,
            executor=cfg["executor_agent"],
            runner=cfg["runner_agent"],
            scout=cfg["scout_agent"],
            budget=cfg.get("read_budget", 8),
        )
    else:
        context = WORKER.format(model=model, architect=cfg["architect_agent"])

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": payload.get("hook_event_name", "UserPromptSubmit"),
                    "additionalContext": context,
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

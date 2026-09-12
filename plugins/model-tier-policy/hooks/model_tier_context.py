#!/usr/bin/env python3
"""Re-injects the model tier policy into context on a schedule.

Wired to UserPromptSubmit (per turn), SessionStart (launch, resume, and the restart after a compaction), and
PostModelSwitch. The always-loaded rules file can drift far up the context window in a long session; this keeps the
policy in recent context, which is what makes forgetting structurally impossible. PostCompact is deliberately not a
carrier: Claude Code discards its output, so a fragment rendered there is a fragment lost — the compaction anchor is
SessionStart with `source: "compact"`, the documented restore point.

Injected context is attached to the turn's user message and stays in the transcript, so a full reminder on every turn
accumulates — in a premium-tier session it spends exactly the budget it exists to protect. So the full text lands on
turn 1 and every `reminder_interval` turns after (default 10), and a brief marker carries the turns in between. The
anchor events — SessionStart, PostModelSwitch — always re-anchor with the full text.

A banner that is byte-identical every turn stops being parsed: it becomes furniture, and a session violated every
clause of one while its text sat in context (#31). So the brief marker varies — it carries the turn number, how far the
transcript has grown since the last anchor, the reads the guard counted last turn, and one clause of the policy per
turn, rotating — and a compaction gets a fragment of its own: provenance is what a summary compresses away, so the
turn after a compaction is told that every remembered actor and approval is unverified before it is told anything else.

The model is read from the transcript, and a fresh session has no assistant entry in it at SessionStart or on its first
prompt. Exiting silently there left the first turn — the whole of an autonomous single-turn session — with no reminder
at all, so an unknown model now renders the posture-neutral `pending` fragment instead. It does not count as a turn: the
first firing that knows the model is turn 1 and lands the full text.

The injected text itself lives in context/*.md beside this script (see render below); this file is only the loader.
"""

import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from model_tier_guard import (
        agent_ref,
        cfg_int,
        load_config,
        live_model,
        orchestrator_active,
        posture,
        project_dir,
        resolved_models,
        resolved_paths,
    )
except Exception:  # pragma: no cover - guard missing means policy is not installed
    sys.exit(0)

ANCHOR_EVENTS = ("SessionStart", "SessionResume", "PostModelSwitch")
# Events whose output Claude Code discards: nothing is rendered and no state is touched, whatever wired them.
SILENT_EVENTS = ("PostCompact", "PreCompact")
# How close together two firings of the same event must be to count as one event handled by two installed copies.
DEDUPE_WINDOW_SECONDS = 10

# The reminder text is data, not code: it lives in context/*.md beside this script — inside the plugin when running
# as a plugin hook, so the wording updates with the plugin and there is no second copy left to drift; beside the
# installed copy otherwise. This loader carries only the mechanics. Tuning the policy text is a markdown edit.
CONTEXT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "context")

FALLBACK = (
    "[model tier policy — active for {model}. Full policy: .claude/rules/model-tier-policy.md — reminder fragments "
    "missing beside the hook, so re-read the rules file now.]"
)


def render(name, values):
    """The named context fragment, placeholders filled. Degrades softly: a missing or unreadable fragment falls back
    to a one-line pointer at the rules file, and a malformed placeholder yields the raw text — still readable policy —
    rather than no reminder at all."""
    try:
        with open(os.path.join(CONTEXT_DIR, name + ".md"), encoding="utf-8") as fh:
            text = fh.read().strip()
    except Exception:
        text = FALLBACK
    try:
        return text.format(**values)
    except Exception:
        return text


def state_path(session_id):
    return os.path.join(tempfile.gettempdir(), "claude-model-tier-ctx-%s.json" % re.sub(r"\W", "", session_id)[:64])


def load_state(path):
    try:
        state = json.loads(open(path, encoding="utf-8").read())
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def save_state(path, state):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except Exception:
        pass


def turn_number(session_id, anchor, dedupe_key, advance=True):
    """Turn counter for this session. Anchor events reset it so the next reminder is a full one.

    `advance=False` records the event for de-duplication without counting it as a turn: the pending anchor fires before
    the model is known and must not use up the full-reminder slot that the first firing with a known model gets — but
    it still goes through the duplicate check below, or two installed copies would both inject it.

    Returns None when this is a duplicate firing of an event already handled. If the policy is installed at both user
    and project scope, two copies of this hook run per event; without the check they would inject the reminder twice
    and advance the counter at twice the rate, so the full text would land every 5 turns instead of every 10.

    A duplicate is recognized by the *other copy's* script path, not by timing alone: without a prompt_id every
    UserPromptSubmit shares one dedupe key, and a timing-only check would swallow real turns arriving inside the
    window — no reminder, and a stalled counter. The same copy firing again is always a new event.

    This read-then-write is not atomic: two copies firing concurrently can both inject once for that event. The cost
    is one duplicated reminder, never a missed one, and the doubled-copy configuration itself is what the installer's
    files-only mode removes — a plugin install plus a hand install is transitional, not steady state.
    """
    path = state_path(session_id)
    state = load_state(path)

    now = time.time()
    script = os.path.abspath(__file__)
    if (
        state.get("key") == dedupe_key
        and state.get("script") not in (None, script)
        and now - float(state.get("ts") or 0) < DEDUPE_WINDOW_SECONDS
    ):
        return None  # the other installed copy already injected for this event

    if advance:
        count = 1 if anchor else int(state.get("turns", 0)) + 1
    else:
        count = int(state.get("turns", 0))
    state.update({"turns": count, "key": dedupe_key, "ts": now, "script": script})
    save_state(path, state)
    return count


def transcript_growth(session_id, transcript_path, anchor):
    """KB the transcript has grown since the last anchor — a legible proxy for how far context has filled.

    Anchors (a session start, a compaction, a model switch) reset the baseline. The number is what makes the brief
    reminder escalate as the session ages instead of reading the same at turn 3 and turn 80.
    """
    try:
        size = os.path.getsize(transcript_path) if transcript_path else 0
    except Exception:
        size = 0
    path = state_path(session_id)
    state = load_state(path)
    if anchor or "anchor_bytes" not in state:
        state["anchor_bytes"] = size
        save_state(path, state)
        return 0
    try:
        return max(0, size - int(state.get("anchor_bytes") or 0)) // 1024
    except Exception:
        return 0


def reads_last_turn(session_id, previous_prompt):
    """The budgeted reads the guard counted in the previous turn — its own counter file, read only.

    The reminder fires at the start of a turn, before any read of that turn, so the count it can show is the previous
    turn's: the invisible budget made legible one turn late, which is still every turn. The guard's file names the
    last turn that had a read, so a turn with none reports 0 rather than the stale count before it; a count above the
    budget is an overrun that was denied, and is shown as such.
    """
    path = os.path.join(tempfile.gettempdir(), "claude-model-tier-%s.json" % re.sub(r"\W", "", session_id)[:64])
    try:
        state = json.loads(open(path, encoding="utf-8").read())
        if previous_prompt and state.get("turn") != previous_prompt:
            return 0
        return int(state.get("count", 0))
    except Exception:
        return 0


def next_clause_index(session_id):
    """The brief-reminder sequence number for this session — advanced per brief rendered, never per turn.

    Indexing clauses by turn number lets the full-reminder turns swallow the same clause every cycle: with ten clauses
    and an interval of ten, one clause never appears. Counting briefs instead walks the whole list whatever the
    interval.
    """
    path = state_path(session_id)
    state = load_state(path)
    index = int(state.get("clause_seq", 0))
    state["clause_seq"] = index + 1
    save_state(path, state)
    return index


def clause_of_turn(name, turn, values):
    """One clause of the posture's policy per brief, rotating through context/clauses-<posture>.md.

    `turn` is the brief sequence number (see next_clause_index). The rotation is the point: consecutive brief reminders
    never read the same, and each clause gets read on its own instead of as the middle of a banner. A clause is a
    paragraph — lines within it are joined — so a formatter that rewraps prose cannot split one; a paragraph starting
    with `#` is a comment.
    """
    clauses = []
    try:
        with open(os.path.join(CONTEXT_DIR, "clauses-%s.md" % name), encoding="utf-8") as fh:
            for block in re.split(r"\n\s*\n", fh.read()):
                text = " ".join(block.split())
                if text and not text.startswith("#"):
                    clauses.append(text)
    except Exception:
        clauses = []
    if not clauses:
        return "see the full policy."
    try:
        text = clauses[max(int(turn), 0) % len(clauses)]
    except Exception:
        text = clauses[0]
    try:
        return text.format(**values)
    except Exception:
        return text


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

    event = payload.get("hook_event_name", "UserPromptSubmit")
    if event in SILENT_EVENTS:
        sys.exit(0)  # output discarded by Claude Code; rendering here would only consume state a real anchor needs
    # SessionStart may carry `model`; PostModelSwitch carries `to_model` (the transcript still names the old one until
    # the new model answers); everything else reads the transcript.
    model = (payload.get("to_model") if event == "PostModelSwitch" else None) or payload.get("model")
    model = model or live_model(payload.get("transcript_path")) or ""
    if isinstance(model, dict):  # SessionStart may deliver a model object
        model = model.get("id") or model.get("model") or ""

    anchor = event in ANCHOR_EVENTS
    compacted = event == "SessionStart" and payload.get("source") == "compact"
    try:
        interval = int(cfg.get("reminder_interval", 10))
    except (TypeError, ValueError):
        interval = 10

    # Agent ids go through agent_ref, never straight from the config: the fragments tell the model how to spawn a
    # sibling, and a plugin-served agent only answers to `model-tier-policy:<role>`. The two fixed roles below have no
    # config key — the config decides *which* role is named, this decides how it is spelled.
    values = {
        "model": model or "an unknown model",
        "executor": agent_ref(root, cfg["executor_agent"]),
        "runner": agent_ref(root, cfg["runner_agent"]),
        "scout": agent_ref(root, cfg["scout_agent"]),
        "senior": agent_ref(root, cfg["senior_agent"]),
        "architect": agent_ref(root, cfg["architect_agent"]),
        "steward": agent_ref(root, cfg["steward_agent"]),
        "build_runner": agent_ref(root, "build-runner"),
        "code_reviewer": agent_ref(root, "code-reviewer"),
        "budget": cfg_int(cfg, "read_budget"),
        "orchestrator_budget": cfg_int(cfg, "orchestrator_read_budget"),
        "orchestrator_lines": cfg_int(cfg, "orchestrator_read_lines"),
        "return_cap": cfg_int(cfg, "return_cap_chars"),
        # The reminder text names file locations; they follow the repo's configured paths, not the shipped defaults.
        "plans": resolved_paths(cfg)["plans"].rstrip("/"),
    }
    # Each role's configured model rides beside its id: the fragments tell the coordinator what to pass, and a
    # spawn that passes the configured model is the only way a repo's override reaches a plugin-served agent.
    models = resolved_models(cfg)
    values.update(
        {
            "executor_model": models.get(cfg["executor_agent"]) or models["executor"],
            "runner_model": models.get(cfg["runner_agent"]) or models["runner"],
            "scout_model": models.get(cfg["scout_agent"]) or models["scout"],
            "senior_model": models.get(cfg["senior_agent"]) or models["senior-developer"],
            "architect_model": models.get(cfg["architect_agent"]) or models["architect"],
            "steward_model": models.get(cfg["steward_agent"]) or models["git-steward"],
            "build_runner_model": models["build-runner"],
            "code_reviewer_model": models["code-reviewer"],
            "orchestrator_model": models["orchestrator"],
        }
    )
    values["orchestrator_state"] = (
        "on (the coordinator's tier is %s; a session above it stands down)" % models["orchestrator"]
        if orchestrator_active(cfg)
        else "off"
    )

    dedupe_key = "%s|%s" % (event, payload.get("prompt_id") or "")
    session_key = payload.get("session_id") or "session"

    if not model:
        # No assistant entry in the transcript yet: a fresh SessionStart, or the first prompt. The posture cannot be
        # resolved, so say that rather than nothing — the guard resolves it at the first tool call, and the next prompt
        # carries the full reminder. The turn counter is left alone so that reminder is a full one; the duplicate check
        # still runs, so a second installed copy does not inject the anchor twice.
        if turn_number(session_key, anchor, dedupe_key, advance=False) is None:
            sys.exit(0)  # another installed copy already injected the pending anchor for this event
        transcript_growth(session_key, payload.get("transcript_path"), anchor)
        context = render("pending", values)
        if compacted:
            context = render("compact", values) + "\n\n" + context
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))
        sys.exit(0)

    turn = turn_number(session_key, anchor, dedupe_key)
    if turn is None:
        sys.exit(0)  # another installed copy already injected the reminder for this event

    full = True if interval <= 1 else turn % interval == 1

    name = posture(cfg, model)
    values["turn"] = turn
    values["growth"] = transcript_growth(session_key, payload.get("transcript_path"), anchor)
    state = load_state(state_path(session_key))
    values["reads_last"] = reads_last_turn(session_key, state.get("last_prompt"))
    state["last_prompt"] = payload.get("prompt_id")
    save_state(state_path(session_key), state)
    values["clause"] = clause_of_turn(name, next_clause_index(session_key), values) if not full else ""
    # A disabled policy announces itself on every turn — one line, no brief variant — because a policy that has
    # gone quiet is indistinguishable from one that is working.
    context = render("disabled", values) if name == "disabled" else render(name if full else name + "-brief", values)
    # The compaction fragment comes first, on every posture: what the summary dropped is decided before anything else.
    # Workers get the short form — the ledger and the steward are a coordinator's.
    if compacted:
        context = render("compact" if name in ("premium", "orchestrator", "disabled") else "compact-worker", values) + "\n\n" + context

    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if os.environ.get("MODEL_TIER_DEBUG"):  # surface the traceback for the check; still fail open
            import traceback

            traceback.print_exc()
        sys.exit(0)

#!/usr/bin/env python3
"""Re-injects the model tier policy into context on a schedule.

Wired to UserPromptSubmit (per turn), SessionStart (launch, resume, and post-compact restarts), and PostCompact. The
always-loaded rules file can drift far up the context window in a long session; this keeps the policy in recent context,
which is what makes forgetting structurally impossible.

Injected context is attached to the turn's user message and stays in the transcript, so a full reminder on every turn
accumulates — in a premium-tier session it spends exactly the budget it exists to protect. So the full text lands on
turn 1 and every `reminder_interval` turns after (default 10), and a one-line marker carries the turns in between.
SessionStart and PostCompact always re-anchor with the full text.

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
    from model_tier_guard import agent_ref, load_config, live_model, orchestrator_active, project_dir, resolved_paths
except Exception:  # pragma: no cover - guard missing means policy is not installed
    sys.exit(0)

ANCHOR_EVENTS = ("SessionStart", "PostCompact", "SessionResume")
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


def turn_number(session_id, anchor, dedupe_key):
    """Turn counter for this session. Anchor events reset it so the next reminder is a full one.

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

    # Agent ids go through agent_ref, never straight from the config: the fragments tell the model how to spawn a
    # sibling, and a plugin-served agent only answers to `model-tier-policy:<role>`. The two fixed roles below have no
    # config key — the config decides *which* role is named, this decides how it is spelled.
    values = {
        "model": model,
        "executor": agent_ref(root, cfg["executor_agent"]),
        "runner": agent_ref(root, cfg["runner_agent"]),
        "scout": agent_ref(root, cfg["scout_agent"]),
        "senior": agent_ref(root, cfg["senior_agent"]),
        "architect": agent_ref(root, cfg["architect_agent"]),
        "steward": agent_ref(root, cfg["steward_agent"]),
        "build_runner": agent_ref(root, "build-runner"),
        "code_reviewer": agent_ref(root, "code-reviewer"),
        "budget": cfg.get("read_budget", 8),
        # The reminder text names file locations; they follow the repo's configured paths, not the shipped defaults.
        "plans": resolved_paths(cfg)["plans"].rstrip("/"),
    }
    if premium.search(model):
        name = "premium"
    elif orchestrator_active(cfg):
        name = "orchestrator"
    else:
        name = "worker"
    context = render(name if full else name + "-brief", values)

    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

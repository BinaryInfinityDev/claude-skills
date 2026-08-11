#!/usr/bin/env python3
"""PreToolUse guard for the model tier policy.

Denies procedural tool calls when the *main loop* is running on the premium tier (Fable), and tells the model exactly
how to re-issue the call as a delegation to a lower tier.

Design notes:
  - There is no $CLAUDE_MODEL env var and hook input does not carry the model, so the live model is read from the
    session transcript: the last non-sidechain assistant entry's `message.model`.
  - Tool calls made inside a subagent carry `agent_id`/`agent_type` in the payload. Those are skipped entirely, so an
    Opus executor is never blocked by a policy aimed at its Fable parent.
  - Every failure path allows the call. A guardrail that bricks a session on an unparseable transcript is worse than
    one that occasionally misses.
"""

import fnmatch
import json
import os
import re
import sys
import tempfile

DEFAULTS = {
    "enabled": True,
    "premium_model_pattern": "fable",
    "read_budget": 8,
    "executor_agent": "executor",
    "runner_agent": "runner",
    "scout_agent": "scout",
    "architect_agent": "architect",
    "write_allow": [".claude/plans/**", "**/*.plan.md", ".claude/decisions/**", "decisions/**"],
    "bash_allow": [],
    "research_tools": [r"^(Read|Grep|Glob|WebFetch|WebSearch|NotebookRead)$"],
    "procedural_tools": [
        r"^(Edit|MultiEdit|Write|NotebookEdit)$",
        r"^(Bash|BashOutput|KillShell)$",
        r"^Workflow$",
        r"^mcp__github__(create|update|push|merge|delete|add_|sub_issue|fork|assign|request_|resolve"
        r"|unresolve|run_|actions_run|issue_write|pull_request_review_write)",
    ],
}

# Built-in agent types that are safe to spawn without pinning a model.
# Explore inherits the main conversation's model but is capped at Opus on the Claude API.
UNPINNED_OK = {"explore"}
# Always inherits the parent model, so it can never be made cheap.
NEVER_UNPINNED = {"fork"}

WRITE_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}


def allow():
    sys.exit(0)


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def project_dir(payload):
    return os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()


def load_config(root):
    cfg = dict(DEFAULTS)
    for name, loader in (("model-tiers.json", json.loads), ("model-tiers.yaml", None)):
        path = os.path.join(root, ".claude", name)
        if not os.path.exists(path):
            continue
        try:
            raw = open(path, encoding="utf-8").read()
            if loader is None:
                import yaml  # optional; skipped when PyYAML is absent

                data = yaml.safe_load(raw)
            else:
                data = loader(raw)
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    return cfg


def live_model(transcript_path):
    """Last non-sidechain assistant model in the transcript, or None."""
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as fh:
            fh.seek(max(0, size - 512 * 1024))
            chunk = fh.read()
        lines = chunk.decode("utf-8", "ignore").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") != "assistant" or entry.get("isSidechain"):
                continue
            model = (entry.get("message") or {}).get("model")
            if model:
                return model
    except Exception:
        return None
    return None


def matches_any(patterns, value):
    for pattern in patterns:
        try:
            if re.search(pattern, value):
                return True
        except re.error:
            continue
    return False


def path_allowed(root, path, globs):
    if not path:
        return False
    absolute = path if os.path.isabs(path) else os.path.join(root, path)
    try:
        relative = os.path.relpath(os.path.normpath(absolute), root)
    except ValueError:
        return False
    candidates = (relative, "./" + relative, os.path.normpath(absolute))
    return any(fnmatch.fnmatch(c, g) for g in globs for c in candidates)


def bump_read_count(session_key, turn_key):
    """Per-turn counter for read-family calls. Resets when the turn changes."""
    state_path = os.path.join(tempfile.gettempdir(), "claude-model-tier-%s.json" % re.sub(r"\W", "", session_key)[:64])
    state = {}
    try:
        state = json.loads(open(state_path, encoding="utf-8").read())
    except Exception:
        pass
    if state.get("turn") != turn_key:
        state = {"turn": turn_key, "count": 0}
    state["count"] = int(state.get("count", 0)) + 1
    try:
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except Exception:
        pass
    return state["count"]


def agent_pins_model(root, agent_type, premium):
    """True when the named agent definition pins a non-premium model."""
    for base in (os.path.join(root, ".claude", "agents"), os.path.expanduser("~/.claude/agents")):
        path = os.path.join(base, "%s.md" % agent_type)
        if not os.path.exists(path):
            continue
        try:
            head = open(path, encoding="utf-8").read(4096)
        except Exception:
            continue
        match = re.search(r"^model:\s*['\"]?([\w.\-]+)", head, re.MULTILINE)
        if not match:
            return False
        value = match.group(1).strip()
        return value != "inherit" and not premium.search(value)
    return False


def check_agent_call(cfg, root, tool_input, premium):
    """Reject subagent spawns that would run on the premium tier."""
    model = (tool_input.get("model") or "").strip()
    agent_type = (tool_input.get("subagent_type") or "").strip()
    if model:
        # An explicit pin is deliberate, including a premium one — the problem being solved here is *accidental*
        # inheritance, not a considered escalation.
        return None
    if agent_type.lower() in UNPINNED_OK:
        return None
    if agent_type.lower() in NEVER_UNPINNED:
        return (
            "Model tier policy: `%s` always inherits the parent model, so this would run on the premium tier.\n"
            "Use the `%s` agent instead, or pass model: \"opus\"." % (agent_type, cfg["executor_agent"])
        )
    if agent_type and agent_pins_model(root, agent_type, premium):
        return None
    return (
        "Model tier policy: a subagent's model defaults to `inherit`, so this spawn would run on the premium tier —\n"
        "the most expensive possible way to do procedural work.\n"
        "Re-issue with the model pinned: Agent(subagent_type=\"%s\", model=\"opus\", prompt=...)\n"
        "Agents available: %s (Opus, implementation), %s (Sonnet, bulk mechanical), %s (Opus, read-only research)."
        % (cfg["executor_agent"], cfg["executor_agent"], cfg["runner_agent"], cfg["scout_agent"])
    )


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        allow()

    if os.environ.get("MODEL_TIER_POLICY", "").lower() in ("off", "0", "false"):
        allow()

    # Subagent tool calls are already on a delegated tier — never gate them.
    if payload.get("agent_id") or payload.get("agent_type"):
        allow()

    root = project_dir(payload)
    cfg = load_config(root)
    if not cfg.get("enabled", True):
        allow()

    try:
        premium = re.compile(cfg["premium_model_pattern"], re.IGNORECASE)
    except re.error:
        allow()

    model = live_model(payload.get("transcript_path"))
    if not model or not premium.search(model):
        allow()  # fail open: unknown or non-premium tier

    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    delegate_hint = (
        "Delegate it: Agent(subagent_type=\"%s\", model=\"opus\", prompt=<goal, plan file path, scope, "
        "acceptance criteria, and a return cap of 15 lines>)." % cfg["executor_agent"]
    )

    if tool == "Agent":
        reason = check_agent_call(cfg, root, tool_input, premium)
        if reason:
            deny(reason)
        allow()

    if matches_any(cfg["procedural_tools"], tool):
        if tool in WRITE_TOOLS:
            target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            if path_allowed(root, target, cfg["write_allow"]):
                allow()
            deny(
                "Model tier policy: %s is procedural and you are on the premium tier (%s), which plans but does not "
                "implement.\n%s\nYou may write plan and decision files directly (%s) — put the plan on disk and hand "
                "the executor its path."
                % (tool, model, delegate_hint, ", ".join(cfg["write_allow"]))
            )

        if tool in ("Bash", "BashOutput", "KillShell"):
            command = tool_input.get("command") or ""
            if command and matches_any(cfg["bash_allow"], command):
                allow()
            deny(
                "Model tier policy: shell commands are procedural and you are on the premium tier (%s).\n%s\n"
                "The executor runs the command and reports the outcome — you do not need the transcript in context."
                % (model, delegate_hint)
            )

        if tool == "Workflow":
            deny(
                "Model tier policy: workflow agents inherit the main-loop model, so this would run the whole fan-out "
                "on the premium tier (%s).\nDelegate the orchestration instead: Agent(subagent_type=\"%s\", "
                "model=\"opus\", prompt=<the workflow goal and plan file path>)." % (model, cfg["executor_agent"])
            )

        deny(
            "Model tier policy: %s mutates external state and you are on the premium tier (%s), which plans but does "
            "not execute.\n%s" % (tool, model, delegate_hint)
        )

    budget = int(cfg.get("read_budget") or 0)
    if budget > 0 and matches_any(cfg["research_tools"], tool):
        session_key = payload.get("session_id") or "session"
        turn_key = payload.get("prompt_id") or session_key
        count = bump_read_count(session_key, turn_key)
        if count > budget:
            deny(
                "Model tier policy: orientation budget spent (%d/%d reads this turn) on the premium tier (%s). "
                "Premium context is the scarce resource — raw file contents do not belong in it.\n"
                "Send a scout instead: Agent(subagent_type=\"%s\", model=\"opus\", prompt=<the question, the paths to "
                "search, and 'return findings only — no file contents, max 15 lines'>)."
                % (count, budget, model, cfg["scout_agent"])
            )

    allow()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

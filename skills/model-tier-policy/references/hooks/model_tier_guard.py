#!/usr/bin/env python3
"""PreToolUse guard for the model tier policy.

Denies procedural tool calls when the *main loop* is running on the premium tier (Fable) — or, with orchestrator mode
marked on, when the session runs as the orchestrator on any tier — and tells the model exactly how to re-issue the
call as a delegation.

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
    "reminder_interval": 10,  # consumed by model_tier_context.py, which shares this loader
    "orchestrator_mode": False,
    # Tools the orchestrator may use even though they mutate external state: tickets are its work product.
    "orchestrator_tools_allowed": [r"^mcp__github__(issue_write|add_issue_comment|sub_issue_write)$"],
    "executor_agent": "executor",
    "runner_agent": "runner",
    "scout_agent": "scout",
    "architect_agent": "architect",
    "senior_agent": "senior-developer",
    "write_allowed": [
        ".claude/plans/**",
        "docs/plans/**",
        "**/*.plan.md",
        ".claude/decisions/**",
        "decisions/**",
        ".claude/reviews/**",
    ],
    "bash_allowed": [],
    "research_tools_allowed": [r"^(Read|Grep|Glob|WebFetch|WebSearch|NotebookRead)$"],
    "procedural_tools_denied": [
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

DENIAL_FOOTER = (
    "[This denial is the model tier policy working as intended, not a broken tool or a misconfigured repo. "
    "Do not debug the environment or look for a workaround — delegate. The user can suspend the policy with "
    "MODEL_TIER_POLICY=off.]"
)


def allow():
    sys.exit(0)


def deny(reason):
    # The footer matters: without it a denial reads like a broken tool or a misconfigured repo, and the model (or the
    # user watching it) starts debugging the environment instead of delegating.
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason + "\n" + DENIAL_FOOTER,
                }
            }
        )
    )
    sys.exit(0)


def project_dir(payload):
    return os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()


def apply_config_files(cfg, root):
    """Overlay any model-tier-policy config found under root/.claude onto cfg, in place.

    The legacy model-tiers.* names are read first so a repo installed before the rename keeps working; when both
    spellings exist, the current name wins.
    """
    for name, loader in (
        ("model-tiers.json", json.loads),
        ("model-tiers.yaml", None),
        ("model-tier-policy.json", json.loads),
        ("model-tier-policy.yaml", None),
    ):
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


def load_config(root):
    """Config layered defaults < user < project, mirroring how Claude Code resolves its own settings.

    The user layer is not optional bookkeeping: hooks always run with $CLAUDE_PROJECT_DIR pointing at the repo, so
    without this a user-scope install would read only the repo's config — and in a repo with no config at all, would
    silently ignore ~/.claude/model-tier-policy.json and fall back to the built-in defaults.
    """
    cfg = dict(DEFAULTS)
    home = os.path.expanduser("~")
    apply_config_files(cfg, home)
    if os.path.normpath(root) != os.path.normpath(home):
        apply_config_files(cfg, root)
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


def orchestrator_active(cfg):
    """True when this session's main loop is declared to run as the orchestrator.

    The marker is deliberate configuration, not inference — the guard cannot tell an Opus orchestrator session from an
    Opus executor session by model alone. A repo whose primary sessions coordinate sets "orchestrator_mode": true in
    its config; MODEL_TIER_ORCHESTRATOR=on|off flips a single session either way and wins over the config.
    """
    env = os.environ.get("MODEL_TIER_ORCHESTRATOR", "").lower()
    if env in ("on", "1", "true"):
        return True
    if env in ("off", "0", "false"):
        return False
    return bool(cfg.get("orchestrator_mode"))


def matches_any(patterns, value):
    for pattern in patterns:
        try:
            if re.search(pattern, value):
                return True
        except re.error:
            continue
    return False


def path_allowed(root, path, globs):
    """True when path is inside the project root AND matches one of the repo-relative globs.

    Containment is checked before glob matching, and it is not optional. `fnmatch` treats `*` as matching `/` too, so a
    permissive-looking entry like `**/*.plan.md` matches `../../tmp/foo.plan.md` and `/etc/cron.d/x.plan.md` just as
    happily as a path in the repo. Without the containment gate the allowlist would sanction writes anywhere on the
    filesystem.

    Paths are resolved with realpath so a symlink inside the repo cannot be used to land the write outside it, and the
    globs are matched only against the repo-relative form — an absolute candidate would reopen the same hole.
    """
    if not path:
        return False
    try:
        root_abs = os.path.realpath(root)
        absolute = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
        relative = os.path.relpath(absolute, root_abs)
    except (ValueError, OSError):
        return False
    if os.path.isabs(relative) or relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return False  # outside the project root
    return any(fnmatch.fnmatch(c, g) for g in globs for c in (relative, "./" + relative))


def bump_read_count(session_key, turn_key, call_key):
    """Per-turn counter for read-family calls. Resets when the turn changes.

    Counts each *tool call* once, not each hook invocation. If the policy is installed at both user and project scope,
    two copies of this guard fire for the same call; without the `call_key` check that would burn the read budget at
    twice the configured rate.
    """
    state_path = os.path.join(tempfile.gettempdir(), "claude-model-tier-%s.json" % re.sub(r"\W", "", session_key)[:64])
    state = {}
    try:
        state = json.loads(open(state_path, encoding="utf-8").read())
    except Exception:
        pass
    if state.get("turn") != turn_key:
        state = {"turn": turn_key, "count": 0}
    if call_key and state.get("call") == call_key:
        return int(state.get("count", 0))  # same tool call, another copy of the hook — already counted
    state["count"] = int(state.get("count", 0)) + 1
    state["call"] = call_key
    try:
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except Exception:
        pass
    return state["count"]


def agent_pins_model(root, agent_type):
    """True when the named agent definition pins a model of its own — premium or not.

    The hazard this guard exists for is *accidental* inheritance: an unpinned spawn silently running on the premium
    tier because `model` defaults to `inherit`. An agent file that names its own model cannot inherit, so it is not
    that hazard, and that holds whether the pin is cheap or premium. A premium pin in an agent definition is the same
    kind of deliberate escalation as passing `model="fable"` at the call site, which the caller above already allows —
    `senior-developer` is exactly that, and rejecting it would send the caller to the executor tier for work the role
    exists to take off it.

    `agent_type` comes from tool input and is interpolated into a path, so it is restricted to a bare filename here —
    otherwise a name like `../../some/other` would read a file outside the agents directory and take its `model:` line
    as the pin.
    """
    if not agent_type or os.sep in agent_type or (os.altsep and os.altsep in agent_type) or os.pardir in agent_type:
        return False
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
        return value != "inherit"
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
    if agent_type and agent_pins_model(root, agent_type):
        return None
    return (
        "Model tier policy: a subagent's model defaults to `inherit`, so this spawn would run on the premium tier —\n"
        "the most expensive possible way to do procedural work.\n"
        "Re-issue with the model pinned: Agent(subagent_type=\"%s\", model=\"opus\", prompt=...)\n"
        "Agents available: %s (Opus, implementation), %s (Sonnet, bulk mechanical), %s (Opus, read-only research).\n"
        "For work that genuinely needs the premium tier to write the code, `%s` pins Fable itself."
        % (
            cfg["executor_agent"],
            cfg["executor_agent"],
            cfg["runner_agent"],
            cfg["scout_agent"],
            cfg["senior_agent"],
        )
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
    is_premium = bool(model) and bool(premium.search(model))
    as_orchestrator = bool(model) and not is_premium and orchestrator_active(cfg)
    if not is_premium and not as_orchestrator:
        allow()  # fail open: unknown model, or a worker tier with no orchestrator marker

    # One denial machinery serves two postures. What differs is why: the premium tier is kept off procedural work to
    # protect its context budget; an orchestrator session is kept off it because coordination is its whole job.
    role = (
        "on the premium tier (%s), which plans but does not implement" % model
        if is_premium
        else "running as the orchestrator, which coordinates but does not implement"
    )

    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    delegate_hint = (
        "Delegate it: Agent(subagent_type=\"%s\", model=\"opus\", prompt=<goal, plan file path, scope, "
        "acceptance criteria, and a return cap of 15 lines>)." % cfg["executor_agent"]
    )

    if tool in ("Agent", "Task"):  # the subagent-spawn tool is named Task in some Claude Code builds
        # Orchestrator spawns are never gated: inheritance lands on the worker tier it already runs on, and an
        # explicit premium pin is the same deliberate escalation it is for everyone else.
        if is_premium:
            reason = check_agent_call(cfg, root, tool_input, premium)
            if reason:
                deny(reason)
        allow()

    if as_orchestrator and matches_any(cfg["orchestrator_tools_allowed"], tool):
        allow()  # tickets are the orchestrator's work product, not procedural drift

    if matches_any(cfg["procedural_tools_denied"], tool):
        if tool in WRITE_TOOLS:
            target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            if path_allowed(root, target, cfg["write_allowed"]):
                allow()
            deny(
                "Model tier policy: %s is procedural and you are %s.\n%s\nYou may write plan, decision, and review "
                "files directly (%s) — put the plan on disk and hand the executor its path."
                % (tool, role, delegate_hint, ", ".join(cfg["write_allowed"]))
            )

        if tool in ("Bash", "BashOutput", "KillShell"):
            command = tool_input.get("command") or ""
            if command and matches_any(cfg["bash_allowed"], command):
                allow()
            deny(
                "Model tier policy: shell commands are procedural and you are %s.\n%s\n"
                "The executor runs the command and reports the outcome — you do not need the transcript in context."
                % (role, delegate_hint)
            )

        if tool == "Workflow":
            if is_premium:
                deny(
                    "Model tier policy: workflow agents inherit the main-loop model, so this would run the whole "
                    "fan-out on the premium tier (%s).\nDelegate the orchestration instead: "
                    "Agent(subagent_type=\"%s\", model=\"opus\", prompt=<the workflow goal and plan file path>)."
                    % (model, cfg["executor_agent"])
                )
            deny(
                "Model tier policy: you are running as the orchestrator — orchestration happens by dispatching "
                "agents with pinned models, not by running workflows.\nDelegate: Agent(subagent_type=\"%s\", "
                "model=\"opus\", prompt=<the goal and plan file path>)." % cfg["executor_agent"]
            )

        extra = (
            ""
            if is_premium
            else "\nTicket tools the orchestrator owns are allowed via orchestrator_tools_allowed in the config."
        )
        deny(
            "Model tier policy: %s mutates external state and you are %s.\n%s%s" % (tool, role, delegate_hint, extra)
        )

    budget = int(cfg.get("read_budget") or 0)
    turn_key = payload.get("prompt_id")
    # No prompt_id means turns cannot be told apart, and a session-keyed counter would never reset — the budget would
    # lock reads out for the whole session after 8 calls. Fail open instead, like every other degraded input here.
    if budget > 0 and turn_key and matches_any(cfg["research_tools_allowed"], tool):
        session_key = payload.get("session_id") or "session"
        count = bump_read_count(session_key, turn_key, payload.get("tool_use_id"))
        if count > budget:
            scarcity = (
                "Premium context is the scarce resource — raw file contents do not belong in it."
                if is_premium
                else "The orchestrator's context is its longevity — plans and tickets belong in it, file contents "
                "do not."
            )
            deny(
                "Model tier policy: orientation budget spent (%d/%d reads this turn) and you are %s. %s\n"
                "Send a scout instead: Agent(subagent_type=\"%s\", model=\"opus\", prompt=<the question, the paths to "
                "search, and 'return findings only — no file contents, max 15 lines'>)."
                % (count, budget, role, scarcity, cfg["scout_agent"])
            )

    allow()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

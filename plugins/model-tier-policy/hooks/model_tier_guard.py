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
    # Tools a coordinating session may use even though they mutate external state — on the premium posture as much
    # as the orchestrator one, because tickets are the plan's home on either. The key's name predates that.
    "orchestrator_tools_allowed": [r"^mcp__github__(issue_write|add_issue_comment|sub_issue_write)$"],
    # Where the policy's file conventions live in THIS repo. Every rule, role, and reminder that names one of these
    # paths defers to this block, so a repo that keeps plans in docs/plans/ declares it once here instead of bending
    # its layout to the plugin's defaults. Individual keys only, no root: real repos split these locations (plans in
    # docs/, the lock in .claude/), so they must not have to move together.
    "paths": {
        "plans": ".claude/plans",
        "decisions": ".claude/decisions",
        "reviews": ".claude/reviews",
        "timings": ".claude/build-timings.md",
        "runner_lock": ".claude/build-runner.lock",
        "operating_rules": ".claude/agent-operating-rules.md",
    },
    # The model each role runs on. These are the shipped frontmatter pins; a repo overrides per role. At spawn time an
    # explicit `model` argument beats the definition's pin and a plugin's cache is read-only, so the config becomes
    # effective by being *passed*: the reminders and denials print each role with its configured model, the guard
    # refuses an unpinned premium-posture spawn whose definition pin differs from it, and hand installs bake it into
    # the agent copies. Values are Claude Code aliases (haiku/sonnet/opus/fable) or full ids; comparisons go by tier.
    "models": {
        "orchestrator": "opus",
        "architect": "fable",
        "senior-developer": "fable",
        "executor": "opus",
        "code-reviewer": "fable",
        "scout": "opus",
        "devils-advocate": "opus",
        "runner": "sonnet",
        "build-runner": "sonnet",
        "build-analyst": "haiku",
        "git-steward": "sonnet",
    },
    "executor_agent": "executor",
    "runner_agent": "runner",
    "scout_agent": "scout",
    "architect_agent": "architect",
    "senior_agent": "senior-developer",
    "steward_agent": "git-steward",
    "write_allowed": [
        ".claude/plans/**",
        "docs/plans/**",
        "**/*.plan.md",
        "**/*.tracker.md",
        "**/*.addendum.md",
        ".claude/decisions/**",
        "decisions/**",
        ".claude/reviews/**",
        ".claude/agent-operating-rules.md",
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

# Path keys that accept null as an explicit opt-out. runner_lock: null means the repo's bar command owns locking and
# the build runner neither takes nor checks a lock. The other keys are interpolated into the reminder text and named
# by the rules, so a null there is nonsense and keeps the default.
NULLABLE_PATHS = {"runner_lock"}

# The namespace Claude Code registers this policy's agents under when they are served by the plugin rather than by
# `.claude/agents/` copies. Only a plugin-served agent needs it; see agent_ref.
PLUGIN_NAME = "model-tier-policy"

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


def resolved_paths(cfg):
    """The paths block with defaults filled in for any key the user's config left out.

    `load_config` overlays user config with a plain dict.update, so a user block naming only `plans` would otherwise
    silently drop the defaults for every sibling key — the ad-hoc path handling this block exists to replace.
    """
    paths = dict(DEFAULTS["paths"])
    user = cfg.get("paths")
    if isinstance(user, dict):
        for key, value in user.items():
            if isinstance(value, str) and value:
                paths[key] = value
            elif value is None and key in NULLABLE_PATHS:
                paths[key] = None
    return paths


def paths_write_globs(paths):
    """Write-allowlist globs implied by the configured paths, so declaring a location is enough by itself.

    Without this, moving plans to docs/plans/ would need the same fact stated twice — once in `paths` for the prose
    conventions and again in `write_allowed` for enforcement — and the two would drift.
    """
    globs = []
    for key in ("plans", "decisions", "reviews"):
        base = (paths.get(key) or "").rstrip("/")
        if base:
            globs.append(base + "/**")
    if paths.get("operating_rules"):
        globs.append(paths["operating_rules"])
    return globs


# Cheapest to costliest. A model id is placed by the alias it contains, so "claude-opus-5" and "opus" compare equal.
MODEL_TIERS = ("haiku", "sonnet", "opus", "fable")


def model_alias(value):
    """The tier alias a model id or alias names, or None when it names none of the known tiers."""
    text = (value or "").lower()
    for alias in MODEL_TIERS:
        if alias in text:
            return alias
    return None


def model_tier(value):
    """Position in MODEL_TIERS, or None for an unrecognized model."""
    alias = model_alias(value)
    return MODEL_TIERS.index(alias) if alias else None


def resolved_models(cfg):
    """The models block with defaults filled in for every role the user's config left out (same reason as paths)."""
    models = dict(DEFAULTS["models"])
    user = cfg.get("models")
    if isinstance(user, dict):
        for key, value in user.items():
            if isinstance(value, str) and value:
                models[key] = value
    return models


def role_model(models, agent_name, fallback_role):
    """The configured model for an agent name, falling back to the shipped role's when the name is a custom one."""
    return models.get(agent_name) or models.get(fallback_role) or "opus"


def posture(cfg, model):
    """Which posture the guard and the reminder take for this session: premium, orchestrator, worker, or disabled.

    One resolver for both hooks, so a denial and the reminder that explains it can never disagree.

    With orchestrator mode on, the orchestrator role has a configured model and the session is expected to run on it
    — or below; a cheaper coordinator is fine. A session opened on a *higher* tier than the configured orchestrator
    is off-design, and the policy stands down rather than fight it: "disabled", which the guard treats as allow-all
    and the reminder announces every turn, since a policy that goes quiet is the failure this plugin exists to avoid.
    An unrecognized model id on either side keeps the pre-enforcement behavior (premium pattern, else orchestrator).
    With orchestrator mode off nothing changes: the premium pattern decides between premium and worker.
    """
    if not model:
        return "worker"
    try:
        is_premium = bool(re.search(cfg["premium_model_pattern"], model, re.IGNORECASE))
    except re.error:
        is_premium = False
    if orchestrator_active(cfg):
        session_tier = model_tier(model)
        expected_tier = model_tier(resolved_models(cfg)["orchestrator"])
        if session_tier is not None and expected_tier is not None:
            return "disabled" if session_tier > expected_tier else "orchestrator"
        return "premium" if is_premium else "orchestrator"
    return "premium" if is_premium else "worker"


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


def agent_search_bases(root):
    """(directory, is_local) pairs in the order Claude Code resolves an agent name.

    Project scope first, then user scope, then the plugin's own `agents/` directory — reachable both relative to this
    script and via $CLAUDE_PLUGIN_ROOT. `is_local` records whether a hit there registers under the *bare* name
    (project/user scope) or only namespaced (plugin-served); see agent_ref.

    A hand-installed copy of this hook lives in `.claude/hooks/`, so its `../agents` is the project-scope directory,
    not a plugin's. The normalized-path check below keeps that hit classified as local.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bases = [
        (os.path.join(root, ".claude", "agents"), True),
        (os.path.expanduser("~/.claude/agents"), True),
        (os.path.normpath(os.path.join(script_dir, "..", "agents")), False),
    ]
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        bases.append((os.path.join(plugin_root, "agents"), False))
    local_dirs = {os.path.normpath(base) for base, is_local in bases if is_local}
    return [(base, is_local or os.path.normpath(base) in local_dirs) for base, is_local in bases]


def find_agent_definition(root, agent_type):
    """(path, is_local) for the first definition file matching agent_type, or (None, False) when there is none.

    `agent_type` comes from tool input and is interpolated into a path, so it is restricted to a bare filename here —
    otherwise a name like `../../some/other` would read a file outside the agents directory. A `model-tier-policy:`
    prefix is stripped first: that is how a caller addresses *these* agents when they are plugin-served, and the
    definition file is still named for the bare role. Another plugin's namespace is left alone — its agents are not in
    these directories, and stripping the prefix would match a same-named role of ours that is not the one being
    spawned.
    """
    if not agent_type:
        return None, False
    if agent_type.startswith(PLUGIN_NAME + ":"):
        agent_type = agent_type[len(PLUGIN_NAME) + 1 :]
    if not agent_type or os.sep in agent_type or (os.altsep and os.altsep in agent_type) or os.pardir in agent_type:
        return None, False
    for base, is_local in agent_search_bases(root):
        path = os.path.join(base, "%s.md" % agent_type)
        if os.path.exists(path):
            return path, is_local
    return None, False


def agent_ref(root, agent_type):
    """How *this* install must spell agent_type in `subagent_type`.

    A denial that names an unresolvable agent is worse than no denial: the model follows the instruction verbatim and
    gets "Agent type 'executor' not found", then goes looking for a broken environment. The two scopes spell the same
    role differently — a project- or user-scope `.claude/agents/executor.md` registers under the bare name and shadows
    the plugin's, while a plugin-served agent is only resolvable as `model-tier-policy:executor` — so the spelling is
    resolved the same way the definition is, rather than hardcoded either way.

    A role no definition can be found for keeps the bare name: the config names something this install does not ship,
    and inventing a namespace for it would only add a wrong prefix to an already-wrong name.
    """
    path, is_local = find_agent_definition(root, agent_type)
    if path is None or is_local:
        return agent_type
    return "%s:%s" % (PLUGIN_NAME, agent_type)


def agent_refs(root, cfg):
    """The configured role names, each spelled the way this install resolves it."""
    return {
        key: agent_ref(root, cfg[key])
        for key in ("executor_agent", "runner_agent", "scout_agent", "architect_agent", "senior_agent", "steward_agent")
    }


def agent_pins_model(root, agent_type):
    """True when the named agent definition pins a model of its own — premium or not.

    The hazard this guard exists for is *accidental* inheritance: an unpinned spawn silently running on the premium
    tier because `model` defaults to `inherit`. An agent file that names its own model cannot inherit, so it is not
    that hazard, and that holds whether the pin is cheap or premium. A premium pin in an agent definition is the same
    kind of deliberate escalation as passing `model="fable"` at the call site, which the caller above already allows —
    `senior-developer` is exactly that, and rejecting it would send the caller to the executor tier for work the role
    exists to take off it.

    Plugin-served agents are visible too: when the policy runs as a plugin there may be no `.claude/agents` copies at
    all (the installer's files-only mode removes them). Without that, every plugin agent would read as unpinned and the
    guard would demand an explicit model for definitions that already pin one.
    """
    return agent_pin(root, agent_type) is not None


def agent_pin(root, agent_type):
    """The model the named agent definition pins, or None when it has no definition, no pin, or pins `inherit`."""
    path, _ = find_agent_definition(root, agent_type)
    if path is None:
        return None
    try:
        head = open(path, encoding="utf-8").read(4096)
    except Exception:
        return None
    match = re.search(r"^model:\s*['\"]?([\w.\-]+)", head, re.MULTILINE)
    if not match or match.group(1).strip() == "inherit":
        return None
    return match.group(1).strip()


def bare_agent(agent_type):
    """The role name behind a possibly namespaced subagent_type — the key the models block uses."""
    if agent_type.startswith(PLUGIN_NAME + ":"):
        return agent_type[len(PLUGIN_NAME) + 1 :]
    return agent_type


def check_agent_call(root, refs, models, tool_input):
    """Reject subagent spawns that would run on the premium tier, or that would silently ignore the configured model."""
    model = (tool_input.get("model") or "").strip()
    agent_type = (tool_input.get("subagent_type") or "").strip()
    executor_model = role_model(models, refs["executor_agent"], "executor")
    if model:
        # An explicit pin is deliberate, including a premium one — the problem being solved here is *accidental*
        # inheritance, not a considered escalation.
        return None
    if agent_type.lower() in UNPINNED_OK:
        return None
    if agent_type.lower() in NEVER_UNPINNED:
        return (
            "Model tier policy: `%s` always inherits the parent model, so this would run on the premium tier.\n"
            "Use the `%s` agent instead, or pass model: \"%s\"." % (agent_type, refs["executor_agent"], executor_model)
        )
    pin = agent_pin(root, agent_type) if agent_type else None
    if pin:
        # The definition pins a model, so this is not the inheritance hazard — but an unpinned spawn means the
        # definition's pin wins, and if the repo configured a different model for this role, the config would be
        # ignored without anyone noticing. Make the caller pass it.
        configured = models.get(bare_agent(agent_type))
        if configured and model_alias(configured) and model_alias(pin) and model_alias(configured) != model_alias(pin):
            return (
                "Model tier policy: the config sets `%s` to model \"%s\" but its definition pins \"%s\", and this "
                "spawn passes no model — the definition would win and the config would be silently ignored.\n"
                "Re-issue with the configured model: Agent(subagent_type=\"%s\", model=\"%s\", prompt=...)"
                % (bare_agent(agent_type), configured, pin, agent_type, configured)
            )
        return None
    return (
        "Model tier policy: a subagent's model defaults to `inherit`, so this spawn would run on the premium tier —\n"
        "the most expensive possible way to do procedural work.\n"
        "Re-issue with the model pinned: Agent(subagent_type=\"%s\", model=\"%s\", prompt=...)\n"
        "Agents available: %s (%s, implementation), %s (%s, bulk mechanical), %s (%s, read-only research).\n"
        "For work that genuinely needs the premium tier to write the code, `%s` pins %s itself."
        % (
            refs["executor_agent"],
            executor_model,
            refs["executor_agent"],
            executor_model,
            refs["runner_agent"],
            role_model(models, refs["runner_agent"], "runner"),
            refs["scout_agent"],
            role_model(models, refs["scout_agent"], "scout"),
            refs["senior_agent"],
            role_model(models, refs["senior_agent"], "senior-developer"),
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

    model = live_model(payload.get("transcript_path"))
    stance = posture(cfg, model)
    if stance in ("worker", "disabled"):
        # worker: unknown model or a worker tier with no orchestrator marker — fail open. disabled: orchestrator mode
        # on a session running above the orchestrator's configured tier; the reminder hook says so every turn.
        allow()
    is_premium = stance == "premium"
    models = resolved_models(cfg)

    # One denial machinery serves two postures. What differs is why: the premium tier is kept off procedural work to
    # protect its context budget; an orchestrator session is kept off it because coordination is its whole job.
    role = (
        "on the premium tier (%s), which plans but does not implement" % model
        if is_premium
        else "running as the orchestrator, which coordinates but does not implement"
    )

    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    # Every agent id printed below is resolved, never taken from the config verbatim: a plugin-served agent only
    # answers to `model-tier-policy:<role>`, and an instruction the model cannot follow makes the denial look like a
    # broken environment instead of a policy.
    refs = agent_refs(root, cfg)
    executor_model = role_model(models, refs["executor_agent"], "executor")
    delegate_hint = (
        "Delegate it: Agent(subagent_type=\"%s\", model=\"%s\", prompt=<goal, plan file path, scope, "
        "acceptance criteria, and a return cap of 15 lines>)." % (refs["executor_agent"], executor_model)
    )

    if tool in ("Agent", "Task"):  # the subagent-spawn tool is named Task in some Claude Code builds
        # Orchestrator spawns are never gated: inheritance lands on the worker tier it already runs on, and an
        # explicit premium pin is the same deliberate escalation it is for everyone else.
        if is_premium:
            reason = check_agent_call(root, refs, models, tool_input)
            if reason:
                deny(reason)
        allow()

    if matches_any(cfg["orchestrator_tools_allowed"], tool):
        allow()  # tickets are the plan's home on either posture — coordination's work product, not procedural drift

    if matches_any(cfg["procedural_tools_denied"], tool):
        if tool in WRITE_TOOLS:
            target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            # The configured paths imply their own write permission — write_allowed extends the set, it is not the
            # only source. A repo that declares "plans": "docs/plans" gets docs/plans/** writable with no second entry.
            effective = list(cfg["write_allowed"])
            for glob in paths_write_globs(resolved_paths(cfg)):
                if glob not in effective:
                    effective.append(glob)
            if path_allowed(root, target, effective):
                allow()
            deny(
                "Model tier policy: %s is procedural and you are %s.\n%s\nYou may write plan, decision, and review "
                "files directly (%s) — put the plan on disk and hand the executor its path."
                % (tool, role, delegate_hint, ", ".join(effective))
            )

        if tool in ("Bash", "BashOutput", "KillShell"):
            command = tool_input.get("command") or ""
            if command and matches_any(cfg["bash_allowed"], command):
                allow()
            # The most common denied command in a coordinating session is a git commit of its own artifacts — the
            # uncommitted-state nag loop. Point that case at the steward, whose whole job it is.
            steward_hint = (
                '\nFor committing or pushing coordination artifacts (plan, tracker, addendum, decisions), the '
                'steward is the delegation: Agent(subagent_type="%s", model="%s", prompt=<the one-line '
                "instruction>)." % (refs["steward_agent"], role_model(models, refs["steward_agent"], "git-steward"))
                if re.search(r"\bgit\b", command)
                else ""
            )
            deny(
                "Model tier policy: shell commands are procedural and you are %s.\n%s%s\n"
                "The executor runs the command and reports the outcome — you do not need the transcript in context."
                % (role, delegate_hint, steward_hint)
            )

        if tool == "Workflow":
            if is_premium:
                deny(
                    "Model tier policy: workflow agents inherit the main-loop model, so this would run the whole "
                    "fan-out on the premium tier (%s).\nDelegate the orchestration instead: "
                    "Agent(subagent_type=\"%s\", model=\"%s\", prompt=<the workflow goal and plan file path>)."
                    % (model, refs["executor_agent"], executor_model)
                )
            deny(
                "Model tier policy: you are running as the orchestrator — orchestration happens by dispatching "
                "agents with pinned models, not by running workflows.\nDelegate: Agent(subagent_type=\"%s\", "
                "model=\"%s\", prompt=<the goal and plan file path>)." % (refs["executor_agent"], executor_model)
            )

        deny(
            "Model tier policy: %s mutates external state and you are %s.\n%s\nTicket tools are allowed on either "
            "posture via orchestrator_tools_allowed in the config." % (tool, role, delegate_hint)
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
                "Send a scout instead: Agent(subagent_type=\"%s\", model=\"%s\", prompt=<the question, the paths to "
                "search, and 'return findings only — no file contents, max 15 lines'>)."
                % (count, budget, role, scarcity, refs["scout_agent"], role_model(models, refs["scout_agent"], "scout"))
            )

    allow()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

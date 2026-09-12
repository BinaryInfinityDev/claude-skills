#!/usr/bin/env python3
"""Test bed for the model-tier-policy hooks and installer — run per commit, python3 only, no network.

Copilot's note on PR #27 was that with no CI it could not judge the Python; everything here was being run by hand from
a scratchpad (#29). It is committed now, and it never skips: a case that cannot run fails, because a gate that reports
PASS with cases omitted is reporting on a different question than the one it appears to answer (#31, finding 2).

Every hook is exercised the way Claude Code drives it — a JSON payload on stdin, a one-line transcript naming the
model, CLAUDE_PROJECT_DIR at a scratch repo, HOME at a sandbox so no user-scope config overlays.
"""

import atexit
import json
import time
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "model-tier-policy")
HOOKS = os.path.join(PLUGIN, "hooks")
GUARD = os.path.join(HOOKS, "model_tier_guard.py")
CTX = os.path.join(HOOKS, "model_tier_context.py")
RECEIPT = os.path.join(HOOKS, "model_tier_receipt.py")
INSTALL = os.path.join(PLUGIN, "skills", "model-tier-policy", "references", "install.py")
REFS = os.path.join(PLUGIN, "skills", "model-tier-policy", "references")
SCRATCH = tempfile.mkdtemp(prefix="check-hooks-")
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)  # on every exit path, a crash included
HOOK_TMP = os.path.join(SCRATCH, "tmp")  # the hooks' state files land here, never in the real temp dir
os.makedirs(HOOK_TMP)
RUN = os.urandom(3).hex()

sys.path.insert(0, HOOKS)
import model_tier_guard as g  # noqa: E402

failures = []
count = [0]


def check(name, got, want=True):
    count[0] += 1
    ok = got == want
    if not ok:
        failures.append("%s (got %r, want %r)" % (name, got, want))
    return ok


def tmp(prefix):
    return tempfile.mkdtemp(prefix=prefix + "-", dir=SCRATCH)


def write(path, text, mode="w"):
    """Write through a context manager: a bare open().write() leaves the close to the garbage collector, and a hook
    run as a subprocess may read the file before a non-refcounting runtime has flushed it."""
    with open(path, mode, encoding="utf-8") as fh:
        fh.write(text)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def make_repo(cfg, model, agents=False):
    root = tmp("repo")
    os.makedirs(os.path.join(root, ".claude", "plans"))
    os.makedirs(os.path.join(root, "src"))
    write_json(os.path.join(root, ".claude", "model-tier-policy.json"), cfg)
    write(os.path.join(root, ".claude", "plans", "p.tracker.md"), "| m1 |\n" * 300)
    write(os.path.join(root, ".claude", "plans", "p.plan.md"), "# plan\n")
    write(os.path.join(root, ".claude", "agent-operating-rules.md"), "rules\n")
    write(os.path.join(root, "src", "main.py"), "print(1)\n")
    if agents:
        shutil.copytree(os.path.join(PLUGIN, "agents"), os.path.join(root, ".claude", "agents"))
    tr = os.path.join(root, "main.jsonl")
    if model:
        write(tr, json.dumps({"type": "assistant", "message": {"model": model}}) + "\n")
    else:
        write(tr, "")
    return root, tr


def run_hook(script, payload, env_extra=None):
    """Drive a hook as Claude Code does. A hook that writes to stderr has crashed into its fail-open wrapper
    (MODEL_TIER_DEBUG makes the wrapper print the traceback), and that is a failure of its own: without it an
    "allowed" verdict and a crash look identical — the #31 finding-2 shape, inside the gate."""
    env = dict(os.environ)
    for key in ("MODEL_TIER_POLICY", "MODEL_TIER_ORCHESTRATOR", "CLAUDE_PLUGIN_ROOT"):
        env.pop(key, None)
    env["CLAUDE_PROJECT_DIR"] = payload["cwd"]
    env["HOME"] = payload["cwd"]
    env["TMPDIR"] = HOOK_TMP
    env["MODEL_TIER_DEBUG"] = "1"
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, script], input=json.dumps(payload), capture_output=True, text=True, env=env)
    if proc.stderr.strip():
        count[0] += 1
        failures.append("%s wrote to stderr on %s %s: %s" % (
            os.path.basename(script), payload.get("hook_event_name"), payload.get("tool_name", ""),
            proc.stderr.strip().splitlines()[-1][:160]))
    out = proc.stdout.strip()
    try:
        return json.loads(out) if out else None
    except ValueError:
        return {"_raw": out}


def call(root, tr, tool, tool_input=None, prompt="p1", session=None, **extra):
    payload = {"cwd": root, "transcript_path": tr, "tool_name": tool, "tool_input": tool_input or {},
               "session_id": session or "s" + RUN + os.urandom(2).hex(), "prompt_id": prompt,
               "tool_use_id": os.urandom(4).hex(), "hook_event_name": "PreToolUse"}
    payload.update(extra)
    return payload


def decision(res):
    return (res or {}).get("hookSpecificOutput", {}).get("permissionDecision")


def reason(res):
    return (res or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


def updated(res):
    return (res or {}).get("hookSpecificOutput", {}).get("updatedInput")


def guard(root, tr, tool, tool_input=None, **kw):
    return run_hook(GUARD, call(root, tr, tool, tool_input, **kw))


def context(root, tr, event="UserPromptSubmit", session=None, prompt=None, script=CTX, **extra):
    payload = {"cwd": root, "transcript_path": tr, "hook_event_name": event, "session_id": session or "c" + RUN}
    if prompt:
        payload["prompt_id"] = prompt
    payload.update(extra)
    return (run_hook(script, payload) or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


def unfilled(text):
    return re.findall(r"\{[a-z_]+\}", text)


# ---------------------------------------------------------------------------------------------------------------- compile
for script in (GUARD, CTX, RECEIPT, INSTALL):
    proc = subprocess.run([sys.executable, "-m", "py_compile", script], capture_output=True, text=True)
    check("compile %s" % os.path.basename(script), proc.returncode, 0)

# ---------------------------------------------------------------------------------------------------------- guard: postures
premium, tr_p = make_repo({}, "claude-fable-5-1")
orch, tr_o = make_repo({"orchestrator_mode": True}, "claude-opus-5")
worker, tr_w = make_repo({}, "claude-opus-5")
disabled, tr_d = make_repo({"orchestrator_mode": True}, "claude-fable-5-1")

check("posture premium", g.posture(g.load_config(premium), "claude-fable-5-1"), "premium")
check("posture orchestrator", g.posture(g.load_config(orch), "claude-opus-5"), "orchestrator")
check("posture worker", g.posture(g.load_config(worker), "claude-opus-5"), "worker")
check("posture disabled", g.posture(g.load_config(disabled), "claude-fable-5-1"), "disabled")
check("guard premium: shell denied", decision(guard(premium, tr_p, "Bash", {"command": "ls"})), "deny")
check("guard orch: shell denied", decision(guard(orch, tr_o, "Bash", {"command": "ls"})), "deny")
check("guard worker: shell allowed", decision(guard(worker, tr_w, "Bash", {"command": "ls"})), None)
check("guard disabled: shell allowed", decision(guard(disabled, tr_d, "Bash", {"command": "ls"})), None)
check("guard worker via MODEL_TIER_ORCHESTRATOR=off overrides config",
      decision(run_hook(GUARD, call(orch, tr_o, "Bash", {"command": "ls"}), {"MODEL_TIER_ORCHESTRATOR": "off"})), None)
check("guard orch via MODEL_TIER_ORCHESTRATOR=on overrides config",
      decision(run_hook(GUARD, call(worker, tr_w, "Bash", {"command": "ls"}), {"MODEL_TIER_ORCHESTRATOR": "on"})), "deny")
check("guard: MODEL_TIER_POLICY=off suspends", decision(run_hook(GUARD, call(premium, tr_p, "Bash", {"command": "ls"}), {"MODEL_TIER_POLICY": "off"})), None)
check("guard: enabled false suspends", decision(guard(*make_repo({"enabled": False}, "claude-fable-5-1"), "Bash", {"command": "ls"})), None)
r = guard(orch, tr_o, "Bash", {"command": "git commit -am x"})
check("guard orch: git denial names the steward with the resolved id", "model-tier-policy:git-steward" in reason(r))
check("guard: tier denial footer separates tier from authorization", "confers no permission" in reason(r))

# ------------------------------------------------------------------------------------------------------- guard: write gates
for root, tr, label in ((premium, tr_p, "premium"), (orch, tr_o, "orch")):
    check("guard %s: Write under paths.plans allowed" % label, decision(guard(root, tr, "Write", {"file_path": ".claude/plans/x.plan.md"})), None)
    check("guard %s: Write under paths.decisions allowed" % label, decision(guard(root, tr, "Write", {"file_path": ".claude/decisions/0001.md"})), None)
    check("guard %s: Write under paths.reviews allowed" % label, decision(guard(root, tr, "Write", {"file_path": ".claude/reviews/pr-1.md"})), None)
    check("guard %s: Edit operating rules allowed" % label, decision(guard(root, tr, "Edit", {"file_path": ".claude/agent-operating-rules.md"})), None)
    check("guard %s: write_allowed suffix glob allowed anywhere in the repo" % label, decision(guard(root, tr, "Write", {"file_path": "docs/x.tracker.md"})), None)
    check("guard %s: Edit source denied" % label, decision(guard(root, tr, "Edit", {"file_path": "src/main.py"})), "deny")
    check("guard %s: write outside the repo denied (containment)" % label, decision(guard(root, tr, "Write", {"file_path": "../x.plan.md"})), "deny")
custom, tr_c = make_repo({"paths": {"plans": "docs/plans"}}, "claude-fable-5-1")
check("guard: configured paths.plans derives its write glob", decision(guard(custom, tr_c, "Write", {"file_path": "docs/plans/x.md"})), None)

# -------------------------------------------------------------------------------------------------------- guard: Agent gate
check("guard premium: unpinned spawn denied", decision(guard(premium, tr_p, "Agent", {"subagent_type": "general-purpose"})), "deny")
check("guard premium: pinned spawn allowed", decision(guard(premium, tr_p, "Agent", {"subagent_type": "general-purpose", "model": "opus"})), None)
check("guard premium: Explore unpinned allowed", decision(guard(premium, tr_p, "Agent", {"subagent_type": "Explore"})), None)
check("guard premium: fork unpinned denied", decision(guard(premium, tr_p, "Agent", {"subagent_type": "fork"})), "deny")
check("guard premium: definition-pinned plugin role allowed unpinned", decision(guard(premium, tr_p, "Agent", {"subagent_type": "model-tier-policy:executor"})), None)
check("guard orch (worker tier): unpinned spawn allowed", decision(guard(orch, tr_o, "Agent", {"subagent_type": "general-purpose"})), None)
mismatch, tr_m = make_repo({"models": {"executor": "sonnet"}}, "claude-fable-5-1")
r = guard(mismatch, tr_m, "Agent", {"subagent_type": "model-tier-policy:executor"})
check("guard: pin that disagrees with models denied with the re-issue text", decision(r) == "deny" and 'model="sonnet"' in reason(r))
check("guard premium: Workflow denied", decision(guard(premium, tr_p, "Workflow", {})), "deny")
check("guard orch: Workflow denied", decision(guard(orch, tr_o, "Workflow", {})), "deny")

# ------------------------------------------------------------------------------------------------------ guard: GitHub tools
for root, tr, label in ((premium, tr_p, "premium"), (orch, tr_o, "orch")):
    for tool in ("mcp__github__create_pull_request", "mcp__github__enable_pr_auto_merge", "mcp__github__pull_request_review_write"):
        check("guard %s: %s denied" % (label, tool), decision(guard(root, tr, tool, {})), "deny")
    for tool in ("mcp__github__issue_write", "mcp__github__add_issue_comment", "mcp__github__sub_issue_write"):
        check("guard %s: %s allowed (ticket tool)" % (label, tool), decision(guard(root, tr, tool, {})), None)
    for tool in ("mcp__Claude_Code_Remote__subscribe_pr_activity", "mcp__Claude_Code_Remote__send_later"):
        check("guard %s: %s allowed" % (label, tool), decision(guard(root, tr, tool, {})), None)

# ------------------------------------------------------------------------------------------------- guard: premium read budget
sess = "b" + RUN
for i in range(8):
    guard(premium, tr_p, "Read", {"file_path": "src/main.py"}, session=sess)
r = guard(premium, tr_p, "Read", {"file_path": "src/main.py"}, session=sess)
check("guard premium: ninth read of a turn denied", decision(r) == "deny" and "9/8" in reason(r))
check("guard premium: read denial names the scout", "model-tier-policy:scout" in reason(r))
check("guard premium: budget resets on a new prompt_id", decision(guard(premium, tr_p, "Read", {"file_path": "src/main.py"}, session=sess, prompt="p2")), None)

# ------------------------------------------------------------------------------------------------ guard: ids resolve per install
local, tr_l = make_repo({}, "claude-fable-5-1", agents=True)
r = guard(local, tr_l, "Bash", {"command": "ls"})
check("guard: denial spells the bare id when .claude/agents ships the role", 'subagent_type="executor"' in reason(r))
r = guard(premium, tr_p, "Bash", {"command": "ls"})
check("guard: denial spells the namespaced id when the plugin serves the role", 'subagent_type="model-tier-policy:executor"' in reason(r))

# -------------------------------------------------------------------------------------------------- guard: authorization (#30)
for root, tr, label in ((premium, tr_p, "premium"), (orch, tr_o, "orch"), (worker, tr_w, "worker"), (disabled, tr_d, "disabled")):
    r = guard(root, tr, "mcp__github__merge_pull_request", {"pullNumber": 1})
    check("auth %s: merge_pull_request denied as project policy" % label, decision(r) == "deny" and "not a tier question" in reason(r))
    check("auth %s: push to main denied" % label, decision(guard(root, tr, "Bash", {"command": "git push origin main"})), "deny")
r = guard(worker, tr_w, "mcp__github__merge_pull_request", {}, agent_id="a1", agent_type="executor")
check("auth: subagent merge denied — authorization precedes the exemption", decision(r) == "deny" and "every agent" in reason(r))
check("auth: subagent gh pr merge denied", decision(guard(worker, tr_w, "Bash", {"command": "gh pr merge 5 --squash"}, agent_id="a1")), "deny")
check("auth: subagent feature push allowed", decision(guard(worker, tr_w, "Bash", {"command": "git push -u origin feat/x"}, agent_id="a1")), None)
check("auth: HEAD:master push denied", decision(guard(worker, tr_w, "Bash", {"command": "git push origin HEAD:master"})), "deny")
check("auth: main-fix branch push allowed", decision(guard(worker, tr_w, "Bash", {"command": "git push origin main-fix"})), None)
for command in ("git push origin HEAD:refs/heads/main", "git push origin refs/heads/main", "git push origin +main",
                "git -C /repo push origin main", "git -c user.name=x push origin main", "git push origin 'main'",
                "git push origin \"main\"", "git push origin main;", "git push origin :main",
                "cd x && git push --force-with-lease origin main", "gh api -X PUT repos/o/r/pulls/5/merge",
                "gh api --method PUT repos/o/r/pulls/5/merge", "gh api -X POST repos/o/r/merges -f base=main",
                "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'"):
    check("auth tripwire: %r denied" % command, decision(guard(worker, tr_w, "Bash", {"command": command})), "deny")
for command in ("gh api repos/o/r/pulls/5/merge", "gh pr view 5", "git push origin mainline",
                "git push origin feature/main-menu", "gh api repos/o/r/pulls/5/merge_requests", "git merge origin/main"):
    check("auth tripwire: %r allowed" % command, decision(guard(worker, tr_w, "Bash", {"command": command})), None)
check("auth: push_files to a protected branch denied for a subagent", decision(guard(worker, tr_w, "mcp__github__push_files", {"branch": "main", "files": []}, agent_id="a1")), "deny")
check("auth: create_or_update_file to master denied", decision(guard(worker, tr_w, "mcp__github__create_or_update_file", {"branch": "master"})), "deny")
check("auth: push_files to a feature branch allowed", decision(guard(worker, tr_w, "mcp__github__push_files", {"branch": "feat/x"}, agent_id="a1")), None)
prot, tr_prot = make_repo({"authorization": {"protected_branches": ["release"]}}, "claude-opus-5")
check("auth: configured protected_branches drive the tripwire", (decision(guard(prot, tr_prot, "Bash", {"command": "git push origin release"})), decision(guard(prot, tr_prot, "Bash", {"command": "git push origin main"}))), ("deny", None))
for command in ("gh api -XPUT repos/o/r/pulls/5/merge", "gh api repos/o/r/pulls/5/merge --method PUT",
                "gh api --input body.json repos/o/r/pulls/5/merge", "git push origin 'refs/heads/main'",
                "git push --force origin main", "git push origin main:main"):
    check("auth tripwire: %r denied" % command, decision(guard(worker, tr_w, "Bash", {"command": command})), "deny")
check("auth tripwire: the phrase in a quoted string trips it too (accepted, documented)", decision(guard(worker, tr_w, "Bash", {"command": 'echo "git push origin main"'})), "deny")
check("auth tripwire: lowercase gh api method still trips (gh uppercases it)", decision(guard(worker, tr_w, "Bash", {"command": "gh api -X put repos/o/r/pulls/5/merge"})), "deny")
extra, tr_extra = make_repo({"authorization": {"merge_commands": ["^never$"]}}, "claude-opus-5")
check("auth: configured merge_commands add to the shipped pattern, never replace it",
      (decision(guard(extra, tr_extra, "Bash", {"command": "gh pr merge 5"})), decision(guard(extra, tr_extra, "Bash", {"command": "never"})), decision(guard(extra, tr_extra, "Bash", {"command": "git push origin main"}))), ("deny", "deny", "deny"))
# The tripwire stays linear: a long command of repeated tokens must not run the hook into its timeout, where a timed-out
# PreToolUse hook renders no decision at all.
for label, command in (("gh api", "gh api x " * 4500), ("git push", "git push x " * 3700), ("mixed", "gh api x git push y ; " * 2000)):
    started = time.monotonic()
    r = guard(worker, tr_w, "Bash", {"command": command})
    elapsed = time.monotonic() - started
    check("auth tripwire: a 40 KB command of repeated '%s' tokens answers in under 3 s (took %.2f s)" % (label, elapsed), elapsed < 3.0 and decision(r) is None)
session_cfg, tr_s = make_repo({"authorization": {"merge_authority": "session"}}, "claude-opus-5")
check("auth: merge_authority session allows the merge", decision(guard(session_cfg, tr_s, "mcp__github__merge_pull_request", {})), None)
bad_cfg, tr_b = make_repo({"authorization": {"merge_authority": None}}, "claude-opus-5")
check("auth: malformed merge_authority falls back to owner", decision(guard(bad_cfg, tr_b, "mcp__github__merge_pull_request", {})), "deny")
check("auth: MODEL_TIER_POLICY=off suspends it", decision(run_hook(GUARD, call(worker, tr_w, "mcp__github__merge_pull_request", {}), {"MODEL_TIER_POLICY": "off"})), None)

# ---------------------------------------------------------------------------------------------- guard: the exemption rule (#30)
check("exempt: agent_id -> Edit allowed on the orchestrator posture", decision(guard(orch, tr_o, "Edit", {"file_path": "src/main.py"}, agent_id="a1", agent_type="executor")), None)
check("exempt: agent_type alone (a --agent main session) is gated", decision(guard(orch, tr_o, "Edit", {"file_path": "src/main.py"}, agent_type="orchestrator")), "deny")
check("exempt: agent_id alone suffices", decision(guard(orch, tr_o, "Bash", {"command": "make"}, agent_id="a2")), None)

# ------------------------------------------------------------------------------------------ guard: orchestrator reads (#30)
r = guard(orch, tr_o, "Read", {"file_path": ".claude/plans/p.tracker.md"})
check("orch Read tracker: allowed with limit clamped", decision(r) == "allow" and (updated(r) or {}).get("limit") == 200)
r = guard(orch, tr_o, "Read", {"file_path": ".claude/plans/p.tracker.md", "limit": 40})
check("orch Read with a smaller limit: input untouched", updated(r) is None or updated(r).get("limit") == 40)
check("orch Read operating rules allowed", decision(guard(orch, tr_o, "Read", {"file_path": ".claude/agent-operating-rules.md"})), "allow")
check("orch Read decisions allowed", decision(guard(orch, tr_o, "Read", {"file_path": ".claude/decisions/0001.md"})), "allow")
r = guard(orch, tr_o, "Read", {"file_path": ".claude/plans/p.plan.md"})
check("orch Read plan denied, naming the architect's brief", decision(r) == "deny" and "architect" in reason(r))
r = guard(orch, tr_o, "Read", {"file_path": "src/main.py"})
check("orch Read source denied, naming the scout", decision(r) == "deny" and "scout" in reason(r).lower())
check("orch Read receipts path denied as a handle", "handle" in reason(guard(orch, tr_o, "Read", {"file_path": ".claude/receipts/s/x.md"})))
check("orch Read outside the repo denied", decision(guard(orch, tr_o, "Read", {"file_path": "../../etc/hosts.tracker.md"})), "deny")
check("orch Grep denied", "investigation" in reason(guard(orch, tr_o, "Grep", {"pattern": "x"})))
check("orch WebFetch denied", decision(guard(orch, tr_o, "WebFetch", {"url": "https://x"})), "deny")
check("orch Glob inside plans allowed", decision(guard(orch, tr_o, "Glob", {"pattern": ".claude/plans/*.tracker.md"})), None)
check("orch Glob over src denied", decision(guard(orch, tr_o, "Glob", {"pattern": "src/**/*.py"})), "deny")
check("orch pull_request_read get_diff denied", decision(guard(orch, tr_o, "mcp__github__pull_request_read", {"method": "get_diff"})), "deny")
check("orch get_commit denied", decision(guard(orch, tr_o, "mcp__github__get_commit", {})), "deny")
check("orch search_commits denied (commit messages were the #31 leak)", decision(guard(orch, tr_o, "mcp__github__search_commits", {})), "deny")
check("orch list_releases denied", decision(guard(orch, tr_o, "mcp__github__list_releases", {})), "deny")
sess_u = "u" + RUN
for i in range(2):
    guard(orch, tr_o, "mcp__github__get_me", {}, session=sess_u)
check("orch: a GitHub read the lists do not name is still budgeted, never free", decision(guard(orch, tr_o, "mcp__github__get_me", {}, session=sess_u)), "deny")
sess_s = "sub" + RUN
subs = [decision(guard(orch, tr_o, tool, {"owner": "o", "repo": "r", "pullNumber": 1}, session=sess_s)) for tool in
        ("mcp__github__subscribe_pr_activity", "mcp__Claude_Code_Remote__subscribe_pr_activity", "mcp__github__unsubscribe_pr_activity", "mcp__github__subscribe_pr_activity")]
check("orch: subscribing to PR events is coordination — allowed on the orchestrator posture and unbudgeted", subs, [None] * 4)
check("orch pull_request_read get allowed", decision(guard(orch, tr_o, "mcp__github__pull_request_read", {"method": "get"})), None)
sess = "o" + RUN
guard(orch, tr_o, "Read", {"file_path": ".claude/plans/p.tracker.md"}, session=sess)
guard(orch, tr_o, "mcp__github__issue_read", {"method": "get"}, session=sess)
r = guard(orch, tr_o, "mcp__github__pull_request_read", {"method": "get"}, session=sess)
check("orch budget: third state read of a turn denied", decision(r) == "deny" and "3/2" in reason(r))
check("orch budget: resets on a new prompt_id", decision(guard(orch, tr_o, "Read", {"file_path": ".claude/plans/p.tracker.md"}, session=sess, prompt="p2")), "allow")
check("orch budget: ticket writes not counted", decision(guard(orch, tr_o, "mcp__github__issue_write", {}, session=sess, prompt="p2")), None)
check("orch: Edit tracker allowed", decision(guard(orch, tr_o, "Edit", {"file_path": ".claude/plans/p.tracker.md"})), None)
check("premium: Read source still allowed (budgeted, not path-gated)", decision(guard(premium, tr_p, "Read", {"file_path": "src/main.py"})), None)
check("premium: Grep still allowed", decision(guard(premium, tr_p, "Grep", {"pattern": "x"})), None)

# ------------------------------------------------------------------------------------------------------- reminder hook
fresh, tr_f = make_repo({"orchestrator_mode": True}, None)
sess = "f" + RUN
pend = context(fresh, tr_f, "SessionStart", sess, source="startup")
check("reminder: no assistant entry at SessionStart -> pending anchor", "posture pending" in pend and unfilled(pend) == [])
pend2 = context(fresh, tr_f, "UserPromptSubmit", sess, prompt="p1")
check("reminder: first prompt still unknown -> pending", "posture pending" in pend2)
write(tr_f, json.dumps({"type": "assistant", "message": {"model": "claude-opus-5"}}) + "\n")
t1 = context(fresh, tr_f, "UserPromptSubmit", sess, prompt="p2")
check("reminder: first known-model firing is turn 1, the full fragment", "orchestrator session" in t1 and "Rule of the turn" not in t1)
briefs = [context(fresh, tr_f, "UserPromptSubmit", sess, prompt="p%d" % i) for i in range(3, 12)]
check("reminder: turns 2-10 brief", all("Rule of the turn:" in b for b in briefs))
check("reminder: briefs carry no unfilled placeholders", all(unfilled(b) == [] for b in briefs))
check("reminder: consecutive briefs differ (rotating clause, turn number)", all(a != b for a, b in zip(briefs, briefs[1:])))
t11 = context(fresh, tr_f, "UserPromptSubmit", sess, prompt="p12")
check("reminder: turn 11 full again", "state reads per turn" in t11)
dd = context(disabled, tr_d, "UserPromptSubmit", "d" + RUN, prompt="p1")
check("reminder: premium under orchestrator_mode -> DISABLED notice", "DISABLED" in dd)
c0 = context(fresh, tr_f, "PostCompact", sess, trigger="auto")
check("reminder: PostCompact renders nothing (Claude Code discards its output)", c0, "")
c1 = context(fresh, tr_f, "SessionStart", sess, source="compact")
check("reminder: SessionStart(compact) after PostCompact -> compaction fragment first, full anchor after", c1.startswith("[model tier policy — COMPACTION BOUNDARY") and "unverified" in c1 and "orchestrator session" in c1)
c2 = context(fresh, tr_f, "PostCompact", sess, trigger="auto")
check("reminder: PostCompact after SessionStart(compact) -> still nothing", c2, "")
wsess = "wc" + RUN
context(worker, tr_w, "SessionStart", wsess, source="startup")
wc = context(worker, tr_w, "SessionStart", wsess, source="compact")
check("reminder: worker posture gets the short compaction form", wc.startswith("[model tier policy — COMPACTION BOUNDARY") and "steward" not in wc and "executor tier" in wc)
covsess = "cov" + RUN
seen = set()
context(orch, tr_o, "SessionStart", covsess, source="startup")
for i in range(2, 22):
    b = context(orch, tr_o, "UserPromptSubmit", covsess, prompt="c%d" % i)
    if "Rule of the turn:" in b:
        seen.add(b.split("Rule of the turn:", 1)[1].split("Full policy")[0].strip())
clauses_orch = [" ".join(x.split()) for x in re.split(r"\n\s*\n", open(os.path.join(HOOKS, "context", "clauses-orchestrator.md")).read()) if x.strip() and not x.strip().startswith("#")]
check("reminder: every orchestrator clause appears across two reminder cycles (none swallowed by the full turns)", len(seen), len(clauses_orch))
rsess = "rl" + RUN
context(orch, tr_o, "SessionStart", rsess, source="startup")
context(orch, tr_o, "UserPromptSubmit", rsess, prompt="r2")
guard(orch, tr_o, "Read", {"file_path": ".claude/plans/p.tracker.md"}, session=rsess, prompt="r2")
guard(orch, tr_o, "Read", {"file_path": ".claude/plans/p.tracker.md"}, session=rsess, prompt="r2")
b3 = context(orch, tr_o, "UserPromptSubmit", rsess, prompt="r3")
check("reminder: reads counted in the previous turn are reported", "2/2 state reads" in b3)
b4 = context(orch, tr_o, "UserPromptSubmit", rsess, prompt="r4")
check("reminder: a turn with no reads reports 0, not the stale count", "0/2 state reads" in b4)
sw = context(fresh, tr_f, "PostModelSwitch", sess, from_model="claude-opus-5", to_model="claude-fable-5-1")
check("reminder: PostModelSwitch renders for to_model", "DISABLED" in sw and "claude-fable-5-1" in sw)
pb = context(premium, tr_p, "UserPromptSubmit", "q" + RUN, prompt="p1")
check("reminder: premium full fragment names the receipt contract", "receipt" in pb and unfilled(pb) == [])
# two installed copies firing on one event inject once
dup = tmp("dup")
shutil.copytree(HOOKS, os.path.join(dup, "hooks"), ignore=shutil.ignore_patterns("__pycache__"))
twin = os.path.join(dup, "hooks", "model_tier_context.py")
sess2 = "t" + RUN
first = context(fresh, tr_f, "UserPromptSubmit", sess2, prompt="x1")
second = context(fresh, tr_f, "UserPromptSubmit", sess2, prompt="x1", script=twin)
check("reminder: a second installed copy injects nothing for the same event", bool(first) and second == "")
fresh2, tr_f2 = make_repo({"orchestrator_mode": True}, None)
sess3 = "u" + RUN
pa = context(fresh2, tr_f2, "SessionStart", sess3, source="startup")
pb2 = context(fresh2, tr_f2, "SessionStart", sess3, source="startup", script=twin)
check("reminder: the pending anchor is de-duplicated across copies too", "posture pending" in pa and pb2 == "")
# missing fragment -> fallback line, never silence
broken = tmp("broken")
shutil.copytree(HOOKS, os.path.join(broken, "hooks"), ignore=shutil.ignore_patterns("__pycache__"))
os.remove(os.path.join(broken, "hooks", "context", "orchestrator.md"))
fb = context(orch, tr_o, "SessionStart", "m" + RUN, source="startup", script=os.path.join(broken, "hooks", "model_tier_context.py"))
check("reminder: missing fragment -> one-line fallback", "reminder fragments missing" in fb)

# ------------------------------------------------------------------------------------------------- allow vs crash
# A hook that raises inside its fail-open wrapper must not read as "allowed": MODEL_TIER_DEBUG surfaces the traceback
# on stderr and run_hook records it. Proven with a copy of the guard whose Glob anchor raises.
broken_cfg, tr_bc = make_repo({"orchestrator_mode": True, "paths": {"plans": ["not", "a", "string"]}}, "claude-opus-5")
before = len(failures)
r = guard(broken_cfg, tr_bc, "Glob", {"pattern": ".claude/plans/*.md"})
check("crash detection: a malformed paths block falls back to defaults — no crash, no stderr", len(failures) == before and decision(r) is None)
crash_dir = tmp("crash")
shutil.copytree(HOOKS, os.path.join(crash_dir, "hooks"), ignore=shutil.ignore_patterns("__pycache__"))
crash_guard = os.path.join(crash_dir, "hooks", "model_tier_guard.py")
src = open(crash_guard, encoding="utf-8").read()
marker = "def glob_anchor(root, tool_input):\n"
assert marker in src
write(crash_guard, src.replace(marker, marker + "    raise RuntimeError('boom')\n", 1))
before = len(failures)
r = run_hook(crash_guard, call(orch, tr_o, "Glob", {"pattern": ".claude/plans/*.md"}))
crashed = len(failures) == before + 1 and "RuntimeError" in failures[-1] and r is None
if crashed:
    failures.pop()  # the recorded crash is the expected one; the case below is what counts
    count[0] -= 1
check("crash detection: a raising code path is reported as a failure, never read as an allow", crashed)

# ---------------------------------------------------------------------------------------------------------- receipt hook
LONG = "x" * 3000
def stop(root, tr, text, active=False):
    return {"cwd": root, "transcript_path": tr, "hook_event_name": "SubagentStop", "session_id": "r" + RUN,
            "stop_hook_active": active, "agent_id": "agent-1", "agent_type": "model-tier-policy:executor", "last_assistant_message": text}
r = run_hook(RECEIPT, stop(orch, tr_o, LONG))
check("receipt: SubagentStop over the cap blocks once with the receipt instruction", (r or {}).get("decision") == "block" and "outcome, object, evidence" in (r or {}).get("reason", ""))
filed = os.path.join(orch, ".claude", "receipts", "r" + RUN)
check("receipt: the full text is filed under paths.receipts", os.path.isdir(filed) and any(open(os.path.join(filed, f)).read().endswith(LONG) for f in os.listdir(filed)))
check("receipt: under the cap -> silent", run_hook(RECEIPT, stop(orch, tr_o, "short")), None)
check("receipt: stop_hook_active -> never a second block", run_hook(RECEIPT, stop(orch, tr_o, LONG, active=True)), None)
check("receipt: worker posture -> not capped", run_hook(RECEIPT, stop(worker, tr_w, LONG)), None)
# Two returns filed under one name must both survive — parallel dispatch ends subagents together, and the fallback
# names (`agent`, `return`) are shared — and it is the exclusive create that makes an overwrite impossible, not the
# stamp's resolution. A copy of the hook with `now` pinned files both under one stamp, so the collision is certain and
# the case verifies the suffix path itself rather than sampling the wall clock.
pinned_dir = tmp("pinned")
shutil.copytree(HOOKS, os.path.join(pinned_dir, "hooks"), ignore=shutil.ignore_patterns("__pycache__"))
pinned = os.path.join(pinned_dir, "hooks", "model_tier_receipt.py")
pin_src = open(pinned, encoding="utf-8").read()
pin_marker = "        now = time.time()\n"
assert pin_src.count(pin_marker) == 1
write(pinned, pin_src.replace(pin_marker, "        now = 1700000000.25\n", 1))
twin = dict(stop(orch, tr_o, LONG + "-first"), session_id="c" + RUN)
run_hook(pinned, twin)
run_hook(pinned, dict(twin, last_assistant_message=LONG + "-second"))
twin_dir = os.path.join(orch, ".claude", "receipts", "c" + RUN)
twin_texts = {f: open(os.path.join(twin_dir, f), encoding="utf-8").read() for f in os.listdir(twin_dir)} if os.path.isdir(twin_dir) else {}
check("receipt: two returns filed under one name and one stamp are both kept — the second takes a suffix, never overwrites",
      sorted(twin_texts) == ["agent-1-20231114T221320.250000-1.md", "agent-1-20231114T221320.250000.md"]
      and twin_texts["agent-1-20231114T221320.250000.md"].endswith(LONG + "-first")
      and twin_texts["agent-1-20231114T221320.250000-1.md"].endswith(LONG + "-second"))
post = {"cwd": orch, "transcript_path": tr_o, "hook_event_name": "PostToolUse", "session_id": "r" + RUN, "tool_name": "Agent",
        "tool_input": {"subagent_type": "executor"}, "tool_response": LONG, "tool_use_id": "toolu_1"}
r = run_hook(RECEIPT, post)
hso = (r or {}).get("hookSpecificOutput", {})
check("receipt: PostToolUse backstop cuts a string return and says where the full text is", "receipt cap" in hso.get("additionalContext", "") and isinstance(hso.get("updatedToolOutput"), str))
post["tool_response"] = {"status": "completed", "prompt": "p" * 2500, "agentId": "a1", "agentType": "executor",
                         "content": [{"type": "text", "text": LONG}]}
hso = (run_hook(RECEIPT, post) or {}).get("hookSpecificOutput", {})
out = hso.get("updatedToolOutput")
check("receipt: the real Agent shape — content blocks cut, prompt and siblings untouched",
      isinstance(out, dict) and out.get("prompt") == "p" * 2500 and out.get("status") == "completed"
      and isinstance(out.get("content"), list) and "full text is at" in out["content"][0]["text"])
post["tool_response"] = {"status": "completed", "prompt": "p" * 2500, "content": [{"type": "text", "text": "done"}]}
check("receipt: a long brief with a short return is not a long return", run_hook(RECEIPT, post), None)
post["tool_response"] = {"status": "completed", "content": [{"type": "text", "text": "b" * 200} for _ in range(10)]}
out = (run_hook(RECEIPT, post) or {}).get("hookSpecificOutput", {}).get("updatedToolOutput")
kept = "".join(b["text"] for b in out["content"] if isinstance(b, dict)) if isinstance(out, dict) else ""
def kept_text(blocks):
    """The delivered text as the coordinator sees it — blocks joined by a newline, the trailer removed."""
    texts = [b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str)]
    if texts and "[model tier policy: return cut to" in texts[-1]:
        texts[-1] = texts[-1].split("\n\n[model tier policy: return cut to", 1)[0]
    return "\n".join(texts)


check("receipt: ten 200-char blocks are cut cumulatively to exactly the cap as measured (joins counted), not left whole",
      isinstance(out, dict) and len(out["content"]) == 8 and len(kept_text(out["content"])) == 1500 and "of 2009 chars" in kept)
post["tool_response"] = {"status": "completed", "content": [{"type": "text", "text": "d" * 150} for _ in range(10)]}
out = (run_hook(RECEIPT, post) or {}).get("hookSpecificOutput", {}).get("updatedToolOutput")
check("receipt: blocks whose raw sum fits but whose joined length exceeds the cap are cut, never announced-and-delivered-whole",
      isinstance(out, dict) and len(kept_text(out["content"])) == 1500 and len(out["content"]) == 10 and "return cut to" in out["content"][-1]["text"])
post["tool_response"] = [{"type": "text", "text": "c" * 3000} for _ in range(5)]
out = (run_hook(RECEIPT, post) or {}).get("hookSpecificOutput", {}).get("updatedToolOutput")
check("receipt: five 3000-char blocks in a bare list -> one cut block, the rest dropped", isinstance(out, list) and len(out) == 1 and out[0]["text"].startswith("c" * 1500) and "c" * 1501 not in out[0]["text"])
zero, tr_z = make_repo({"orchestrator_mode": True, "return_cap_chars": 0}, "claude-opus-5")
check("receipt: return_cap_chars 0 disables", run_hook(RECEIPT, stop(zero, tr_z, LONG)), None)

# ------------------------------------------------------------------------------------------------------------- installer
def installer(target, *args, env_extra=None, cwd=None, script=INSTALL):
    env = dict(os.environ)
    env["HOME"] = os.path.join(SCRATCH, "home")
    os.makedirs(env["HOME"], exist_ok=True)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, script, "--target", target] + list(args), capture_output=True, text=True, env=env, cwd=cwd)

cfg_dir = tmp("cfg")
cache = os.path.join(cfg_dir, "plugins", "cache", "claude-skills", "model-tier-policy")
version = json.load(open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json")))["version"]
cached = os.path.join(cache, version)
shutil.copytree(PLUGIN, cached, ignore=shutil.ignore_patterns("__pycache__"))
cached_install = os.path.join(cached, "skills", "model-tier-policy", "references", "install.py")
empty = tmp("empty")
out = installer(empty, script=cached_install).stdout
cfg_path = os.path.join(empty, ".claude", "model-tier-policy.json")
check("installer (cache-shaped path): files-only install seeds exactly the three keys", sorted(json.load(open(cfg_path))) == ["bar_command", "orchestrator_mode", "paths"])
check("installer: no hook or agent copies in files-only mode", not os.path.exists(os.path.join(empty, ".claude", "hooks")) and not os.path.exists(os.path.join(empty, ".claude", "agents")))
stamp = open(os.path.join(empty, ".claude", "model-tier-policy.version")).read()
check("installer: stamp names the marketplace as source", "source: claude-skills marketplace" in stamp)
out2 = installer(empty, script=cached_install).stdout
file_lines = [line for line in out2.splitlines() if line.startswith("  ") and "settings.json" not in line]
check("installer: second run reports keep for every file line", bool(file_lines) and all(line.strip().startswith("keep") for line in file_lines))
check("installer: second run merges settings.json with nothing removed", any("settings.json" in line and "0 hook entries removed" in line for line in out2.splitlines()))
check("installer: unchanged stamp left alone", open(os.path.join(empty, ".claude", "model-tier-policy.version")).read() == stamp)
h1 = subprocess.run([sys.executable, cached_install, "--print-hash"], capture_output=True, text=True).stdout.split()[-1]
os.makedirs(os.path.join(cached, ".in_use")); write(os.path.join(cached, ".in_use", "4242"), "")
h2 = subprocess.run([sys.executable, cached_install, "--print-hash"], capture_output=True, text=True).stdout.split()[-1]
check("installer: --print-hash identical with and without .in_use/<pid>", h1, h2)
rule = os.path.join(empty, ".claude", "rules", "coordination", "state-discipline.md")
write(rule, "\nlocal edit\n", mode="a")
out3 = installer(empty, script=cached_install).stdout
check("installer: an edited seeded rule reports drift and writes .new", "drift" in out3 and os.path.exists(rule + ".new"))
write(rule, open(os.path.join(REFS, "rules", "coordination", "state-discipline.md")).read())
installer(empty, script=cached_install)
check("installer: .new removed once the copies match again", not os.path.exists(rule + ".new"))
write_json(cfg_path, {"orchestrator_mode": False, "read_budget": 8, "write_allowed": ["**/*.plan.md"]})
out4 = installer(empty, "--dry-run", script=cached_install).stdout
check("installer: a key restating a default is noted", "restates the shipped default" in out4)
check("installer: a list member missing from DEFAULTS is noted", "member" in out4 and "write_allowed" in out4)
full = tmp("full")
os.makedirs(os.path.join(full, ".claude"))
write_json(os.path.join(full, ".claude", "model-tier-policy.json"), {"models": {"executor": "sonnet"}})
installer(full, "--full")
exe = os.path.join(full, ".claude", "agents", "executor.md")
check("installer --full: configured model baked into the agent copy", os.path.exists(exe) and "\nmodel: sonnet\n" in open(exe).read())
out5 = installer(full, "--full").stdout
check("installer --full: re-run reports keep for the rendered agent copy", any("keep" in line and "executor.md" in line for line in out5.splitlines()))
hook_copy = os.path.join(full, ".claude", "hooks", "model_tier_guard.py")
os.chmod(hook_copy, 0o644)
installer(full, "--full")
check("installer: a hook copy that lost its exec bit is executable again after a keep", bool(os.stat(hook_copy).st_mode & stat.S_IXUSR))
check("installer: receipt hook copied in --full mode", os.path.exists(os.path.join(full, ".claude", "hooks", "model_tier_receipt.py")))
settings = json.load(open(os.path.join(full, ".claude", "settings.json")))
check("installer: settings wire SubagentStop, PostToolUse, and PostModelSwitch", all(k in settings.get("hooks", {}) for k in ("SubagentStop", "PostToolUse", "PostModelSwitch")))
env_cache = {"CLAUDE_CONFIG_DIR": cfg_dir}
check("installer --cache-status: current when the stamp matches the newest complete copy", installer(empty, "--cache-status", env_extra=env_cache).returncode, 0)
write(os.path.join(empty, ".claude", "model-tier-policy.version"), "model-tier-policy 99.0.0\ncontent: abc\nsource: claude-skills marketplace\n")
check("installer --cache-status: stale when the stamp is ahead of every cached copy", installer(empty, "--cache-status", env_extra=env_cache).returncode, 1)
check("installer --cache-status: missing without a cache", installer(empty, "--cache-status", env_extra={"CLAUDE_CONFIG_DIR": tmp("nocache")}).returncode, 2)
check("installer --cache-status: unknown without a stamp", installer(tmp("nostamp"), "--cache-status", env_extra=env_cache).returncode, 3)
# A copy that predates a hook cannot serve the policy that names it: a half-written newer version directory with
# the receipt hook missing is INCOMPLETE and never "ahead"; with every hook script in place the same copy counts.
ahead = os.path.join(cache, "99.0.0")
shutil.copytree(cached, ahead, ignore=shutil.ignore_patterns("__pycache__", ".in_use"))
os.remove(os.path.join(ahead, "hooks", "model_tier_receipt.py"))
write(os.path.join(empty, ".claude", "model-tier-policy.version"), "model-tier-policy 99.0.0\nsource: claude-skills marketplace\n")
r = installer(empty, "--cache-status", env_extra=env_cache)
check("installer --cache-status: a newer copy missing the receipt hook is INCOMPLETE and the status stays stale",
      r.returncode == 1 and "INCOMPLETE" in r.stdout and "newest complete: %s" % version in r.stdout)
shutil.copy2(os.path.join(cached, "hooks", "model_tier_receipt.py"), os.path.join(ahead, "hooks", "model_tier_receipt.py"))
check("installer --cache-status: the same copy with every hook script is complete and current", installer(empty, "--cache-status", env_extra=env_cache).returncode, 0)

# ------------------------------------------------------------------------------------- the remote session-start snippet
# The snippet in SKILL.md is what a consuming repo copies verbatim, so it is exercised here with a shim `claude` on PATH
# and a fabricated cache, under `set -o pipefail` (the old gate misfired under it).
skill_text = open(os.path.join(PLUGIN, "skills", "model-tier-policy", "SKILL.md"), encoding="utf-8").read()
snip_start = skill_text.index("#!/usr/bin/env bash\n# SessionStart, best-effort: bring the model-tier-policy plugin")
snippet = skill_text[snip_start:skill_text.index("```", snip_start)]
lab = tmp("snippet")
shim_dir = os.path.join(lab, "bin")
os.makedirs(shim_dir)
write(os.path.join(shim_dir, "claude"),
    "#!/usr/bin/env bash\n"
    "echo \"$*\" >>\"$SHIM_LOG\"\n"
    "case \"$1 $2\" in\n"
    "  'plugin list') printf '%s\\n' \"${SHIM_LISTING:-}\" ;;\n"
    "  'plugin update') exit \"${SHIM_UPDATE_RC:-0}\" ;;\n"
    "esac\n"
    "exit 0\n")
os.chmod(os.path.join(shim_dir, "claude"), 0o755)
script = os.path.join(lab, "ensure.sh")
write(script, "set -o pipefail\n" + snippet)


def snippet_run(label, stamp_version, listing, update_rc=0, with_cache=True):
    home = tmp("snip-home-" + label)
    repo = tmp("snip-repo-" + label)
    os.makedirs(os.path.join(repo, ".claude"))
    write_json(os.path.join(repo, ".claude", "settings.json"), {"extraKnownMarketplaces": {"claude-skills": {"source": {"source": "github", "repo": "BinaryInfinityDev/claude-skills"}}}})
    if with_cache:
        shutil.copytree(cached, os.path.join(home, ".claude", "plugins", "cache", "claude-skills", "model-tier-policy", version),
                        ignore=shutil.ignore_patterns("__pycache__", ".in_use"))
    if stamp_version:
        write(os.path.join(repo, ".claude", "model-tier-policy.version"),
            "model-tier-policy %s\ncontent: %s\nsource: claude-skills marketplace\n" % (stamp_version, h1))
    log = os.path.join(lab, "shim-%s.log" % label)
    env = dict(os.environ, HOME=home, PATH=shim_dir + os.pathsep + os.environ.get("PATH", ""), SHIM_LOG=log,
               SHIM_LISTING=listing, SHIM_UPDATE_RC=str(update_rc), MODEL_TIER_POLICY_AUTOINSTALL="1", TMPDIR=lab)
    env.pop("CLAUDE_CONFIG_DIR", None)
    proc = subprocess.run(["bash", script], cwd=repo, capture_output=True, text=True, env=env)
    calls = open(log).read() if os.path.exists(log) else ""
    return proc, calls


proc, calls = snippet_run("current", version, "  > model-tier-policy@claude-skills")
check("snippet: current + enabled -> no install, no update, exit 0, silent stdout", proc.returncode == 0 and proc.stdout == "" and "install" not in calls and "update" not in calls)
proc, calls = snippet_run("unlisted", version, "  > model-tier-policy-extras@claude-skills")
check("snippet: current cache but not enabled -> install", "plugin install model-tier-policy@claude-skills" in calls and "update" not in calls)
proc, calls = snippet_run("stale", "99.0.0", "")
check("snippet: stale -> marketplace add, update on both scopes, no install", "plugin marketplace add" in calls and calls.count("plugin update model-tier-policy@claude-skills --scope") == 2 and "plugin install" not in calls)
proc, calls = snippet_run("nocache", version, "", update_rc=1, with_cache=False)
check("snippet: no cache and update refused -> install", "plugin install model-tier-policy@claude-skills" in calls and proc.returncode == 0)
proc, calls = snippet_run("nostamp", None, "")
check("snippet: no stamp -> nothing changed, exit 0", proc.returncode == 0 and "install" not in calls and "update" not in calls)
home_off = tmp("snip-off")
proc = subprocess.run(["bash", script], cwd=home_off, capture_output=True, text=True, env=dict(os.environ, HOME=home_off, TMPDIR=lab))
check("snippet: marker unset -> inert", proc.returncode == 0 and proc.stdout == "")

# ------------------------------------------------------------------------------------------------------------ sync checks
for rel in ("build-discipline/worktree-builds.md", "coordination/coordination-artifacts.md",
            "coordination/state-discipline.md", "coordination/multi-agent-hygiene.md"):
    a = open(os.path.join(ROOT, "rules", rel), "rb").read()
    b = open(os.path.join(REFS, "rules", rel), "rb").read()
    check("rules: %s byte-identical to the plugin copy" % rel, a == b)
check("rules: semi-linear-history byte-identical to .claude/rules",
      open(os.path.join(ROOT, "rules", "git-etiquette", "semi-linear-history.md"), "rb").read()
      == open(os.path.join(ROOT, ".claude", "rules", "git-etiquette", "semi-linear-history.md"), "rb").read())
for name in sorted(os.listdir(os.path.join(HOOKS, "context"))):
    text = open(os.path.join(HOOKS, "context", name), encoding="utf-8").read()
    check("fragment %s: brackets balanced" % name, text.count("["), text.count("]"))
plugin_events = set(json.load(open(os.path.join(HOOKS, "hooks.json")))["hooks"])
snippet_events = set(json.load(open(os.path.join(REFS, "settings-snippet.json")))["hooks"])
check("hooks.json and settings-snippet.json wire the same events", plugin_events, snippet_events)

print("check-hooks: %d cases, %d failed" % (count[0], len(failures)))
for line in failures:
    print("  FAIL " + line)
sys.exit(1 if failures else 0)

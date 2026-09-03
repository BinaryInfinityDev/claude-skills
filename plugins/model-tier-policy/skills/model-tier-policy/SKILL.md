---
name: model-tier-policy
description:
  Split work across model tiers — an Opus 5 orchestrator session coordinates a team of pinned-model agents; Fable 5 does
  the thinking and planning; Opus 5 (or Sonnet 5) does everything procedural. Use when setting up or operating a session
  that must be frugal with premium-model usage limits, when the user says "Fable plans, Opus executes", asks for an
  orchestrator session, or invokes /model-tier-policy.
source: https://github.com/BinaryInfinityDev/claude-skills/blob/main/plugins/model-tier-policy/skills/model-tier-policy/SKILL.md
---

# Model Tier Policy

Keep the premium reasoning tier (**Fable 5**) doing only what it is uniquely good at — judgement, architecture,
planning, review — and push every mechanical step down to **Opus 5** (preferred) or **Sonnet 5**.

The goal is **frugality with Fable's usage limits**. The scarce resource is not Fable's time, it is Fable's _context_.
Every file dump, test log, and grep result that lands in Fable's window is premium budget spent on text a cheaper model
could have read. So the rule is stronger than "don't let Fable edit files":

> **Fable spends tokens on decisions, never on data.**

This skill is **project-agnostic**. It ships an always-on rules file, a catalog of pinned-model subagents, and two hooks
that enforce the split mechanically so the working model cannot quietly drift back into doing the work itself.

---

## The roles

Eight roles, each pinned to a model. Whoever holds the session's main loop coordinates — the orchestrator (Opus) in the
recommended topology, or the architect (Fable) in a premium-led session; the rest ship as subagents to delegate to.

| Role                       | Agent              | Model                               | Owns                                                                                                                          |
| -------------------------- | ------------------ | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Orchestrator** (coord.)  | `orchestrator`     | Opus 5 (`claude-opus-5`)            | Tickets, plans, decomposition, dispatch, tracking, status — never implementation                                              |
| **Architect** (premium)    | `architect`        | Fable 5 (`claude-fable-5`)          | Problem framing, trade-offs, architecture, task decomposition, acceptance criteria, final review                              |
| **Senior developer**       | `senior-developer` | Fable 5 (`claude-fable-5`)          | Tricky or novel implementation where design and code must be found together                                                   |
| **Executor** (default)     | `executor`         | Opus 5 (`claude-opus-5`)            | All implementation: edits, refactors, tests, builds, git, debugging                                                           |
| **Code reviewer** (gate)   | `code-reviewer`    | Fable 5 first pass, Opus follow-ups | Adversarial read of the green diff before the PR is marked ready: verdict plus ranked findings; writes only its findings file |
| **Scout** (research)       | `scout`            | Opus 5 (`claude-opus-5`), read-only | Investigation: how something works, where it lives, why it breaks, what the blast radius is                                   |
| **Devil's advocate** (opt) | `devils-advocate`  | Opus 5 (`claude-opus-5`), read-only | Adversarial review of a plan before it is built: ranked objections and a verdict                                              |
| **Runner** (bulk)          | `runner`           | Sonnet 5 (`claude-sonnet-5`)        | High-volume mechanical work — repetitive renames, formatting sweeps, boilerplate; heavy builds go to `build-runner`           |

**The orchestrator coordinates and owns nothing else.** Tickets and coordination artifacts are its work product;
everything below them is dispatched. It never edits, builds, reads source, or reads logs — and it does not make
architecture calls, it asks `architect` for them. Its scarce resource is longevity: a coordinator that hoards context
dies of compaction mid-project, so it holds ticket state, plan paths, and capped returns, nothing more. Project state
splits across three files matched to their access patterns — plan (read rarely), tracker (one line per item, edited in
place), append-only addendum (dictated, never read) — with `git-steward` doing the committing and the architect
consolidating the detail back into the plan on a watermark; the shipped `coordination-artifacts` and `state-discipline`
rules carry that discipline.

**Opus is the default worker.** Reach for Sonnet only when the task is genuinely mechanical and voluminous enough that
the tier difference matters. When unsure between Opus and Sonnet, pick Opus.

**Senior developer is the rare premium implementation tier.** Use it when the design and implementation are entangled,
an executor failed for an unnamed reason, the change is hard to reverse, or the problem is novel enough that a plan
would be guesswork. It may change the approach, not the goal. If a decision would unblock the work, use `architect`
instead; use `senior-developer` when a decision alone would not be enough.

**Scout is the one to reach for most often and remember least.** Every question you would answer by reading files is a
scout's job — it reads in its own context and returns findings, so the premium window never sees the files. The
`architect` agent exists for the mirror case: a worker-tier session escalating a decision upward.

**The devil's advocate is optional.** Send it a plan before executors start when the change is large, hard to reverse,
or built on an assumption you have not tested. Skip it for routine work — a critic invoked on everything gets ignored on
the thing that mattered. It runs on Opus because it is a check, not a second architect; pass `model: "fable"` explicitly
on the rare decision worth two premium opinions.

**The code reviewer reads the diff after the build proves it.** The full flow is
`plan → devils-advocate (optional) → executor / senior-developer → build-runner → code-reviewer → PR ready`, so a
premium review is never spent on a diff that does not build. Its model is adjustable by convention: the agent pins Fable
for the once-per-PR pass before marking ready, and follow-up re-reviews after fixes are spawned with `model: "opus"`
plus the previous findings — persist review returns under `.claude/reviews/` (in `write_allowed` for exactly this) and
the reviewer settles each prior finding, fixed or open, before hunting new ones. It never fixes; findings route back
through the caller to `executor`, or `senior-developer` when a finding reveals entanglement. Trivial changes may skip it
the way routine plans skip the devil's advocate.

**Specialists sit beside the roles, not among them.** Three ship with the policy, each kept deliberately narrow:

- `build-runner` (Sonnet 5) owns heavy build and test runs. It builds the ref under test in its own git worktree so
  development continues in the primary tree, captures output to a log file, times the run against the ledger it keeps in
  `.claude/build-timings.md`, and always cleans its worktree up — copying out anything worth keeping first. One instance
  at a time, enforced through `.claude/build-runner.lock`; the lock binds one machine, so more concurrency means other
  sessions on other hosts building a ref already pushed to a branch. It reports verdict, timing, and log path — it never
  fixes, and it hands failures to `build-analyst`. Quick, known-cheap checks (a formatter, a focused test) do not need
  it; any agent may run those in-tree.
- `build-analyst` (Haiku 4.5) is the narrow tool for one recurring waste: re-running a failed build to re-read output
  the build already wrote. Hand it the log _path_, never the log. Both `verdict: <cause>` and `verdict: undetermined`
  are first-class returns, because an honest "could not tell" costs one re-run while a confident wrong answer costs a
  wrong fix. Project-specific signatures that look like failures but are not — cache poisoning, plugin flakes, coverage
  thresholds — belong in the target repo's `.claude/build-signatures.md`, which the agent reads when present.
- `git-steward` (Sonnet 5) is the coordinator's git custodian, spawned per invocation and never kept resident. It
  commits and pushes coordination artifacts (plan, tracker, addendum, decisions, reviews, operating rules), takes
  dictated updates ("mark m13 merged as #661" costs the coordinator ten words), reconciles tracker rows against their
  issue/PR handles, and keeps branches and worktrees tidy. It never touches feature work: artifact paths only, and
  anything else dirty in the tree is reported, never committed or stashed — the push gate stays intact because the
  steward is structurally outside it.

### What "procedural" means

Procedural = anything whose _correct output is determined by the plan_, not by fresh judgement. If a competent engineer
with the plan in hand would produce essentially the same result, it is procedural:

- Writing, editing, or deleting code, config, tests, docs
- Running commands: builds, tests, linters, migrations, git
- Searching, reading, and summarizing the codebase
- Reproducing bugs, bisecting, collecting stack traces
- Applying a refactor that has already been decided

Non-procedural = the parts where a different engineer would reasonably produce a different answer: what to build, which
approach, what the interface should be, whether the result is acceptable, what to do about a surprise.

---

## Topologies: who holds the main loop

The main loop pays for **every** turn — check-ins, tool results, chatter — so which model holds it is the biggest cost
decision the policy makes.

**Opus-led orchestrator session — the recommended default.**

```
Opus session (orchestrator) ──delegates──> fable   (architect / senior-developer — rare: decisions, entangled work)
                                           opus    (executor / scout / devils-advocate)
                                           sonnet  (runner / build-runner)
                                           haiku   (build-analyst)
```

The session runs on Opus and holds the `orchestrator` role: tickets, plans, dispatch, tracking, status — never
implementation. Fable is invoked only as a subagent, only at the moments premium judgement is needed. This is strictly
more frugal than a Fable-led session: the per-turn overhead lands on Opus, and premium tokens buy decisions only.

Mark the session so the guard enforces the role: set `"orchestrator_mode": true` in `.claude/model-tier-policy.json` for
a repo whose primary sessions coordinate, or `MODEL_TIER_ORCHESTRATOR=on` in the environment for a single session (`off`
wins the other way when the config says true). The guard then denies edits, shell, and workflows exactly as it does for
Fable — with ticket writes exempted via `orchestrator_tools_allowed` — and the reminder hook injects the orchestrator
protocol instead of the worker one.

**Fable-led architect session — the alternative.** The original shape: the premium model holds the session, plans, and
delegates everything procedural downward. Right when the work is one hard design problem more than a project to
coordinate. Its protocol is the next section.

A session that is neither premium nor marked as orchestrator is a plain worker session — see
[Working the other direction](#working-the-other-direction-opus-led).

---

## Operating protocol (Architect tier)

When the session model is Fable, every turn runs this loop. Do not skip steps 2 and 3 for "quick" tasks — a quick task
is exactly the kind that should not cost premium tokens.

### 1. Think

Frame the problem, decide the approach, decompose into tasks with explicit acceptance criteria. This is the only step
that belongs on the premium tier. Do it well and at length; the savings come from steps 2–5, not from thinking less.

### 2. Write the plan to disk, not to context

Record the plan in a file (`.claude/plans/<slug>.plan.md` by default — Fable is permitted to write there). The plan file
is the contract handed to executors.

This is the single biggest frugality lever: a plan on disk survives compaction, is re-readable by every executor for
free, and means you never re-derive the same decisions after context loss. A plan that exists only in Fable's context
gets paid for twice.

Use `record-decision` for choices worth preserving beyond the task.

Add `.claude/plans/` to the repo's `.gitignore`. Plan files are session working artifacts, not deliverables — left
tracked, every session ends with an untracked-files warning from any tree-cleanliness hook. The installer does not edit
`.gitignore` for you; that is a one-line decision each repo should make deliberately.

### 2a. Stress-test the plan (optional)

For a large, hard-to-reverse, or assumption-heavy change, send the plan to `devils-advocate` before executors start:

```
Agent(subagent_type="<devils-advocate, spelled as this install resolves it>", model="opus",
      prompt=<plan file path, what you are unsure about, and 'return at most 20 lines'>)
```

See [Addressing the agents](#addressing-the-agents) for which spelling that is.

It returns a verdict — `proceed`, `fix first`, or `rethink` — with at most three ranked objections and what would settle
each. The economics are the point: a review that costs one Opus call is cheaper than executors building the wrong thing,
and far cheaper than you re-planning after they do. Skip it for routine work.

### 3. Delegate every procedural step

Spawn the `executor` subagent (Opus) — or `runner` (Sonnet) for bulk mechanical work, `scout` (Opus, read-only) for
investigation, or `build-runner` (Sonnet) for a heavy build or test run proved in its own worktree. Each brief must
carry:

| Part                    | Why                                                           |
| ----------------------- | ------------------------------------------------------------- |
| **Goal** — one sentence | So the executor knows what "done" means                       |
| **Plan file path**      | So the executor reads context from disk, not from your prompt |
| **Scope** — files/dirs  | So it does not wander                                         |
| **Acceptance criteria** | So it can self-verify before returning                        |
| **Return contract**     | So its output does not blow up your context (see below)       |

Never paste file contents into a brief. Point at paths. The executor can read.

### 4. Enforce the return contract

Every delegation ends with an explicit cap. Use this wording:

> Return at most 15 lines: what you changed (file:line), what you verified and how, and anything that contradicted the
> plan. No file contents, no command transcripts, no diffs unless I asked for a specific hunk.

Subagent output lands in Fable's context verbatim. An executor that returns a 400-line diff has just spent your premium
budget on text you did not need.

### 5. Review and decide

Read the distilled report. Decide: accept, correct, or re-plan. Corrections go back out as a new brief — you do not open
the editor yourself.

---

## What the Architect tier may do directly

A short, deliberate whitelist:

- Think, plan, decide, review
- Write plan, decision, and review files (`.claude/plans/**`, `docs/plans/**`, `**/*.plan.md`, `.claude/decisions/**`,
  `decisions/**`, `.claude/reviews/**`)
- A small orientation budget of reads/greps — **8 calls per turn by default**, enforced by the hook. Past that, send a
  `scout`. The budget exists so you can glance at one or two key files, not so you can survey the repo.
- Talk to the user, ask clarifying questions, spawn subagents

Everything else — Edit, Write outside plan paths, Bash, git, workflows — is denied by the guard hook with a message
telling you exactly how to re-issue the call as a delegation.

---

## Working the other direction (Opus-led)

If the session model is Opus or Sonnet, the policy inverts: **do the work yourself, and escalate to Fable only when
needed.** Spawn `architect` (`model: fable`) for a hard decision; spawn `senior-developer` (`model: fable`) when the
design and implementation must be discovered together or the work is too hard to hand off as a plan.

Escalation briefs must be _distilled_: state the question, the options you have already ruled out and why, the
constraints, and the specific decision you need. Never hand Fable a pile of source to read. A good escalation is under
40 lines. Architect returns a decision; senior-developer returns working code plus the judgment calls behind it.

Do not escalate for: something you are merely unsure about but could resolve by reading code, routine design with an
obvious convention to follow, or work that is just tedious.

---

## Frugality rules (both directions)

1. **No raw data on the premium tier.** File contents, logs, diffs, test output, search results — all of it gets read
   and distilled by a lower tier first.
2. **Batch decisions.** One planning pass that decomposes five tasks beats five planning passes. Premium turns have
   fixed overhead; amortize it.
3. **Plans live on disk.** Re-planning after compaction is pure waste. Point at the file.
4. **Delegate wide, not deep.** Independent tasks go out as parallel executors in a single message — they cost nothing
   extra on the premium tier and finish sooner.
5. **Cap every return.** No exceptions.
6. **Don't escalate a question a scout can answer.** "How does X work here?" is a read, not a decision.

---

## Addressing the agents

The same role has two possible ids, and only one of them resolves in any given repo.

| The roles come from                                            | `subagent_type` must be      |
| -------------------------------------------------------------- | ---------------------------- |
| the plugin (`/plugin install model-tier-policy@claude-skills`) | `model-tier-policy:executor` |
| `.claude/agents/` or `~/.claude/agents/` (installer, by hand)  | `executor`                   |

Claude Code namespaces a plugin's agents under the plugin name, so `Agent(subagent_type="executor", …)` in a
plugin-served repo fails with `Agent type 'executor' not found`. A project- or user-scope `.claude/agents/executor.md`
registers under the **bare** name and shadows the plugin's, so the same call is the only one that works there. Neither
spelling is portable — which is why nothing in this policy hardcodes one.

Both hooks resolve the id per install rather than printing the config value: they look for the definition file the same
way Claude Code does (project scope, then user scope, then the plugin's own `agents/`) and spell the role bare or
namespaced to match where it was found. So the guard's denial messages and the reminder's delegation examples always
name an id you can copy verbatim, in either setup. The config keys (`executor_agent`, `runner_agent`, `scout_agent`,
`architect_agent`, `senior_agent`) stay authoritative for _which_ role is named; they do not carry the namespace.

When you are writing the call yourself and are unsure which applies, `/agents` lists the resolvable ids.

---

## Installation

### As a plugin — the recommended path

The policy ships as the `model-tier-policy` plugin of the `claude-skills` marketplace:

```
/plugin marketplace add BinaryInfinityDev/claude-skills
/plugin install model-tier-policy@claude-skills
```

That activates the skill, all eleven agents, and both hooks immediately — enforcement and the reminder included, with
the reminder's wording loaded from context fragments inside the plugin, so **plugin updates change what the hooks say
with no further steps**. Third-party marketplaces do not auto-update by default: toggle auto-update per marketplace in
`/plugin` → Marketplaces, or pull updates by hand with `claude plugin marketplace update claude-skills`.

Two per-repo pieces are file-shaped and cannot ride a plugin — the always-loaded rules files and the
`.claude/model-tier-policy.json` config. Run the bundled installer once per repo to lay those down (it also stamps the
installed plugin version). It works from a `claude-skills` clone or from the installed plugin's own directory under
`~/.claude/plugins/cache/claude-skills/model-tier-policy/<version>/`:

```bash
python3 <plugin-dir>/skills/model-tier-policy/references/install.py --target /path/to/repo
```

Run from an installed plugin's directory, the installer detects plugin mode and does a **files-only** install: it lays
down the rules, config, and stamp, skips its own hook and agent copies, and removes any it finds from an earlier hand
install. That removal is the point, not tidiness — local copies do not defer to the plugin: a project-scope agent file
_shadows_ the plugin's on a name collision, and a doubled reminder hook injects whichever copy fires first, so stale
copies would keep speaking for the policy after a plugin update. (`--files-only` requests the same from a checkout;
`--full` forces the copy-everything install anyway. The hooks de-duplicate a doubled event, so the forced overlap costs
waste, not correctness.)

When this skill is invoked in a repo that has a `.claude/model-tier-policy.version` stamp, compare it against the
installed plugin's current `.claude-plugin/plugin.json` version; if they differ, say so and offer to re-run the
installer so the file-shaped pieces catch up. The stamp also carries a `content:` hash — compare it against
`install.py --print-hash` run from the live plugin directory. A **matching version with a differing hash** is the
branch-pinned failure the version number cannot see: every push to a pinned branch is a de facto release, so the cache
can go stale while `claude plugin update` keeps reporting "already at the latest version". When the hashes differ,
refresh the marketplace (`claude plugin marketplace update <name>`), reinstall if needed, and re-run the installer. In
this setup those files are the only thing that can drift — with no local copies left, the plugin serves the hooks and
agents live.

### In Claude Code Remote / cloud sessions

**A fresh remote container starts with an empty marketplace cache**, even when the project's `.claude/settings.json`
declares `extraKnownMarketplaces` and `enabledPlugins`. `claude plugin marketplace list` reports
`No marketplaces configured`, so none of the eleven agents and neither hook exists in that session.

The asymmetry is what makes this dangerous rather than merely inconvenient. The rules file, the config, and the version
stamp are **committed repo files**, so they load normally. The session therefore reads an always-loaded policy telling
it to delegate to `executor`/`scout`/`build-runner` and asserting that `PreToolUse` hooks enforce that — with none of
the machinery present. The policy degrades silently into advice, in exactly the environment where no one is watching the
session drift back into doing the work itself.

A plugin cannot install itself, but a repo can close the gap with a `SessionStart` hook that installs it when missing.
That **binds the plugin in the same session** — agents spawnable and the guard firing on that session's own `Bash`
calls, not from the next session onward. Pre-provisioning the container from an environment setup script is therefore an
optimization, not a requirement.

Five properties matter, and the snippet below is shaped by them:

- **Best-effort, never blocking.** Every failure path exits 0. A session that cannot start because a plugin install
  failed is worse than a session without the plugin.
- **Nothing on stdout.** A `SessionStart` hook's stdout is injected into the session's context. Diagnostics go to a log
  file and to stderr.
- **Fast when there is nothing to do.** Gate on `claude plugin list`; the already-installed path costs about 0.7 s
  against roughly 4 s for the install. Match the plugin's full `name@marketplace` id rather than a substring of it, so a
  differently-named plugin that merely contains the name cannot satisfy the gate.
- **Remote only.** Set the marker variable in the remote environment's configuration and leave it unset locally, so the
  hook is inert on a developer machine that manages its own plugins.
- **One source for the marketplace URL.** Read it out of `.claude/settings.json` rather than repeating it in the hook,
  so the declaration stays the single place it is written down.

`.claude/hooks/ensure-model-tier-policy.sh`:

```bash
#!/usr/bin/env bash
# SessionStart, best-effort: install the model-tier-policy plugin when this session started without it.
# Never blocks the session, and never writes to stdout — SessionStart stdout is injected into context.
set -u

LOG="${TMPDIR:-/tmp}/model-tier-policy-install.log"
exec >>"$LOG" # stdout to the log; stderr is left alone, so a real failure still surfaces
echo "=== $(date -Is) SessionStart in $PWD ==="

# Remote only: set MODEL_TIER_POLICY_AUTOINSTALL=1 in the cloud environment's variables, and leave it unset locally.
[ "${MODEL_TIER_POLICY_AUTOINSTALL:-0}" = "1" ] || { echo "marker unset — skipping"; exit 0; }

# Already there: the local case, and every session after the first in a warm container.
# `claude plugin list` prints one `  > NAME@MARKETPLACE` line per plugin. Anchor the match to that whole id —
# a bare substring match would also be satisfied by an unrelated `model-tier-policy-extras@…`.
if claude plugin list 2>/dev/null | grep -qE '(^|[[:space:]>])model-tier-policy@claude-skills([[:space:]]|$)'; then
  echo "already installed"; exit 0
fi

# The marketplace is declared once, in .claude/settings.json. Read it from there.
URL=$(python3 - <<'EOF' 2>/dev/null
import json
try:
    settings = json.load(open(".claude/settings.json"))
except Exception:
    raise SystemExit(0)
entry = (settings.get("extraKnownMarketplaces") or {}).get("claude-skills") or {}
source = entry.get("source", entry) if isinstance(entry, dict) else entry
if isinstance(source, str):
    print(source)
elif isinstance(source, dict):
    for key in ("repo", "url", "path", "source"):
        value = source.get(key)
        if isinstance(value, str) and value not in ("github", "git", "local"):
            print(value)
            break
EOF
)
[ -n "$URL" ] || { echo "no claude-skills marketplace declared in .claude/settings.json"; exit 0; }

claude plugin marketplace add "$URL" || { echo "marketplace add failed"; exit 0; }
claude plugin install model-tier-policy@claude-skills || { echo "install failed"; exit 0; }
echo "installed"
exit 0
```

Wire it in `.claude/settings.json` alongside whatever else runs at session start:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{ "type": "command", "command": "bash .claude/hooks/ensure-model-tier-policy.sh" }]
      }
    ]
  }
}
```

The per-repo file pieces are unaffected — the rules and config are committed, so they are already in the clone. If the
repo does **not** commit them, run `install.py --files-only` from the same hook after the install step.

Two things to know while testing this. Agents are namespaced when they arrive by plugin, so the ids resolve as
`model-tier-policy:executor` rather than `executor` — see [Addressing the agents](#addressing-the-agents). And
`claude plugin marketplace remove <name>` **rewrites the project's committed `.claude/settings.json`** as a side effect,
stripping `extraKnownMarketplaces` and `enabledPlugins` and re-encoding non-ASCII characters; check `git diff` after any
teardown.

### By hand — without the marketplace

**Copying the skill directory somewhere does not install the policy.** A skill loads on demand and activates nothing;
the files under `references/` are inert wherever the skill lives. Enforcement comes from `install.py`, which copies
those files to the paths Claude Code actually reads. Both steps are useful and they are independent:

| Step                                                                                                   | Gives you                                                         |
| ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| Copy `plugins/model-tier-policy/skills/model-tier-policy/` to `~/.claude/skills/` or `.claude/skills/` | The `/model-tier-policy` doc and trigger — no enforcement         |
| Run `install.py --target <repo>`                                                                       | The rules file, the agents, and the two hooks — the actual policy |

Having the skill at user level and the policy installed per repo is the expected setup: the skill copy creates nothing
under `~/.claude/agents/`, `~/.claude/hooks/`, `~/.claude/rules/`, or `~/.claude/settings.json`, so there is exactly one
active copy of everything. The one consequence is that the two copies of the files are independent — after updating the
skill, re-run `install.py` to carry the change into each repo. Re-running is safe and reports `update` for any file that
actually drifted.

Do **not** install at both user and project scope. Two copies of each hook then fire per event; they de-duplicate, so
the read budget and reminder cadence stay correct, but the second copy is wasted work and the two configs diverge
silently. The installer warns when it detects the other scope.

Run from the repo you want the policy active in:

```bash
python3 /path/to/claude-skills/plugins/model-tier-policy/skills/model-tier-policy/references/install.py --target /path/to/repo
```

Run it from a full `model-tier-policy` plugin directory — an installed plugin or a `claude-skills` checkout. The agent
definitions and hooks live at the plugin root (`agents/`, `hooks/`) rather than inside the skill, so a lone copy of the
skill directory has nothing to install them from — the installer says so and exits rather than writing a half-installed
policy.

The installer is idempotent and reports what it changed. It writes:

| File                                                   | Role                                                                                         |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| `.claude/rules/model-tier-policy.md`                   | Always-loaded rules — in context every session, survives compaction                          |
| `.claude/rules/build-discipline/worktree-builds.md`    | Always-loaded — builds in worktrees beside development, pushes gated on green                |
| `.claude/rules/coordination/coordination-artifacts.md` | Always-loaded — plan/tracker/addendum discipline, the steward, consolidation                 |
| `.claude/rules/coordination/state-discipline.md`       | Always-loaded — verify repo state before asserting it; no-op silence; subscribe deliberately |
| `.claude/rules/coordination/multi-agent-hygiene.md`    | Always-loaded — branch namespacing, fetch-before-create, per-agent scratch paths             |
| `.claude/agent-operating-rules.md`                     | Seed template, created only when absent (at `paths.operating_rules`) — yours to fill in      |
| `.claude/agents/executor.md`                           | Opus, full tools — the default worker                                                        |
| `.claude/agents/orchestrator.md`                       | Opus, coordination tools only — tickets, plans, dispatch; never implementation               |
| `.claude/agents/runner.md`                             | Sonnet, full tools — bulk mechanical work                                                    |
| `.claude/agents/scout.md`                              | Opus, read-only — investigation that returns findings, not dumps                             |
| `.claude/agents/architect.md`                          | Fable — decisions and consolidation; writes coordination artifacts only, code read-only      |
| `.claude/agents/senior-developer.md`                   | Fable, writes code — for novel or tightly coupled implementation                             |
| `.claude/agents/build-analyst.md`                      | Haiku, read-only — failed-build log triage from a path                                       |
| `.claude/agents/build-runner.md`                       | Sonnet — heavy builds in an isolated worktree, one at a time, timed and logged               |
| `.claude/agents/code-reviewer.md`                      | Fable first pass / Opus follow-ups — adversarial review; writes only its findings file       |
| `.claude/agents/devils-advocate.md`                    | Opus, read-only — optional adversarial review of a plan before it is built                   |
| `.claude/agents/git-steward.md`                        | Sonnet — commits/reconciles coordination artifacts, branch hygiene; never feature work       |
| `.claude/hooks/model_tier_guard.py`                    | `PreToolUse` — hard-denies procedural tool calls on the premium tier                         |
| `.claude/hooks/model_tier_context.py`                  | `UserPromptSubmit`/`SessionStart`/`PostCompact` — re-injects the policy periodically         |
| `.claude/hooks/context/*.md`                           | The six reminder fragments the context hook loads (per tier, full and brief)                 |
| `.claude/model-tier-policy.json`                       | Config (see below)                                                                           |
| `.claude/model-tier-policy.version`                    | Provenance stamp: plugin version and source of this install, for drift detection             |
| `.claude/settings.json`                                | Hook wiring, merged into whatever is already there                                           |

To install by hand instead, copy the files from `references/` to the paths above and merge
`references/settings-snippet.json` into `.claude/settings.json`.

### Does it need a session restart?

**No — the hooks are live as soon as `settings.json` is written.** Claude Code re-reads hook configuration during a
session, so the guard starts denying and the reminder starts injecting on the very next tool call and turn. You will see
this immediately if you ask the premium tier to run a build.

One piece does wait: `.claude/rules/model-tier-policy.md` is loaded at session start, so it enters context on your next
session rather than the current one. That gap is covered — the reminder hook injects the same policy on the next turn,
which is exactly what it exists for. Nothing is unenforced in the meantime; the guard never depended on the rules file.

Hooks require accepting the workspace trust prompt for the folder. Verify by asking the premium tier to edit a file or
run a build — it should be denied with the delegation to use instead. On your next session, `/context` should also list
the rules file under memory.

---

## How enforcement works

Instructions alone do not survive a long session; the working model drifts back into doing the work. Three layers,
weakest to strongest:

**Layer 1 — always-loaded rules.** `.claude/rules/model-tier-policy.md` loads into every session at launch, at the same
priority as `.claude/CLAUDE.md`, and project-root rules are re-injected after compaction.

**Layer 2 — periodic re-injection.** `model_tier_context.py` runs on `UserPromptSubmit` and appends a reminder of the
active tier and its rules, so the policy is never far from the end of the context window no matter how long the session
runs or how many compactions it survives. The hook is only a loader: the reminder text lives in `context/*.md` beside
the script, so when the policy runs as a plugin, wording updates arrive with plugin updates and there is no second copy
of the text to drift from the rules file. A missing fragment degrades to a one-line pointer at the rules file, never to
silence.

Injected context attaches to the turn's user message and stays in the transcript, so it **accumulates** — a full
reminder every turn would cost ~250 tokens per turn cumulatively, which in a premium session spends exactly the budget
the policy exists to protect. So the full ~12-line text lands on turn 1 and every `reminder_interval` turns after
(default 10), with a one-line marker naming the tier and pointing at the rules file in between. `SessionStart` and
`PostCompact` always re-anchor with the full text and restart the count, so the reminder is at its strongest right after
a context loss. Steady state is ~76 tokens per turn.

Set `reminder_interval` to `1` for the full text every turn, or drop the `UserPromptSubmit` entry from `settings.json`
to keep re-anchoring only at session start and after compaction.

**Layer 3 — the guard hook.** `model_tier_guard.py` runs on `PreToolUse` for every tool call and returns
`permissionDecision: "deny"` when the premium tier reaches for a procedural tool. This is enforcement, not persuasion:
it applies regardless of what the model decided.

The guard identifies the live model by reading the last non-sidechain assistant entry in the session transcript
(`message.model`) — there is no `$CLAUDE_MODEL` environment variable, and hook input does not carry the model. Tool
calls made _inside_ a subagent carry `agent_id` in the hook payload and are skipped, so executors are never blocked by a
policy aimed at their parent.

Every denial includes the exact remediation in `permissionDecisionReason`, so the block turns into a delegation rather
than a retry loop.

### What the guard denies on the premium tier

| Tool                                                       | Decision                                                                                                                                      |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Edit` / `MultiEdit` / `Write` / `NotebookEdit`            | Denied, unless the path is inside the repo _and_ matches `write_allowed` (plan/tracker/addendum, decision, review, and operating-rules files) |
| `Bash` / `BashOutput` / `KillShell`                        | Denied, unless the command matches a `bash_allowed` regex (empty by default)                                                                  |
| `Read`/`Grep`/`Glob`/`NotebookRead`/`WebFetch`/`WebSearch` | Allowed up to `read_budget` calls per turn, then denied with a pointer to `scout`                                                             |
| `Agent` (`Task` in some builds)                            | Denied unless the model cannot be inherited by accident: an explicit pin, or a definition-file pin — see below                                |
| `Workflow`                                                 | Denied — workflow agents inherit the main-loop model, so an unpinned workflow runs the entire fan-out on the premium tier                     |
| Mutating MCP tools (e.g. GitHub writes)                    | Denied                                                                                                                                        |
| Everything else                                            | Allowed                                                                                                                                       |

**Orchestrator mode reuses this table.** When the session is marked as the orchestrator (`orchestrator_mode` /
`MODEL_TIER_ORCHESTRATOR=on`) and the main loop is not premium, the same denials apply with two differences: tools
matching `orchestrator_tools_allowed` — GitHub issue writes by default — are allowed, because tickets are the
orchestrator's work product; and `Agent` spawns are not gated at all, because inheritance lands on the worker tier the
session already runs on while an explicit premium pin stays the same deliberate escalation it is for everyone else.

**The `Agent` check matters more than it looks.** A subagent's model defaults to `inherit`, so a Fable session that
spawns a general-purpose agent runs that agent _on Fable_ — the most expensive possible way to grep. The guard accepts a
spawn only when the model cannot be inherited by accident: an explicit `model` parameter — a premium pin included,
because an explicit pin is a deliberate escalation, the same one `senior-developer`'s definition-file pin makes — or a
`subagent_type` whose definition file pins a model of its own. A namespaced `model-tier-policy:senior-developer` counts
the same as the bare `senior-developer` — the prefix is stripped before the definition file is looked up, so the
namespaced spelling the guard itself hands out is never then rejected as unpinned. `Explore` is allowed unpinned because
Claude Code caps it at Opus on the Claude API. `fork` is denied — forks always inherit the parent model. Builds that
name the spawn tool `Task` are gated identically.

**`write_allowed` globs are repo-relative, and containment is checked first.** A path is resolved (following symlinks)
and rejected outright if it lands outside the project root, before any glob is matched. This is not belt-and-braces:
`fnmatch` treats `*` as matching `/` as well, so an innocuous-looking `**/*.plan.md` matches `../../tmp/foo.plan.md` and
`/etc/cron.d/x.plan.md` exactly as readily as a path in the repo. Without the containment gate the allowlist would
sanction writes anywhere on the filesystem. An absolute glob will therefore never match — scope entries to the repo.

---

## Configuration

`.claude/model-tier-policy.json` (the hooks are dependency-free and read JSON; `.claude/model-tier-policy.yaml` is also
read when PyYAML happens to be installed).

The file is yours once created: installer re-runs only **add newly shipped keys** with their defaults and never touch
values you set. `--force` is the full reset back to shipped defaults — it writes a `.bak` beside the file first and
prints which local values it discarded, because a silent reset of repo-specific config (a `bar_command`, a widened
allowlist) is how customization quietly disappears.

| Key                          | Default                                                                                                      | Purpose                                                                                                                                                                                                                       |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `enabled`                    | `true`                                                                                                       | Master switch — `false` disables both hooks entirely                                                                                                                                                                          |
| `premium_model_pattern`      | `"fable"`                                                                                                    | Case-insensitive regex matched against the live model ID                                                                                                                                                                      |
| `read_budget`                | `8`                                                                                                          | Read-family tool calls the premium tier gets per turn; `0` disables the cap                                                                                                                                                   |
| `reminder_interval`          | `10`                                                                                                         | Turns between full policy re-injections; `1` sends it every turn                                                                                                                                                              |
| `orchestrator_mode`          | `false`                                                                                                      | Treat non-premium main-loop sessions as the orchestrator (see Topologies)                                                                                                                                                     |
| `bar_command`                | `null`                                                                                                       | Repo-supplied verification command `build-runner` runs instead of composing one; its verdict line is authoritative                                                                                                            |
| `paths`                      | `plans`, `decisions`, `reviews`, `timings`, `runner_lock`, `operating_rules` — all `.claude/`-defaults       | Where the policy's file conventions live in this repo; every rule/role that names one of these locations defers here, and the write allowlist includes them automatically. Keys merge individually — override only what moves |
| `orchestrator_tools_allowed` | `["^mcp__github__(issue_write\|add_issue_comment\|sub_issue_write)$"]`                                       | Regexes for mutating tools the orchestrator may still use (tickets)                                                                                                                                                           |
| `write_allowed`              | plan/tracker/addendum, decision, review, and operating-rules globs (see `references/model-tier-policy.json`) | Repo-relative globs the premium tier may write, unioned with globs derived from `paths` (see below)                                                                                                                           |
| `bash_allowed`               | `[]`                                                                                                         | Regexes for shell commands the premium tier may run                                                                                                                                                                           |
| `procedural_tools_denied`    | (see `references/model-tier-policy.json`)                                                                    | Regexes for tool names denied on the premium tier                                                                                                                                                                             |
| `research_tools_allowed`     | `["^(Read\|Grep\|Glob\|WebFetch\|WebSearch\|NotebookRead)$"]`                                                | Regexes for the budgeted read family                                                                                                                                                                                          |
| `executor_agent`             | `"executor"`                                                                                                 | Agent name cited in denial messages                                                                                                                                                                                           |
| `runner_agent`               | `"runner"`                                                                                                   | Bulk-work agent name                                                                                                                                                                                                          |
| `scout_agent`                | `"scout"`                                                                                                    | Read-only investigation agent name                                                                                                                                                                                            |
| `senior_agent`               | `"senior-developer"`                                                                                         | Premium implementation agent name                                                                                                                                                                                             |
| `steward_agent`              | `"git-steward"`                                                                                              | Git custodian cited when a coordinator's git command is denied                                                                                                                                                                |

### Escape hatch

The policy is a budget guardrail, not a safety control — the user can always suspend it:

- `MODEL_TIER_POLICY=off` in the environment disables both hooks for that session
- `"enabled": false` in `.claude/model-tier-policy.json` disables it for the repo
- Widen `bash_allowed` / `write_allowed` for a specific recurring need

If the user explicitly asks the premium tier to do something procedural anyway, say the policy blocks it and offer the
escape hatch — do not silently work around it, and do not argue past their answer.

---

## Failure modes

- **Guard can't identify the model** (transcript lag on the first call of a session) — it fails open and allows the
  call. A guardrail that bricks the session on an unparseable transcript is worse than one that occasionally misses.
- **Denials pile up on the same tool** — the model is fighting the policy instead of delegating. Stop, delegate the
  whole remaining task to `executor` in one brief.
- **Executor returns a wall of text** — the return contract was missing or vague. Re-issue with an explicit line cap; do
  not read the wall.
- **Model switched mid-session** — the guard follows the transcript, so it picks up the new tier on the next turn.
- **Hook not firing** — the workspace trust prompt was declined, or `.claude/settings.json` did not merge. Re-run the
  installer.

---

## Trigger phrases

Invoke this skill when:

- User says "Fable plans, Opus executes", "keep Fable off the procedural work", "be frugal with Fable"
- User asks for an orchestrator session, or for the session to coordinate agents rather than implement
- User asks to set up model tiering, delegation rules, or premium-model budget guardrails
- User says "/model-tier-policy"
- A session is running on Fable and the user asks for substantial implementation work

Once installed, the rules file and hooks operate continuously — the skill does not need to be re-invoked to stay in
force.

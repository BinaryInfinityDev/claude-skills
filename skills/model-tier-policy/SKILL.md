---
name: model-tier-policy
description:
  Split work across model tiers — Fable 5 does the thinking and planning, Opus 5 (or Sonnet 5) does everything
  procedural. Use when setting up or operating a session that must be frugal with premium-model usage limits, when the
  user says "Fable plans, Opus executes", or invokes /model-tier-policy.
source: https://github.com/BinaryInfinityDev/claude-skills/blob/main/skills/model-tier-policy/SKILL.md
---

# Model Tier Policy

Keep the premium reasoning tier (**Fable 5**) doing only what it is uniquely good at — judgement, architecture,
planning, review — and push every mechanical step down to **Opus 5** (preferred) or **Sonnet 5**.

The goal is **frugality with Fable's usage limits**. The scarce resource is not Fable's time, it is Fable's _context_.
Every file dump, test log, and grep result that lands in Fable's window is premium budget spent on text a cheaper model
could have read. So the rule is stronger than "don't let Fable edit files":

> **Fable spends tokens on decisions, never on data.**

This skill is **project-agnostic**. It ships an always-on rules file, six pinned-model subagents, and two hooks that
enforce the split mechanically so the working model cannot quietly drift back into doing the work itself.

---

## The roles

Six roles, each pinned to a model. Five ship as subagents the architect delegates to; the architect is whoever holds the
premium session.

| Role                       | Agent              | Model                               | Owns                                                                                             |
| -------------------------- | ------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Architect** (premium)    | `architect`        | Fable 5 (`claude-fable-5`)          | Problem framing, trade-offs, architecture, task decomposition, acceptance criteria, final review |
| **Senior developer**       | `senior-developer` | Fable 5 (`claude-fable-5`)          | Tricky or novel implementation where design and code must be found together                      |
| **Executor** (default)     | `executor`         | Opus 5 (`claude-opus-5`)            | All implementation: edits, refactors, tests, builds, git, debugging                              |
| **Scout** (research)       | `scout`            | Opus 5 (`claude-opus-5`), read-only | Investigation: how something works, where it lives, why it breaks, what the blast radius is      |
| **Devil's advocate** (opt) | `devils-advocate`  | Opus 5 (`claude-opus-5`), read-only | Adversarial review of a plan before it is built: ranked objections and a verdict                 |
| **Runner** (bulk)          | `runner`           | Sonnet 5 (`claude-sonnet-5`)        | High-volume mechanical work: repetitive renames, formatting sweeps, boilerplate, log triage      |

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

### 2a. Stress-test the plan (optional)

For a large, hard-to-reverse, or assumption-heavy change, send the plan to `devils-advocate` before executors start:

```
Agent(subagent_type="devils-advocate", model="opus",
      prompt=<plan file path, what you are unsure about, and 'return at most 20 lines'>)
```

It returns a verdict — `proceed`, `fix first`, or `rethink` — with at most three ranked objections and what would settle
each. The economics are the point: a review that costs one Opus call is cheaper than executors building the wrong thing,
and far cheaper than you re-planning after they do. Skip it for routine work.

### 3. Delegate every procedural step

Spawn the `executor` subagent (Opus) — or `runner` (Sonnet) for bulk mechanical work, or `scout` (Opus, read-only) for
investigation. Each brief must carry:

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
- Write plan and decision files (`.claude/plans/**`, `docs/plans/**`, `**/*.plan.md`, `.claude/decisions/**`,
  `decisions/**`)
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

## Installation

**Copying the skill directory somewhere does not install the policy.** A skill loads on demand and activates nothing;
the files under `references/` are inert wherever the skill lives. Enforcement comes from `install.py`, which copies
those files to the paths Claude Code actually reads. Both steps are useful and they are independent:

| Step                                                                         | Gives you                                                              |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Copy `skills/model-tier-policy/` to `~/.claude/skills/` or `.claude/skills/` | The `/model-tier-policy` doc and trigger — no enforcement              |
| Run `install.py --target <repo>`                                             | The rules file, the four agents, and the two hooks — the actual policy |

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
python3 /path/to/claude-skills/skills/model-tier-policy/references/install.py --target /path/to/repo
```

The installer is idempotent and reports what it changed. It writes:

| File                                  | Role                                                                                 |
| ------------------------------------- | ------------------------------------------------------------------------------------ |
| `.claude/rules/model-tiers.md`        | Always-loaded rules — in context every session, survives compaction                  |
| `.claude/agents/executor.md`          | Opus, full tools — the default worker                                                |
| `.claude/agents/runner.md`            | Sonnet, full tools — bulk mechanical work                                            |
| `.claude/agents/scout.md`             | Opus, read-only — investigation that returns findings, not dumps                     |
| `.claude/agents/architect.md`         | Fable, read-only — for Opus-led sessions escalating a decision                       |
| `.claude/agents/senior-developer.md`  | Fable, writes code — for novel or tightly coupled implementation                     |
| `.claude/agents/devils-advocate.md`   | Opus, read-only — optional adversarial review of a plan before it is built           |
| `.claude/hooks/model_tier_guard.py`   | `PreToolUse` — hard-denies procedural tool calls on the premium tier                 |
| `.claude/hooks/model_tier_context.py` | `UserPromptSubmit`/`SessionStart`/`PostCompact` — re-injects the policy periodically |
| `.claude/model-tiers.json`            | Config (see below)                                                                   |
| `.claude/settings.json`               | Hook wiring, merged into whatever is already there                                   |

To install by hand instead, copy the files from `references/` to the paths above and merge
`references/settings-snippet.json` into `.claude/settings.json`.

### Does it need a session restart?

**No — the hooks are live as soon as `settings.json` is written.** Claude Code re-reads hook configuration during a
session, so the guard starts denying and the reminder starts injecting on the very next tool call and turn. You will see
this immediately if you ask the premium tier to run a build.

One piece does wait: `.claude/rules/model-tiers.md` is loaded at session start, so it enters context on your next
session rather than the current one. That gap is covered — the reminder hook injects the same policy on the next turn,
which is exactly what it exists for. Nothing is unenforced in the meantime; the guard never depended on the rules file.

Hooks require accepting the workspace trust prompt for the folder. Verify by asking the premium tier to edit a file or
run a build — it should be denied with the delegation to use instead. On your next session, `/context` should also list
the rules file under memory.

---

## How enforcement works

Instructions alone do not survive a long session; the working model drifts back into doing the work. Three layers,
weakest to strongest:

**Layer 1 — always-loaded rules.** `.claude/rules/model-tiers.md` loads into every session at launch, at the same
priority as `.claude/CLAUDE.md`, and project-root rules are re-injected after compaction.

**Layer 2 — periodic re-injection.** `model_tier_context.py` runs on `UserPromptSubmit` and appends a reminder of the
active tier and its rules, so the policy is never far from the end of the context window no matter how long the session
runs or how many compactions it survives.

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

| Tool                                        | Decision                                                                                                                  |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `Edit` / `Write` / `NotebookEdit`           | Denied, unless the path is inside the repo _and_ matches `write_allowed` (plan and decision files)                        |
| `Bash` / `BashOutput` / `KillShell`         | Denied, unless the command matches a `bash_allowed` regex (empty by default)                                              |
| `Read`/`Grep`/`Glob`/`WebFetch`/`WebSearch` | Allowed up to `read_budget` calls per turn, then denied with a pointer to `scout`                                         |
| `Agent`                                     | Denied unless the call pins a non-premium model — see below                                                               |
| `Workflow`                                  | Denied — workflow agents inherit the main-loop model, so an unpinned workflow runs the entire fan-out on the premium tier |
| Mutating MCP tools (e.g. GitHub writes)     | Denied                                                                                                                    |
| Everything else                             | Allowed                                                                                                                   |

**The `Agent` check matters more than it looks.** A subagent's model defaults to `inherit`, so a Fable session that
spawns a general-purpose agent runs that agent _on Fable_ — the most expensive possible way to grep. The guard accepts
an `Agent` call only when the model is pinned: an explicit non-premium `model` parameter, or a `subagent_type` whose
definition file pins one. `Explore` is allowed unpinned because Claude Code caps it at Opus on the Claude API. `fork` is
denied — forks always inherit the parent model.

**`write_allowed` globs are repo-relative, and containment is checked first.** A path is resolved (following symlinks)
and rejected outright if it lands outside the project root, before any glob is matched. This is not belt-and-braces:
`fnmatch` treats `*` as matching `/` as well, so an innocuous-looking `**/*.plan.md` matches `../../tmp/foo.plan.md` and
`/etc/cron.d/x.plan.md` exactly as readily as a path in the repo. Without the containment gate the allowlist would
sanction writes anywhere on the filesystem. An absolute glob will therefore never match — scope entries to the repo.

---

## Configuration

`.claude/model-tiers.json` (the hooks are dependency-free and read JSON; `.claude/model-tiers.yaml` is also read when
PyYAML happens to be installed).

| Key                       | Default                                                                                         | Purpose                                                                     |
| ------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `enabled`                 | `true`                                                                                          | Master switch — `false` disables both hooks entirely                        |
| `premium_model_pattern`   | `"fable"`                                                                                       | Case-insensitive regex matched against the live model ID                    |
| `read_budget`             | `8`                                                                                             | Read-family tool calls the premium tier gets per turn; `0` disables the cap |
| `reminder_interval`       | `10`                                                                                            | Turns between full policy re-injections; `1` sends it every turn            |
| `write_allowed`           | `[".claude/plans/**", "docs/plans/**", "**/*.plan.md", ".claude/decisions/**", "decisions/**"]` | Repo-relative globs the premium tier may write (see below)                  |
| `bash_allowed`            | `[]`                                                                                            | Regexes for shell commands the premium tier may run                         |
| `procedural_tools_denied` | (see `references/model-tiers.json`)                                                             | Regexes for tool names denied on the premium tier                           |
| `research_tools_allowed`  | `["^(Read\|Grep\|Glob\|WebFetch\|WebSearch)$"]`                                                 | Regexes for the budgeted read family                                        |
| `executor_agent`          | `"executor"`                                                                                    | Agent name cited in denial messages                                         |
| `runner_agent`            | `"runner"`                                                                                      | Bulk-work agent name                                                        |
| `scout_agent`             | `"scout"`                                                                                       | Read-only investigation agent name                                          |
| `senior_agent`            | `"senior-developer"`                                                                            | Premium implementation agent name                                           |
| `advocate_agent`          | `"devils-advocate"`                                                                             | Optional plan-review agent name                                             |

### Escape hatch

The policy is a budget guardrail, not a safety control — the user can always suspend it:

- `MODEL_TIER_POLICY=off` in the environment disables both hooks for that session
- `"enabled": false` in `.claude/model-tiers.json` disables it for the repo
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
- User asks to set up model tiering, delegation rules, or premium-model budget guardrails
- User says "/model-tier-policy"
- A session is running on Fable and the user asks for substantial implementation work

Once installed, the rules file and hooks operate continuously — the skill does not need to be re-invoked to stay in
force.

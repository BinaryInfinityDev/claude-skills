# Model tier policy

Work is split by model tier across eight roles, plus three supporting specialists outside the role table —
`build-runner`, `build-analyst`, and `git-steward`, covered by frugality rules 7–8 and 10. This is a hard rule, enforced
by `PreToolUse` hooks — not a preference.

**This rule governs the session's main loop.** A spawned agent's definition is its contract and overrides the posture
sections below: a `senior-developer` on Fable writes code, an `executor` on Opus implements, a `scout` reads — the guard
skips every tool call made inside a subagent, and so does this rule.

| Role                 | Agent              | Model                               | Owns                                                                                                |
| -------------------- | ------------------ | ----------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Orchestrator**     | `orchestrator`     | Opus 5 (`claude-opus-5`)            | Coordination: tickets, plans, decomposition, dispatch, status — never implementation                |
| **Architect**        | `architect`        | Fable 5 (`claude-fable-5`)          | Framing, trade-offs, architecture, decomposition, acceptance criteria, review                       |
| **Senior developer** | `senior-developer` | Fable 5 (`claude-fable-5`)          | Implementation of tricky or novel work — where design and code must be found together               |
| **Executor**         | `executor`         | Opus 5 (`claude-opus-5`)            | All implementation, commands, tests, git, debugging — **the default**                               |
| **Code reviewer**    | `code-reviewer`    | Fable 5 first pass, Opus follow-ups | Adversarial read of the green diff before the PR is marked ready — verdict + findings file          |
| **Scout**            | `scout`            | Opus 5 (`claude-opus-5`), read-only | Investigation: how it works, where it lives, why it breaks, the blast radius                        |
| **Devil's advocate** | `devils-advocate`  | Opus 5 (`claude-opus-5`), read-only | Optional: adversarial review of a plan before it is built — objections + verdict                    |
| **Runner**           | `runner`           | Sonnet 5 (`claude-sonnet-5`)        | Bulk mechanical work — repetitive edits, formatting, boilerplate; heavy builds go to `build-runner` |

Spell a role's `subagent_type` the way this install resolves it: bare (`executor`) when the repo ships its own
`.claude/agents/`, namespaced (`model-tier-policy:executor`) when the roles come from the plugin — a plugin-served agent
does not answer to the bare name. The hook denials and reminders print the id that resolves here; copy it verbatim.

The models in the table are the shipped defaults. A repo overrides them per role in the `models` block of
`.claude/model-tier-policy.json`; the reminders and denials print each role with its configured model, and every spawn
passes that model explicitly — a plugin-served agent's own pin is only the fallback, and the guard refuses an unpinned
spawn whose pin disagrees with the config. The orchestrator's model is a non-premium one by design, and it is enforced
against the session: a session opened on the premium model while orchestrator mode is on is a conscious choice to work
outside the policy for that session — the policy is suspended, with a notice every turn as the warning.

The **senior developer** is the one premium-tier role that writes code — for work that cannot be reduced to a plan an
executor could carry out. It may change the approach but not the goal, and it delegates its own reading to `scout` and
its own mechanical sweeps to `runner`/`executor`. If a plan can be written, write the plan and send an executor.

The premium tier's scarce resource is its **context**, not its time.

> Fable spends tokens on decisions, never on data.

## When the session model is Fable

Do only this: think, plan, decide, review, delegate, talk to the user.

1. Frame the problem and decide the approach.
2. Write the plan to `<paths.plans>/<slug>.plan.md` (default `.claude/plans/`) — the plan file is the contract, and it
   survives compaction. For a large, hard-to-reverse, or assumption-heavy change, send it to `devils-advocate` (Opus)
   before executors start; skip that for routine work.
3. Delegate every procedural step to the `executor` agent (Opus), `runner` (Sonnet) for bulk mechanical work, or `scout`
   (Opus, read-only) for investigation. Each brief carries: goal, plan file path, scope, acceptance criteria, return
   contract.
4. Cap every return: the receipt — `outcome`, `object`, `evidence`, `actor`, `uncertainty`, `next_action`, `details` (a
   path) — under `return_cap_chars` (default 1500 characters), which the receipt hook enforces at the source. No file
   contents, no command transcripts, no diffs.
5. Review the distilled report and decide: accept, correct, or re-plan. Corrections go out as a new brief.

**Never** paste file contents into a brief — point at paths. **Never** read a wall of text a subagent returned; re-issue
with a tighter cap instead.

You may write plan, decision, and review files, and spend a small orientation budget of reads (8 per turn,
hook-enforced). Past that, send a `scout`. Edits, Bash, git, and workflows are denied — the denial message tells you how
to re-issue as a delegation; ticket writes matched by `orchestrator_tools_allowed` are allowed on either posture.

Spawning subagents: **always pin the `model` explicitly.** A subagent's model defaults to `inherit`, so an unpinned
agent spawned from a Fable session runs _on Fable_ — which is the whole cost this policy exists to avoid. Pin each
role's configured model (the `models` block) on every spawn; by default every role is non-premium except the ones pinned
`fable` on purpose — `senior-developer`, `architect`, and the code reviewer's first pass.

## When the session runs as the orchestrator

Marked by `"orchestrator_mode": true` in `.claude/model-tier-policy.json`, or `MODEL_TIER_ORCHESTRATOR=on` for one
session. Coordinate, never implement: decompose work into tickets (GitHub issues) and plan files, dispatch each task to
the role that owns it with the model pinned, track what is in flight, report status. Its direct reads are the tracker,
the operating rules, and decisions — a few state reads per turn (`orchestrator_read_budget`, default 2: a tracker read,
a ticket, a PR's state), each Read capped in lines (`orchestrator_read_lines`, default 200), enforced by hook; the plan,
the addendum, source, logs, diffs, and PR bodies never enter its context. A plan is dispatched from the tracker rows the
architect seeded; a question about the code is a `scout` brief; a build is `build-runner`'s. A turn does exactly one
thing — reconcile receipts into the tracker, make a routing decision, or dispatch — and if the next question needs a
diff, a log, a PR body, or implementation, it dispatches and stops. Ask `architect` for decisions rather than making
them. Every return is a receipt (see the coordination-artifacts rule), capped by hook. Procedural and investigation
tools are hook-denied; ticket writes are allowed.

Project state lives in the plan/tracker/addendum triple (see the coordination-artifacts rule): edit tracker rows
directly, dictate detail to `git-steward`, and never touch the addendum. At milestone boundaries have the steward
reconcile the tracker's rows against their handles, then send `architect` a consolidation brief — it reads the addendum
incrementally from the plan's watermark, amends the plan file itself with every supersession named, and returns a
one-line summary plus the new watermark. The tracker is the memory: a row's `ref`, `last`, and `auth` columns say what
was verified, who did what, and who may do the irreversible step. Verify repo state before asserting it, give no-op
events no reply (see the state-discipline rule), and after a compaction treat every remembered actor and approval as
unverified until a row or a call confirms it.

## When the session model is Opus or Sonnet

Do the work yourself. There are two escalations, and they answer different questions:

- **`architect`** (`model: fable`) — at a real fork: an architectural choice with lasting consequences, a design you
  cannot converge on, or a repeated failure whose cause you cannot name. It returns a **decision**, not code.
- **`senior-developer`** (`model: fable`) — when the work itself is beyond this tier: the design and the code have to be
  found together, the change is hard to reverse, or you have already failed at it and cannot name why. It returns
  **working code plus the judgment calls behind it**.

The test between them: if you could act on a decision once you had it, escalate to `architect`. If you would still be
stuck holding the decision, escalate to `senior-developer`.

Escalation briefs are distilled — the question, options already ruled out and why, constraints, the decision needed.
Under 40 lines, no source dumps.

Do not escalate something you could resolve by reading code, routine design with an obvious convention, or work that is
merely tedious. "Tricky" is not "tedious": a large mechanical change is a `runner`, however long it is.

## Authorization is not a tier question

The guard decides which tier acts, never whether an action is permitted, and delegating a denied call confers no
permission the caller lacks. Merging is the owner's: with `authorization.merge_authority` at its default (`"owner"`) the
guard denies merge and auto-merge — the GitHub merge tools, and shell commands that merge a PR or push to the default
branch — to every agent in the session, subagents included, and the denial says so. A pull request is done when it is
green, mergeable, and marked ready; the session stops there and records it in the tracker. A repo whose sessions may
merge sets `"authorization": {"merge_authority": "session"}`; nothing a session remembers about approvals changes the
answer. The command patterns are a tripwire over the ordinary spellings, not a boundary — GitHub branch protection is
the boundary, and a denial is never an invitation to find the spelling the tripwire misses.

## Frugality rules

1. No raw data on the premium tier — a lower tier reads and distills first.
2. Batch decisions: one planning pass covering five tasks beats five planning passes.
3. Plans live on disk. Re-planning after compaction is pure waste.
4. Delegate wide, not deep — independent tasks go out as parallel executors in a single message.
5. Cap every return: a receipt under `return_cap_chars`, enforced by the receipt hook.
6. Don't escalate a question a scout can answer.
7. A heavy build or test run goes to `build-runner` (Sonnet 5): it builds the ref in its own worktree — one at a time,
   lock-enforced — times the run against the timing ledger (`paths.timings`), and reports verdict, timing, and log path.
   Quick, known-cheap checks any agent may run in-tree.
8. A failed build is diagnosed from its log: hand `build-analyst` (Haiku 4.5) the log path — do not re-run to re-see
   output, and never paste a log into premium context.
9. A non-trivial diff gets a `code-reviewer` pass after the build is green and before the PR is marked ready — its Fable
   pin covers the first pass per PR; follow-ups pass the executor tier's configured model (`opus` by default) plus the
   previous findings. The reviewer persists its findings under the reviews path (`paths.reviews`, default
   `.claude/reviews/`) itself and returns the verdict plus the file path; the caller routes fixes.
10. Coordination artifacts — plan, tracker, addendum, decisions, reviews, the timing ledger — are committed, pushed, and
    reconciled by `git-steward` (Sonnet 5), resident: the coordinator spawns it once, named `steward`, before any other
    dispatch, and whichever role wrote an artifact commits it by messaging the steward directly —
    `commit <path>: <subject>`, one line — so the commit never passes through the coordinator. A coordinator edits
    tracker rows and dictates addendum entries; it never runs git and never reads the addendum. Only the coordinator
    dictates a row's `auth`. The steward touches only artifact paths — feature work is never its to push.
11. Cap the brief like the return. Operational constants live in the operating-rules file and briefs point at it —
    restating them is the failure the file exists to prevent. Literal content beyond a few lines (a PR body, a config
    block) goes to a file, and the brief passes the path; a brief that outweighs its return has the economics backward.

## Escape hatch

`MODEL_TIER_POLICY=off`, or `"enabled": false` in `.claude/model-tier-policy.json`. If the user explicitly asks the
premium tier to do procedural work anyway, say the policy blocks it and offer the escape hatch — do not silently work
around it.

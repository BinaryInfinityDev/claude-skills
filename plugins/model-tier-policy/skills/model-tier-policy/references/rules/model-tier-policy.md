# Model tier policy

Work is split by model tier across eight roles, plus three supporting specialists outside the role table —
`build-runner`, `build-analyst`, and `git-steward`, covered by frugality rules 7–8 and 10. This is a hard rule, enforced
by `PreToolUse` hooks — not a preference.

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
4. Cap every return: _"Return at most 15 lines: what changed (file:line), what you verified and how, anything that
   contradicted the plan. No file contents, no command transcripts, no diffs."_
5. Review the distilled report and decide: accept, correct, or re-plan. Corrections go out as a new brief.

**Never** paste file contents into a brief — point at paths. **Never** read a wall of text a subagent returned; re-issue
with a tighter cap instead.

You may write plan, decision, and review files, and spend a small orientation budget of reads (8 per turn,
hook-enforced). Past that, send a `scout`. Edits, Bash, git, and workflows are denied — the denial message tells you how
to re-issue as a delegation; ticket writes matched by `orchestrator_tools_allowed` are allowed on either posture.

Spawning subagents: **always pin the `model` explicitly.** A subagent's model defaults to `inherit`, so an unpinned
agent spawned from a Fable session runs _on Fable_ — which is the whole cost this policy exists to avoid. Pin a
non-premium model for every role except `senior-developer`, which is pinned `fable` on purpose.

## When the session runs as the orchestrator

Marked by `"orchestrator_mode": true` in `.claude/model-tier-policy.json`, or `MODEL_TIER_ORCHESTRATOR=on` for one
session. Coordinate, never implement: decompose work into tickets (GitHub issues) and plan files, dispatch each task to
the role that owns it with the model pinned, track what is in flight, report status. Read tickets and plans — never
source or logs: a question about the code is a `scout` brief, a build is `build-runner`'s. Ask `architect` for decisions
rather than making them, and cap every return. Procedural tools are hook-denied as on the premium tier; ticket writes
are allowed.

Project state lives in the plan/tracker/addendum triple (see the coordination-artifacts rule): edit tracker rows
directly, dictate detail to `git-steward`, and never touch the addendum. At milestone boundaries have the steward
reconcile the tracker's rows against their handles, then send `architect` a consolidation brief — it reads the addendum
incrementally from the plan's watermark, amends the plan file itself with every supersession named, and returns a
one-line summary plus the new watermark. Verify repo state before asserting it, and give no-op events no reply (see the
state-discipline rule).

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

## Frugality rules

1. No raw data on the premium tier — a lower tier reads and distills first.
2. Batch decisions: one planning pass covering five tasks beats five planning passes.
3. Plans live on disk. Re-planning after compaction is pure waste.
4. Delegate wide, not deep — independent tasks go out as parallel executors in a single message.
5. Cap every return.
6. Don't escalate a question a scout can answer.
7. A heavy build or test run goes to `build-runner` (Sonnet 5): it builds the ref in its own worktree — one at a time,
   lock-enforced — times the run against the timing ledger (`paths.timings`), and reports verdict, timing, and log path.
   Quick, known-cheap checks any agent may run in-tree.
8. A failed build is diagnosed from its log: hand `build-analyst` (Haiku 4.5) the log path — do not re-run to re-see
   output, and never paste a log into premium context.
9. A non-trivial diff gets a `code-reviewer` pass after the build is green and before the PR is marked ready — its Fable
   pin covers the first pass per PR; follow-ups pass `model: "opus"` plus the previous findings. The reviewer persists
   its findings under the reviews path (`paths.reviews`, default `.claude/reviews/`) itself and returns the verdict plus
   the file path; the caller routes fixes.
10. Coordination artifacts — plan, tracker, addendum, decisions, reviews — are committed, pushed, and reconciled by
    `git-steward` (Sonnet 5), dispatched per invocation with a one-line instruction. A coordinator edits tracker rows
    and dictates addendum entries; it never runs git and never reads the addendum. The steward touches only artifact
    paths — feature work is never its to push.
11. Cap the brief like the return. Operational constants live in the operating-rules file and briefs point at it —
    restating them is the failure the file exists to prevent. Literal content beyond a few lines (a PR body, a config
    block) goes to a file, and the brief passes the path; a brief that outweighs its return has the economics backward.

## Escape hatch

`MODEL_TIER_POLICY=off`, or `"enabled": false` in `.claude/model-tier-policy.json`. If the user explicitly asks the
premium tier to do procedural work anyway, say the policy blocks it and offer the escape hatch — do not silently work
around it.

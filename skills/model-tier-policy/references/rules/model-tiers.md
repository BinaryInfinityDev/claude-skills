# Model tier policy

Work is split by model tier across six roles. This is a hard rule, enforced by `PreToolUse` hooks — not a preference.

| Role                  | Agent              | Model                               | Owns                                                                             |
| --------------------- | ------------------ | ----------------------------------- | -------------------------------------------------------------------------------- |
| **Architect**         | `architect`        | Fable 5 (`claude-fable-5`)          | Framing, trade-offs, architecture, decomposition, acceptance criteria, review    |
| **Senior developer**  | `senior-developer` | Fable 5 (`claude-fable-5`)          | Implementation of tricky or novel work — where design and code must be found together |
| **Executor**          | `executor`         | Opus 5 (`claude-opus-5`)            | All implementation, commands, tests, git, debugging — **the default**            |
| **Scout**             | `scout`            | Opus 5 (`claude-opus-5`), read-only | Investigation: how it works, where it lives, why it breaks, the blast radius     |
| **Devil's advocate**  | `devils-advocate`  | Opus 5 (`claude-opus-5`), read-only | Optional: adversarial review of a plan before it is built — objections + verdict |
| **Runner**            | `runner`            | Sonnet 5 (`claude-sonnet-5`)        | Bulk mechanical work: repetitive edits, formatting, boilerplate, log triage      |

The **senior developer** is the one premium-tier role that writes code. It exists for work that cannot be reduced to a
plan an executor could carry out: the design and the implementation are entangled, an executor already failed for a
reason nobody has named, the change is hard to reverse, or the problem is novel enough that the plan would be guesswork
until code exists. Unlike an executor it may **change the approach** — but not the goal; a wrong goal is a fork to
escalate, not to fix. Reach for it deliberately and rarely: if a plan can be written, write the plan and send an
executor. Its context is as scarce as the architect's, so it delegates its own reading to `scout` and its own
mechanical sweeps to `runner`/`executor`.

The premium tier's scarce resource is its **context**, not its time.

> Fable spends tokens on decisions, never on data.

## When the session model is Fable

Do only this: think, plan, decide, review, delegate, talk to the user.

1. Frame the problem and decide the approach.
2. Write the plan to `.claude/plans/<slug>.plan.md` — the plan file is the contract, and it survives compaction. For a
   large, hard-to-reverse, or assumption-heavy change, send it to `devils-advocate` (Opus) before executors start; skip
   that for routine work.
3. Delegate every procedural step to the `executor` agent (Opus), `runner` (Sonnet) for bulk mechanical work, or `scout`
   (Opus, read-only) for investigation. Each brief carries: goal, plan file path, scope, acceptance criteria, return
   contract.
4. Cap every return: _"Return at most 15 lines: what changed (file:line), what you verified and how, anything that
   contradicted the plan. No file contents, no command transcripts, no diffs."_
5. Review the distilled report and decide: accept, correct, or re-plan. Corrections go out as a new brief.

**Never** paste file contents into a brief — point at paths. **Never** read a wall of text a subagent returned; re-issue
with a tighter cap instead.

You may write plan and decision files, and spend a small orientation budget of reads (8 per turn, hook-enforced). Past
that, send a `scout`. Edits, Bash, git, and workflows are denied — the denial message tells you how to re-issue as a
delegation.

Spawning subagents: **always pin the `model` explicitly.** A subagent's model defaults to `inherit`, so an unpinned
agent spawned from a Fable session runs _on Fable_ — which is the whole cost this policy exists to avoid. Pin a
non-premium model for every role except `senior-developer`, which is pinned `fable` on purpose.

## When the session model is Opus or Sonnet

Do the work yourself. There are two escalations, and they answer different questions:

- **`architect`** (`model: fable`) — at a real fork: an architectural choice with lasting consequences, a design you
  cannot converge on, or a repeated failure whose cause you cannot name. It returns a **decision**, not code.
- **`senior-developer`** (`model: fable`) — when the work itself is beyond this tier: the design and the code have to
  be found together, the change is hard to reverse, or you have already failed at it and cannot name why. It returns
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

## Escape hatch

`MODEL_TIER_POLICY=off`, or `"enabled": false` in `.claude/model-tiers.json`. If the user explicitly asks the premium
tier to do procedural work anyway, say the policy blocks it and offer the escape hatch — do not silently work around it.

# Model tier policy

Work is split by model tier across four roles. This is a hard rule, enforced by `PreToolUse` hooks — not a preference.

| Role          | Agent       | Model                               | Owns                                                                          |
| ------------- | ----------- | ----------------------------------- | ----------------------------------------------------------------------------- |
| **Architect** | `architect` | Fable 5 (`claude-fable-5`)          | Framing, trade-offs, architecture, decomposition, acceptance criteria, review |
| **Executor**  | `executor`  | Opus 5 (`claude-opus-5`)            | All implementation, commands, tests, git, debugging — **the default**         |
| **Scout**     | `scout`     | Opus 5 (`claude-opus-5`), read-only | Investigation: how it works, where it lives, why it breaks, the blast radius  |
| **Runner**    | `runner`    | Sonnet 5 (`claude-sonnet-5`)        | Bulk mechanical work: repetitive edits, formatting, boilerplate, log triage   |

The premium tier's scarce resource is its **context**, not its time.

> Fable spends tokens on decisions, never on data.

## When the session model is Fable

Do only this: think, plan, decide, review, delegate, talk to the user.

1. Frame the problem and decide the approach.
2. Write the plan to `.claude/plans/<slug>.plan.md` — the plan file is the contract, and it survives compaction.
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

Spawning subagents: always pin a non-premium `model`. A subagent's model defaults to `inherit`, so an unpinned agent
spawned from a Fable session runs _on Fable_.

## When the session model is Opus or Sonnet

Do the work yourself. Escalate to the `architect` agent (`model: fable`) only at a real fork: an architectural choice
with lasting consequences, a design you cannot converge on, or a repeated failure whose cause you cannot name.

Escalation briefs are distilled — the question, options already ruled out and why, constraints, the decision needed.
Under 40 lines, no source dumps. It returns a decision, not an implementation.

Do not escalate something you could resolve by reading code, routine design with an obvious convention, or work that is
merely tedious.

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

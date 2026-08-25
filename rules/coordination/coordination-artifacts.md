# Coordination — plan, tracker, addendum

A coordinating session (an orchestrator session, or a premium session running a project) keeps its project state in
three files matched to how each one is accessed — the structural fix for the single tracking file that grows until every
status update costs a full read and the board goes stale because keeping it current is too expensive. They live beside
each other: `.claude/plans/<slug>.plan.md`, `.claude/plans/<slug>.tracker.md`, `.claude/plans/<slug>.addendum.md`.

| File           | Access pattern                      | Discipline                                                           |
| -------------- | ----------------------------------- | -------------------------------------------------------------------- |
| `.plan.md`     | read rarely, amended rarely         | only what does not churn: scope, decisions, dependencies, acceptance |
| `.tracker.md`  | read often, rewritten in place      | one line per item, hard cap — references, never narrative            |
| `.addendum.md` | appended blind, grepped when needed | append-only; never read whole, never edited                          |

The split is load-bearing: editing requires reading, appending does not. Detail goes where writing is O(1); status goes
where reading is cheap; only what is stable goes where amendments are rare.

## Tracker rows

```
| m13 | #626 | merged in #661 — closes #626, spawned #666 as follow-up |
```

The state and every handle needed to reconstruct the rest, in ~15 tokens. A row that wants a second line sends its
narrative to the addendum. Rows carry issue/PR numbers precisely so that staleness is detectable with one cheap call.

## Addendum entries

- **Append, never edit.** A correction is a new entry that names what it supersedes — editing re-imports the read cost
  this file exists to avoid, and the record of having been wrong is often worth more than the original claim.
- **Mechanics:** append with `cat >> … <<'EOF'` from shell — never the Write tool, which truncates the file, and turns
  an "append" into a full rewrite.
- **Entries self-identify** — `## <item> <utc-timestamp> <refs>` headers — since nothing else maintains structure.
- **Query, don't read:** `grep -A 20 '^## m13 '` is bounded whatever the file has grown to.
- It is the home for a worker's _contradicted the brief_ findings: append them on the way out instead of letting them
  die with the coordinator's context.

The coordinator never touches the addendum in either direction. Detail is dictated — a ten-word instruction to the
steward, or a brief's return contract — and appended by whoever holds shell.

## The git steward

Committing and pushing coordination artifacts, reconciling tracker rows against their handles, and branch hygiene belong
to `git-steward` (Sonnet 5), dispatched per invocation and never kept resident. A status update costs the coordinator
one tracker-row edit and a one-line dispatch, not a git session. The steward never pushes feature work:
coordination-artifact paths only, and anything else it finds dirty is reported, never committed and never stashed.

## Consolidation

Periodically — a milestone completes, a sprint ends, the plan visibly diverges — the architect reads the tracker plus
the addendum's unread suffix and amends the plan: what changed, what comes next, and **what the amendment supersedes,
named explicitly**. Open with the assertion being killed, or decisions get silently dropped.

The plan records the watermark: `consolidated through line N (<utc-timestamp>)`. Because the addendum is append-only and
never edited, line offsets are immutable — reading from line N+1 yields exactly the unconsolidated suffix, so each pass
is incremental and consolidation cost does not grow with project age. This recurring pass is also what catches plan
items that already shipped: scope comes from tickets, truth comes from the tree, and the consolidation is where the two
are reconciled on a schedule instead of by accident.

## Operating rules

Operational constants shared by every brief — build protocol, commit cadence, timeouts, standing constraints — live once
in `.claude/agent-operating-rules.md`, and briefs point at it instead of restating it. A brief carries the task: goal,
plan path, scope, acceptance criteria, return cap — plus the pointer.

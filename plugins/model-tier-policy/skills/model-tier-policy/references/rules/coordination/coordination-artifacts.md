# Coordination — plan, tracker, addendum

A coordinating session (an orchestrator session, or a premium session running a project) keeps its project state in
three files matched to how each one is accessed — the structural fix for the single tracking file that grows until every
status update costs a full read and the board goes stale because keeping it current is too expensive. They live beside
each other in the repo's plans directory (`paths.plans` in `.claude/model-tier-policy.json`, default `.claude/plans/`):
`<slug>.plan.md`, `<slug>.tracker.md`, `<slug>.addendum.md`.

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

When the plan is authored for dispatch — by the architect, usually — its rows are seeded from the plan before any step
goes out, and each carries the dispatch index beside the state, and the provenance beside that:

```
| id | what | plan section | depends on | size | state | ref | last | auth | next | details |
```

The tracker is the coordinator's memory, and it holds what conversational memory loses first. `ref` is the immutable
observation the state rests on — the sha the checks were green at, the PR number — never a moving ref. `last` is
`actor · action · utc`: who did what, most recently, to this item — the field a compaction summary drops, and the one a
coordinator then back-fills with itself. `auth` is who may perform the row's irreversible step and who has approved it
(`merge: owner`, then `merge: owner-approved 2026-09-12T14:02Z`); an irreversible action is dispatched only from a row
whose `auth` says so, never from what the conversation remembers. `next` is the next action and its role; `details` is
the path of the receipt or artifact that carries the rest. The architect seeds the rows; the steward's reconciliation
trues `state`, `ref`, and `last` against the handles; the coordinator edits `state`, `next`, and `auth` as it routes,
and `auth` only from the owner's word. A row that wants a second line sends its narrative to the addendum.

The section — the plan heading the step lives under, cited by its anchor — is what lets a worker's brief say "step 7 —
`<plan path>#m2-3-the-gate`" and the worker read only that section. A heading is an identity where a line number is only
an address: it survives edits above it, a link to it can be checked, and it fails loudly when the section is gone
instead of silently pointing at the wrong lines. It stays true because the plan does not churn: a plan amended often
enough for its headings to move is a plan absorbing churn that belongs in the tracker or the addendum, and a
consolidation pass that amends the plan re-trues the rows' sections in the same pass. The coordinator dispatches from
the row and never opens the plan — it passes the plan's references along, and the architect's short brief says what,
how, and in what order. The decomposition is the architect's work product; reading the plan to re-derive it is the
duplication the tier split exists to remove.

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

## Receipts

Every return to a coordinator leads with a receipt — seven lines, under the configured cap (`return_cap_chars`, default
1500 characters, enforced by the receipt hook):

```
outcome: ready
object: PR #873 @ 0a538d3
evidence: checks green; review approved
actor: owner
uncertainty: none
next_action: wait for the owner to merge
details: .claude/receipts/<session>/agent-def456.md
```

`outcome` is the state the work reached, in a word or two; `object` names what it is about, with its immutable ref;
`evidence` is how the outcome was verified, as references; `actor` is who performed the decisive action — the receipt
that says `actor: owner` is what keeps a coordinator from later remembering itself in that role; `uncertainty` is what
the worker could not settle; `next_action` is what should happen next and whose it is; `details` is the path of the file
that carries everything else. The coordinator acts on the receipt and passes the path on; it never opens the file — the
path is a handle, not a read. A return longer than the cap is filed under `paths.receipts` by the hook and the worker is
asked for the receipt; the file is where a later reader, or a scout, finds the rest.

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

Where plan files are committed deliverables (a `paths.plans` under `docs/`, say), consolidation also publishes: the
steward commits the amended plan and the trued tracker so the docs tree carries the current state, and the addendum
stays where it is — appended, never published whole. Where plans are session scratch, nothing changes.

## Operating rules

Operational constants shared by every brief — build protocol, commit cadence, timeouts, standing constraints — live once
in the operating-rules file (`paths.operating_rules`, default `.claude/agent-operating-rules.md`), and briefs point at
it instead of restating it. Restating is the failure this file exists to prevent: a brief carries the task — goal, plan
path, scope, acceptance criteria, return cap — plus the pointer, and literal content beyond a few lines goes to a file
whose path the brief passes.

## The compaction threshold

Compaction mid-project is the death this discipline defends against, so the approach of the threshold is an event, not
background. When context is close to compacting: stop dispatching new work, dictate a handoff entry to the addendum —
one line per in-flight item, with its state and its handles — have the steward true the tracker and commit everything,
and only then hand off or compact. The artifacts are the contract that survives; anything held only in context does not.

And after a compaction — the moment the discipline could not prevent — treat the summary as loss of authority, not as
memory: every actor, approval, and precedent it reports is unverified until a call or a tracker row confirms it. Reload
state from the tracker (its `last` and `auth` columns are the ledger), perform no irreversible action and dispatch none
on the strength of the summary, and have the steward reconcile the rows against their handles before the next dispatch.
The reminder hook says this on the first turn after a compaction; the discipline is what makes that turn survivable.

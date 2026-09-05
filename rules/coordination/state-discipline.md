# Coordination — state discipline

Four rules about asserting, reporting, triaging, and subscribing to state, for any session that coordinates work or
watches events.

## Never assert repo state from memory

Every factual claim about a branch, a PR, an issue, or CI — in a reply to the user, a brief to an agent, or a tracker
row — gets one cheap verification call first. Memory of repo state goes stale the moment anyone else acts, and a stale
claim costs more to correct than the call costs to make: it produces contradictory briefs, and dispatches against work
that already landed. The state to distrust most is the state you yourself set — it is exactly what someone else has had
time to change.

## Silence on no-op events

An event that requires no action gets no user-facing text. Report state _changes_, not state _observations_: "still
green", "no new comments", "check passed as expected" are context spent on nothing, and twenty of them bury the one
event that mattered. Handle the event, update the tracker if a row changed, and say nothing otherwise.

## Recognize no-ops by construction

Most of a subscription's traffic is decidable without reading it. Three classes are no-ops by construction, each settled
by one comparison made before anything else about the event is read:

- **A check on a superseded commit.** A `check_suite` or `check_run` event whose `head_sha` is not the PR's current head
  reports on a commit that has already been replaced — its verdict, red or green, changes nothing. Compare the sha to
  the head you last pushed; do not read the run.
- **An echo of your own write.** A comment, review reply, thread resolution, or ready-for-review flip that this session
  or one of its agents performed comes back as an event. It is a receipt, not a request: match it against what you just
  did and drop it.
- **The subscription rulebook.** The payload that arrives when a subscription is created restates the handling rules at
  length. It carries no state; nothing in it needs a reply or a tracker row.

What survives the three comparisons — a check on the current head, a comment someone else wrote — is the event worth the
read. On a typical PR those are a small minority of what is delivered; treating every delivery as a read is how a
coordinator's context goes to receipts.

## Subscribe deliberately

Every subscription's events land in the subscribing session's context, in full, forever — there is no lower tier to
route them to. So subscribe to a PR only where an event would change what you do: a red build you would fix, a review
you would answer. A docs-only change, or a PR that cannot meaningfully fail, gets a scheduled check-in instead of a
subscription, and a subscription whose answer has become "nothing" gets unsubscribed, not tolerated.

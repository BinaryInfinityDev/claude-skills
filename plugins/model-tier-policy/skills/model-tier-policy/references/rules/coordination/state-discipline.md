# Coordination — state discipline

Three rules about asserting, reporting, and subscribing to state, for any session that coordinates work or watches
events.

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

## Subscribe deliberately

Every subscription's events land in the subscribing session's context, in full, forever — there is no lower tier to
route them to. So subscribe to a PR only where an event would change what you do: a red build you would fix, a review
you would answer. A docs-only change, or a PR that cannot meaningfully fail, gets a scheduled check-in instead of a
subscription, and a subscription whose answer has become "nothing" gets unsubscribed, not tolerated.

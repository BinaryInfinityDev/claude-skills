# Coordination — state discipline

Two rules about asserting and reporting state, for any session that coordinates work or watches events.

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

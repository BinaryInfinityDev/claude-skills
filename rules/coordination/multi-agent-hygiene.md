# Coordination — multi-agent hygiene

When several agents work one repository at once, the shared namespaces — branch names, remote refs, scratch files — are
where they collide. Three incidents in two trial runs, all the same class: two writers, one name, no coordination.

## Branches

- **Namespace the branches you create.** A branch name carries its creator: `<role>/<slug>-<id>` (the id a short random
  suffix), so two agents never reach for the same name and a stale branch names its owner.
- **Fetch before you create.** A name that is free locally may exist on the remote; creating over it silently forks
  history. `git fetch origin <name>` first, and if the name is taken, pick another — never reuse it.
- **Never create onto or rename onto a live name**, and **never rename, reset, or force-push a branch another agent
  created.** Its checkout, its worktree, and its push expectations all break silently. If another agent's branch looks
  wrong, report it to the coordinator; the owner fixes it.

## Scratch space

The session scratchpad is shared between concurrently running agents, not per-agent. Suffix every scratch path you write
with an identifier unique to you (`scratchpad/run-bar.<agent-id>.sh`, or a random hex) — the same discipline the
worktree naming already applies, for the same reason: one agent's file was overwritten mid-flight by another's.

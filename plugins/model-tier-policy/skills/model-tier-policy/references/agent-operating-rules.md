# Agent operating rules

This file holds the operational constants every brief shares, written once — briefs point here instead of restating
them. Fill the sections in for this repo and delete what does not apply; keep it short enough that pointing at it stays
obviously cheaper than restating it.

## Build and verification

- Bar command: see `bar_command` in `.claude/model-tier-policy.json`; note here anything about running it (timeouts,
  known-slow modules, hook quirks).
- Quick checks any agent may run in-tree: (formatter, linter, focused tests)

## Git

- Agent branch naming: `<role>/<slug>-<id>` per the multi-agent-hygiene rule; repo-specific prefixes or exceptions go
  here.
- Commit and PR conventions beyond the repo's rules files: (anything a brief would otherwise restate)
- The resident git steward is spawned first, named `steward`. A tracked artifact is committed by messaging it —
  `commit <path>: <subject>`, plus `mark <row> …` for your own work, never `auth` — and its one-line reply goes in your
  receipt.

## Standing constraints

- (The constraints every brief was restating — "no concurrent bars", "never edit generated/ by hand", …)

## Return contracts

- Default return contract: the receipt — outcome, object, evidence, actor, uncertainty, next_action, details (a path) —
  under `return_cap_chars` (1500 by default, hook-enforced). No file contents, no transcripts, no diffs; anything longer
  goes to a file the receipt names.

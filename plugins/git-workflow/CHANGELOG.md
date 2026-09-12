# git-workflow — version history

Newest first. Each release entry names the pull request that merged it. **Outstanding** collects what is known and not
yet done.

## Outstanding

- None tracked. `arda-end-session`, the project-specific finalizer that `end-session` generalizes, stays unpackaged
  under the repo's top-level `skills/` as a reference implementation.

## 1.0.2 — 2026-09-12 — [#35](https://github.com/BinaryInfinityDev/claude-skills/pull/35)

- **Added:** this version history ([#34](https://github.com/BinaryInfinityDev/claude-skills/issues/34)), and the
  README's plugin table now links it. Nothing else changed: the pre-commit hook treats every file under the plugin as
  content, so adding the file took a patch bump, and the review round that reworded it took another — 1.0.1 was consumed
  on the branch.

## 1.0.0 — 2026-08-23 — [#15](https://github.com/BinaryInfinityDev/claude-skills/pull/15)

- **Added:** the plugin form of `start-session` and `end-session`, unchanged in content from the unpackaged skills.

## Before packaging

- 2026-05-25 — `start-session` pinned to Haiku as a procedural skill.
- 2026-05-24 — the initial commit: `start-session` and `end-session`.

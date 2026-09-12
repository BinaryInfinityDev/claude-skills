# time-tracking — version history

Newest first. Each entry names the pull request that merged it. **Outstanding** collects what is known and not yet done.

## Outstanding

- None tracked.

## 1.0.1 — 2026-09-12 — this history ([#34](https://github.com/BinaryInfinityDev/claude-skills/issues/34))

- **Added:** this version history, and the README's plugin table now links it. Nothing else changed; the pre-commit hook
  treats every file under the plugin as content, so adding the file took a patch bump.

## 1.0.0 — 2026-08-23 — [#15](https://github.com/BinaryInfinityDev/claude-skills/pull/15)

- **Added:** the plugin form of `session-timelog` and `time-report`, unchanged in content from the unpackaged skills.

## Before packaging

- 2026-08-22 — [#13](https://github.com/BinaryInfinityDev/claude-skills/pull/13): `session-timelog`'s skill file
  re-wrapped to satisfy the formatter; no content change.
- 2026-07-17 — [#2](https://github.com/BinaryInfinityDev/claude-skills/pull/2): `session-timelog` and `time-report` —
  content-free session timelines on a tracking branch, pooled into a time report and a per-day timesheet.

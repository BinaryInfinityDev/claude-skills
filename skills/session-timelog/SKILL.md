---
name: session-timelog
description:
  Record this session's own usage as a content-free timestamp timeline and commit it to a dedicated tracking branch
  (never via a PR). Use when the user says "log session time", "record session usage", "track this session", at the end
  of a working session, or on a timer/routine. Feeds the time-report skill; keeps time data out of feature PRs.
source: https://github.com/BinaryInfinityDev/claude-skills/blob/main/skills/session-timelog/SKILL.md
---

# Session Timelog

Record **when** this session worked — never **what** it did. Extract a timestamps-only timeline from the session's own
transcript and commit it to a dedicated tracking branch, so time data never pollutes a feature branch or PR.

This skill is **project-agnostic**: it discovers the transcript from the working directory and reads per-project
overrides from `.claude/timelog.yaml`.

---

## Why timestamps-only

A raw Claude Code transcript embeds prompts, tool output, file contents, model identifiers, the account email, and
environment internals. None of that is needed for time tracking. The timeline keeps one JSON object per event —
`{timestamp, type, sessionId}` — which is safe to keep in plain Git indefinitely (a full working day compresses to a few
hundred KB; no LFS needed).

## Configuration

Defaults work for any repo; override in `.claude/timelog.yaml` or via environment variables when running the script.

| Key (`.claude/timelog.yaml`) | Env var          | Default                    | Purpose                               |
| ---------------------------- | ---------------- | -------------------------- | ------------------------------------- |
| `branch`                     | `TIMELOG_BRANCH` | `metrics/session-timelogs` | Tracking branch the timelines land on |
| `remote`                     | `TIMELOG_REMOTE` | `origin`                   | Remote to push the tracking branch to |

## Steps

Run the bundled script from the repository root (it is self-contained; read it before first use):

```bash
bash references/record_timelog.sh
```

Verify from its output that each step happened:

1. **Locate this session's transcript.** A cloud session's container holds only its own transcript, under
   `~/.claude/projects/<sanitized-cwd>/` (the working directory's absolute path with every non-alphanumeric character
   replaced by `-`). The main transcript is the most recently modified `*.jsonl` there; subagent sidechains live in
   `<session-id>/subagents/agent-*.jsonl`.
2. **Extract timestamps only** with `jq`: `select(type=="object" and .timestamp!=null) | {timestamp, type, sessionId}` —
   the bare identifiers in `{timestamp, type}` are jq field-lookup shorthand (`{type: .type}`), _not_ the `type`
   builtin.
3. **Scan the extract clean** — zero matches required for `@`, `/home/`, `/root/`, `proxy`, `trustStore`, and any
   model-id substring. The script aborts on a hit; investigate before retrying. Never commit a dirty extract.
4. **Commit to the tracking branch** via a temporary worktree — the working tree and current branch are never touched.
   Files land as `timelines/<UTC-date>-<sid8>.timeline.jsonl` (plus one per subagent). The branch is created as an
   orphan with an empty init commit if it doesn't exist.
5. **Push the branch**, retrying on network failure with backoff.

## Hard rules

- **Never open a PR for the tracking branch.** It is a data drop, consumed by the `time-report` skill and periodically
  cleared; a PR would defeat its purpose.
- **Never commit the raw transcript** — not to this branch, not anywhere. A raw archive is a separate, deliberate
  decision with its own redaction and secret-scan checklist; do not fold it into this skill.
- Re-running in the same session overwrites that session's own files (snapshot semantics) — safe and idempotent. The
  snapshot ends at extraction time; the commit itself and the session's final turns are not captured, and that is
  expected.
- Different sessions write different filenames, so concurrent sessions never conflict.

## Trigger phrases

- "log session time", "record session usage", "track this session", "/session-timelog"
- At the natural end of a working session (pairs well with an end-session skill)
- On a timer: a scheduled routine resumes the session (or the session schedules a self check-in) and invokes this skill,
  so long-running sessions leave timelines even if they die before wrap-up
- Before purging or abandoning a session whose time should still be counted

---
name: end-session
description: Finalize a git session branch — write a session summary, run project-specific finalization, and merge to the main branch with a structured commit. Use when the user says "end session", "wrap up", "session complete", or invokes /end-session.
source: https://github.com/bamapookie/claude-skills/blob/main/skills/end-session/SKILL.md
---

# End Session

Finalize the current git session branch by writing a session summary, running optional project-specific finalization, and merging into the main branch with a structured commit.

This skill is **project-agnostic**. Project-specific behavior (where summaries live, what extra files to update) is supplied by config and a project-scoped follow-up skill.

---

## Configuration

The skill resolves configuration in this order (each layer overrides the previous):

1. **Defaults** — work for any repo
2. **`.claude/session.yaml`** at the repo root — per-project overrides
3. **Skill arguments** at invocation — one-off overrides

### Config keys

| Key              | Default                                                  | Purpose                                                                                    |
| ---------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `summary_dir`    | `./sessions/`                                            | Directory where session summary files are written                                          |
| `summary_name`   | `session-{date}-{nn}.md`                                 | Filename pattern; `{date}` = YYYY-MM-DD, `{nn}` = 2-digit session number                   |
| `branch_regex`   | `^session/(\d{4}-\d{2}-\d{2})-(\d{2})$`                  | Current branch must match; capture group 1 = date, group 2 = session number                |
| `main_branch`    | `main`                                                   | Branch to merge into                                                                       |
| `finalize_skill` | `session-finalize`                                       | Project skill to invoke between summary and merge. Skip silently if not in available list. |
| `co_author`      | `Co-Authored-By: Claude {model} <noreply@anthropic.com>` | Trailer for commits; `{model}` substituted with running-model name (e.g. `Opus 4.7`)       |

If `.claude/session.yaml` is missing, run with defaults. If a project's `CLAUDE.md` documents session conventions, honor those as additional constraints (template format, mandatory sections, etc.).

---

## Pre-flight checks

Run these before any state-changing operation. If any fails, stop and report.

1. **Repo state** — run `git status -sb` and `git log {main_branch}..HEAD --oneline` in parallel. Note any uncommitted files for step 4.
2. **Branch** — current branch must match `branch_regex`. Extract `{date}` and `{nn}`. If on `main_branch` or any non-matching branch, abort with: _"Not on a session branch matching `{branch_regex}`. Start one with `git checkout -b session/YYYY-MM-DD-NN` (or your project's convention)."_
3. **Main is current** — `git fetch --dry-run`. If main is behind origin, ask whether to `git pull --ff-only` before merging. Do not pull without asking.
4. **CLAUDE.md scan** — if a `CLAUDE.md` exists, read it for project-specific session conventions (file paths, additional artifacts to update, model-name format).

---

## Workflow

### 1. Gather session context

Run in parallel:

- `git log {main_branch}..HEAD --oneline` — commits on this branch
- `git diff {main_branch}...HEAD --stat` — change summary
- `git diff {main_branch}...HEAD --name-only` — file list

Use this material to author the summary in step 2.

### 2. Write or finalize the session summary

Path: `{summary_dir}/{summary_name}` with `{date}` and `{nn}` substituted.

- If the file does not exist, create it.
- If it exists, read it first and edit in place — do not overwrite an existing summary the user has been writing.

Default summary content (project's `CLAUDE.md` may specify a stricter template — honor it):

```markdown
# Session {nn} — {date}

**Tool:** {Claude Code CLI | Claude desktop app | other — ask if unclear}
**Participants:** {user name from `git config --get user.name`}, Claude ({model})

## Summary

{One paragraph describing what the session accomplished.}

## Changes

- {Bullets per commit or unit of work, grouped by theme}

## Decisions

{Decisions made and where they're recorded — link to decision files if the project has them. Omit section if none.}

## Follow-ups

{Open items, or "None" if clean.}
```

Show the draft to the user before committing if anything is ambiguous.

### 3. Invoke the project finalize skill

Check the available-skills list (system reminder) for a skill matching `finalize_skill` (default: `session-finalize`).

- **If present:** invoke it via the Skill tool. Pass context if the skill accepts args: `date={date} nn={nn} summary_path={path} branch={branch}`.
- **If absent:** continue without comment. Projects without project-specific finalization are valid.

The finalize skill handles things like sidebar entries, index tables, cross-reference files — anything beyond the session summary itself.

### 4. Commit pending changes

If pre-flight found uncommitted changes:

- Show the user the change list.
- Ask: _"Include these in the session before merging? Or stash them?"_
- If including: stage the relevant files by name (never `git add -A`), then commit with a clear imperative-mood message + the `co_author` trailer.
- If stashing: `git stash push -m "WIP after session/{date}-{nn}"` so they're recoverable.

The session summary file written in step 2 must be committed before merging.

### 5. Merge to main

State-changing — confirm with the user before executing unless they've pre-authorized in permission settings.

```bash
git checkout {main_branch}
git merge --no-ff session/{date}-{nn} -m "$(cat <<'EOF'
Merge session/{date}-{nn}: {one-line summary from step 2}

{3–6 bullet points summarizing the session, drawn from the summary file.}

{co_author trailer}
EOF
)"
```

If the merge fails (conflict, hook), stop and report; do not auto-resolve.

### 6. Report

Show:

- Session summary file path
- Merge commit SHA (`git rev-parse HEAD`)
- Any follow-ups extracted from the summary
- A note that the session branch can be deleted by the user (do **not** delete automatically — see Failure modes)

---

## Failure modes

- **Merge conflict** — stop, list conflicting files, ask the user how to proceed. Do not auto-resolve.
- **Pre-commit hook fails** — fix the underlying issue, re-stage, create a _new_ commit. Never `--amend` to bypass.
- **Detached HEAD** — abort, ask the user to check out a proper session branch first.
- **Branch name doesn't match `branch_regex`** — abort with the expected pattern in the message.
- **Main is behind origin** — ask before pulling. Never pull silently.
- **User asks to delete the session branch** — only after the merge succeeded and was pushed (if applicable). Branch deletion is destructive; require explicit confirmation each time, not session-level pre-authorization.

---

## Trigger phrases

Invoke this skill when the user says any of:

- "end session" / "end the session"
- "session complete" / "complete the session"
- "wrap up" / "wrap up the session"
- "/end-session"

Do not invoke for ambiguous phrases like "I'm done for now" — ask first.

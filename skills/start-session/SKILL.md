---
name: start-session
description: Start or resume a git session branch — detect current state, pull main if needed, and create or continue a session/YYYY-MM-DD-NN branch. Use when the user says "start session", "new session", "begin session", or invokes /start-session.
source: https://github.com/bamapookie/claude-skills/blob/main/skills/start-session/SKILL.md
---

# Start Session

Detect the current git state and either resume an existing session branch or create a new one. This skill ensures the working tree is ready for a focused unit of work.

This skill is **project-agnostic**. It reads `.claude/session.yaml` for overrides if present, otherwise uses defaults.

---

## Configuration

Same config file as `end-session` (`.claude/session.yaml`). Relevant keys:

| Key            | Default                                        | Purpose                                          |
| -------------- | ---------------------------------------------- | ------------------------------------------------ |
| `branch_regex` | `^session/(\d{4}-\d{2}-\d{2})-(\d{2})$`        | Pattern for session branches                     |
| `main_branch`  | `main`                                         | Branch to pull from and diverge from             |
| `co_author`    | `Co-Authored-By: Claude {model} <noreply@anthropic.com>` | Noted for the session — used in commits later |

---

## Pre-flight

Run these checks (all read-only, can be parallel):

1. `git branch --show-current` — current branch name
2. `git status -sb` — uncommitted changes
3. `git stash list` — pending stashes (informational)
4. Read `.claude/session.yaml` if it exists

---

## Decision tree

### Case 1: Already on a session branch

The current branch matches `branch_regex`.

- **Report:** "Already on `session/{date}-{nn}`. Continuing."
- **If uncommitted changes exist:** mention them so the user is aware, but don't block.
- **Do not** create a new branch. Do not switch.
- **Done.** The session is already in progress.

### Case 2: On the main branch

The current branch is `main_branch`.

**Step A — Sync main:**

```bash
git fetch origin
```

Check if main is behind origin:

```bash
git rev-list --count HEAD..origin/{main_branch}
```

- If behind (count > 0): run `git pull --ff-only`. If ff-only fails (diverged), stop and report — do not force-pull or rebase without user direction.
- If up to date: continue.

**Step B — Determine session number:**

Today's date in `YYYY-MM-DD` format. Find existing branches for today:

```bash
git branch --list "session/{today}-*"
```

- If none: `{nn}` = `01`
- If some exist: `{nn}` = highest existing number + 1, zero-padded to 2 digits

**Step C — Create the branch:**

```bash
git checkout -b session/{date}-{nn}
```

**Step D — Report:**

- New branch name
- Session number
- Whether main was pulled
- Any uncommitted changes carried over (inherited from main's working tree)
- The model running this session (from context — useful for co-author trailers later)

### Case 3: On a different branch (not main, not a session branch)

The user might be on a feature branch or something else.

- **Report:** "Currently on `{branch}`, which isn't a session branch or `{main_branch}`."
- **Ask:** "Switch to `{main_branch}` and start a new session, or stay here?"
- If switching: check for uncommitted changes first — offer to stash if any exist, then `git checkout {main_branch}` and proceed with Case 2.
- If staying: stop. The user knows what they're doing.

---

## Uncommitted changes

This skill never discards work. If uncommitted changes exist at any decision point:

- **On main before branching:** they carry into the new session branch automatically (git preserves working tree on branch creation). Mention this.
- **On a non-session branch:** offer to stash before switching.
- **Already on a session branch:** just note them and continue.

Never run `git checkout .`, `git restore .`, `git clean`, or `git reset --hard`.

---

## Edge cases

- **Detached HEAD** — abort. Ask user to check out a proper branch.
- **Dirty index (staged but uncommitted)** — warn but allow. The user may have staged work intentionally.
- **Session numbering overflow** (> 99 sessions in a day) — unlikely but if it happens, use 3 digits. Don't error.
- **No git remote** — skip the fetch/pull step; create the branch locally. Note that sync was skipped.
- **Rebase in progress / merge in progress** — abort. Report the state; ask the user to resolve first.

---

## Trigger phrases

Invoke this skill when the user says any of:

- "start session" / "start a session" / "new session"
- "begin session" / "begin a new session"
- "/start-session"

Also invoke if the user asks "what branch am I on?" or "am I on a session branch?" and the answer leads to starting one.

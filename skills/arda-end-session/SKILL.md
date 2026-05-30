---
name: arda-end-session
description:
  Arda Net project finalization — add the new session to the Starlight sidebar in astro.config.mjs and a row to the
  Sessions table in activity-index.md. Invoked by the generic end-session skill before merge.
model: haiku
source: https://github.com/BinaryInfinityDev/claude-skills/blob/main/skills/arda-end-session/SKILL.md
---

# Session Finalize — Arda Net

Project-specific counterpart to the generic `end-session` skill. Runs after the session summary file has been written,
before the merge to `main`. Updates the two cross-reference files that Starlight needs:

1. **`astro.config.mjs`** — sidebar entry under the Sessions group
2. **`src/content/docs/record/activity/activity-index.md`** — row in the Sessions table

Both lists are **newest-first**. New entries go at the top.

---

## Inputs

When invoked by `end-session`, these are passed as args:

| Arg            | Format                           | Example                                                              |
| -------------- | -------------------------------- | -------------------------------------------------------------------- |
| `date`         | `YYYY-MM-DD`                     | `2026-05-24`                                                         |
| `nn`           | 2-digit string                   | `01`                                                                 |
| `summary_path` | path to the session summary file | `src/content/docs/record/activity/sessions/session-2026-05-24-01.md` |
| `branch`       | session branch name              | `session/2026-05-24-01`                                              |

If invoked directly by the user (without `end-session`), derive these:

- `date` and `nn` from the current branch name (`session/YYYY-MM-DD-NN`)
- `summary_path` from `src/content/docs/record/activity/sessions/session-{date}-{nn}.md`

Abort if the summary file doesn't exist — this skill assumes `end-session` has already written it.

---

## Pre-flight

1. Read `summary_path` — needed to synthesize the activity-index row.
2. Read `astro.config.mjs` and `src/content/docs/record/activity/activity-index.md`.
3. Verify neither file already references `session-{date}-{nn}` (duplicate detection). If found, report and stop —
   likely indicates the skill has already run for this session.

---

## Step 1 — Update the Starlight sidebar

File: `astro.config.mjs`

Locate the Sessions group inside the Activity group inside the Record top-level. It looks like:

```js
{
  label: "Activity",
  items: [
    { label: "Activity Index", slug: "record/activity/activity-index" },
    {
      label: "Sessions",
      items: [
        { label: "2026-05-23 Session 02", slug: "record/activity/sessions/session-2026-05-23-02" },
        { label: "2026-05-23 Session 01", slug: "record/activity/sessions/session-2026-05-23-01" },
        // ...
      ],
    },
  ],
},
```

**Insert** at the top of the Sessions `items` array:

```js
{ label: "{date} Session {nn}", slug: "record/activity/sessions/session-{date}-{nn}" },
```

### Insertion rules

- Newest-first. The new entry becomes the first item.
- Two-space indent inside `items: [` per the existing file style (use Read to confirm exact indentation before editing).
- Trailing comma on every entry, including the new one.
- Label format: `YYYY-MM-DD Session NN` — exact spacing, single space between date and "Session", single space before
  the two-digit number.
- Slug format: `record/activity/sessions/session-YYYY-MM-DD-NN` — no leading slash, no `.md` extension.

Use `Edit` with a sufficiently unique `old_string` (include the `Sessions` line + the current first entry) so the
insertion is unambiguous.

---

## Step 2 — Update the activity-index Sessions table

File: `src/content/docs/record/activity/activity-index.md`

Locate the table under the `## Sessions` heading:

```markdown
| Date                                            | Tool        | Session | Summary |
| ----------------------------------------------- | ----------- | ------- | ------- |
| [2026-05-23](sessions/session-2026-05-23-02.md) | Claude Code | 02      | ...     |
```

(Real header has wider column padding — match what's already there.)

**Insert** a new row immediately after the header separator (`| ---- | ... |`), making it the first data row.

### Row format

```markdown
| [{date}](sessions/session-{date}-{nn}.md) | {tool} | {nn} | {summary} |
```

| Field     | How to fill                                                                                                            |
| --------- | ---------------------------------------------------------------------------------------------------------------------- |
| `date`    | The skill input `date` (YYYY-MM-DD)                                                                                    |
| `tool`    | `Claude Code` for CLI sessions; `Cowork` for Claude desktop app sessions. Read from the session summary's header line. |
| `nn`      | The skill input `nn` (zero-padded 2 digits, e.g. `01`)                                                                 |
| `summary` | Dense single-cell synthesis of the session — see below                                                                 |

### Summary field

The summary cell is a **dense paragraph** of 1–4 sentences synthesizing the session's work. Read prior rows in the table
to calibrate density and tone — they pack a lot of concrete detail into one cell.

Source the content from the session summary file's narrative sections (Summary, Changes, Decisions). Surface concrete
facts: decision IDs (e.g. `D-040`), file paths, services, dates, sizes — not abstractions.

The cell is one long line in the Markdown source. No internal line breaks. Markdown links inside the cell are allowed
(e.g. linking to decisions). No raw HTML.

If the session was trivial (one-line fix, no decisions), a one-sentence cell is fine.

---

## Step 3 — Verify

After both edits:

1. Confirm the sidebar entry is at the top of the Sessions group and the trailing comma is present.
2. Confirm the activity-index row is at the top of the data rows (immediately after the separator) and the column count
   matches the header.
3. Run `git diff astro.config.mjs src/content/docs/record/activity/activity-index.md` and show the user the two-file
   diff so they can sanity-check before merge.

---

## Failure modes

- **Sessions group not found in `astro.config.mjs`** — sidebar layout has changed; abort and ask the user to confirm
  where session entries should go now.
- **Sessions table not found in `activity-index.md`** — abort; report which file structure looks different.
- **Duplicate detected** (entry for this `date`/`nn` already in either file) — abort; do not overwrite. The skill is
  idempotent in spirit but conservative in practice.
- **Indentation mismatch** in `astro.config.mjs` — read the surrounding 5–10 lines before inserting; match the existing
  pattern exactly.

---

## When to invoke directly

`end-session` invokes this skill automatically. You can also invoke it manually if a session was merged without
finalization and you need to backfill the cross-references — pass `date`, `nn`, and `summary_path` explicitly.

Trigger phrases for direct invocation:

- "finalize the session indexes"
- "update the sidebar and activity index for session NN"
- "/session-finalize"

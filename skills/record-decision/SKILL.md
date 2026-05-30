---
name: record-decision
description:
  Record an architecture/design decision with auto-incrementing numbering, structured sections, and index update. Use
  when the user makes or discusses a decision worth recording, or invokes /record-decision.
source: https://github.com/BinaryInfinityDev/claude-skills/blob/main/skills/record-decision/SKILL.md
---

# Record Decision

Record a numbered decision with structured sections, write it to the appropriate location, and update the project's
decision index. This skill handles the mechanics — numbering, file placement, cross-references — so the author focuses
on content.

This skill is **project-agnostic**. It reads `.claude/decisions.yaml` for project-specific conventions (topic
categories, file layout, section format). Without config, it defaults to a simple single-file ADR pattern.

---

## Configuration

Read `.claude/decisions.yaml` at the repo root. If absent, use defaults.

### Config keys

| Key             | Default                             | Purpose                                                                                       |
| --------------- | ----------------------------------- | --------------------------------------------------------------------------------------------- |
| `decisions_dir` | `./decisions/`                      | Directory containing decision files                                                           |
| `index_file`    | `null` (no index)                   | Path to a summary index file; if set, a one-line entry is added                               |
| `layout`        | `one-per-file`                      | How decisions are stored: `one-per-file`, `single-file`, or `topic-split`                     |
| `prefix`        | `ADR-`                              | Numbering prefix                                                                              |
| `padding`       | `4`                                 | Zero-padding width (e.g., 4 → `ADR-0001`)                                                     |
| `topics`        | `null`                              | Map of topic name → filename (required when `layout: topic-split`)                            |
| `sections`      | `[Context, Decision, Consequences]` | Ordered list of section headings for each full entry                                          |
| `heading_level` | `##`                                | Markdown heading level for each decision                                                      |
| `title_style`   | `inline`                            | `inline` (title in heading) or `bold-below` (title as bold line after heading)                |
| `index_format`  | (see below)                         | Template for the index entry                                                                  |
| `anchor_style`  | `default`                           | `default` (rehype-slug from full heading) or `number-only` (heading contains only the number) |

### Layout modes

- **`one-per-file`** — each decision is its own file: `{decisions_dir}/{prefix}{number}.md`. Default for new projects.
- **`single-file`** — all decisions appended to one file: `{decisions_dir}/decisions.md`.
- **`topic-split`** — decisions grouped by topic, one file per topic. Requires `topics` map.

---

## Workflow

### 1. Determine the next number

Scan all decision files in `decisions_dir` for headings matching `{heading_level} {prefix}NNN`. Find the highest number
and increment by 1.

For `topic-split` layout, scan ALL topic files — decisions share a single global sequence.

### 2. Gather inputs

The skill needs:

| Input     | Source                                                                          |
| --------- | ------------------------------------------------------------------------------- |
| **Title** | From the user's message, or ask                                                 |
| **Topic** | Ask the user to pick from `topics` keys (only for `topic-split` layout)         |
| **Date**  | Today's date (YYYY-MM-DD)                                                       |
| **Body**  | Each configured section — synthesize from conversation context, or ask for each |

If the decision has already been discussed in the conversation (user said "let's decide X because Y"), synthesize the
sections from context rather than asking the user to re-state everything. Show the draft and ask for confirmation.

### 3. Write the full entry

**Location** depends on layout mode:

- `one-per-file`: create `{decisions_dir}/{prefix}{number}.md` with frontmatter + sections
- `single-file`: append to the single decisions file
- `topic-split`: append to `{decisions_dir}/{topics[chosen_topic]}`

**Entry format:**

```markdown
{heading_level} {prefix}{number} ← if anchor_style: number-only, heading is ONLY the number if anchor_style: default,
title goes in the heading

{title as bold line} ← only when title_style: bold-below

**{sections[0]}:** ...

**{sections[1]}:**

- ...

**{sections[2]}:**

- ...
```

Separate the new entry from the previous one with a `---` horizontal rule if the file already has entries.

### 4. Update the index (if configured)

If `index_file` is set, add an entry. The entry format is controlled by `index_format`. Default:

```markdown
{heading_level} {prefix}{number}

**{title}** _({date})_

{one-sentence summary}

→ [Full context]({relative_path_to_entry}#{anchor})
```

**Placement:** find the correct section in the index. For `topic-split`, the index is organized by topic with section
headers — insert under the matching topic section. New entries go at the END of their section (chronological within a
topic).

### 5. Report

Show:

- Decision number assigned
- File written (with path)
- Index entry added (if applicable)
- The anchor that other pages can reference: `{index_file}#{anchor}`

---

## Synthesizing from conversation

When the user discusses a decision in conversation ("let's go with X because Y, the alternative was Z"), extract:

- **Title** — short imperative or declarative phrase describing the choice
- **Decision section** — what was decided, stated clearly
- **Rationale/Context section** — why this choice was made (the reasons from conversation)
- **Implications/Consequences section** — what follows from this decision
- **Alternatives section** — what was considered and rejected, with brief reasons

Show the synthesized entry to the user before writing. They may want to adjust wording or add detail.

---

## Edge cases

- **Number gap** — if decisions were deleted or skipped, use the next number after the highest existing, not the gap.
  Never reuse a number.
- **Duplicate detection** — if the exact title + number already exists in the target file, abort and report.
- **Missing topic file** — if `layout: topic-split` and the topic file doesn't exist, create it with appropriate
  frontmatter (read sibling files for format).
- **Index section not found** — if the index file doesn't have a section header matching the topic, report and ask where
  to insert.

---

## Trigger phrases

Invoke this skill when:

- User says "record this decision", "let's document this as a decision", "add this to the decision log"
- User says "/record-decision"
- A clear architectural choice has been made in conversation and should be preserved

Do not invoke unprompted — decisions are intentional records, not meeting notes. If you think something should be
recorded, suggest it; don't just write it.

---
name: ingest-artifact
description: Ingest raw lab data (zone files, configs, exports) into the project's artifact store — write the file, update the catalog index. Use when the user provides raw data to archive, or invokes /ingest-artifact.
model: haiku
source: https://github.com/bamapookie/claude-skills/blob/main/skills/ingest-artifact/SKILL.md
---

# Ingest Artifact

Accept raw data from the user (pasted content, a local file path, or command output), store it in the project's artifact directory in the appropriate format, and update the catalog index.

This skill is **project-agnostic**. It reads `.claude/artifacts.yaml` for project-specific conventions (paths, catalog format, subdirectories). Without config, it defaults to a simple `./artifacts/` directory with markdown wrappers.

---

## Configuration

Read `.claude/artifacts.yaml` at the repo root. If absent, use defaults.

### Config keys

| Key               | Default                                   | Purpose                                                                              |
| ----------------- | ----------------------------------------- | ------------------------------------------------------------------------------------ |
| `raw_dir`         | `null`                                    | Directory for raw static files (served verbatim). If null, only wrapper mode is used |
| `wrapper_dir`     | `./artifacts/`                            | Directory for `.md` wrapper pages                                                    |
| `catalog_file`    | `{wrapper_dir}/index.md`                  | Path to the catalog/index file                                                       |
| `subdirectories`  | `{}`                                      | Map of category name → subdirectory + description                                    |
| `naming`          | `lowercase-hyphenated`                    | Filename convention                                                                  |
| `catalog_columns` | `[Artifact, Type, Source, Last Exported]` | Column headings for the catalog table                                                |

### Storage modes

- **Raw file** — the export file is stored verbatim (no markdown wrapping). Best for stable outputs from scripts where overwriting on re-export is expected. The catalog row carries all metadata.
- **Markdown wrapper** — a `.md` page with a metadata table and the raw content in a fenced code block. Best for hand-curated data, one-off exports, or artifacts that need a rendered site URL for cross-linking.

The user chooses the mode at ingest time (or the skill recommends based on source).

---

## Workflow

### 1. Receive the raw data

Sources:

- **Pasted in conversation** — user pastes raw content directly
- **Local file path** — user points to a file on disk (e.g., "ingest `/tmp/zone-export.txt`")
- **Command output** — user says "run `cat /etc/pihole/...` and ingest the result" (only if the user instructs the command)

Read the content. Detect or ask:

| Field        | How to determine                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------- |
| **Syntax**   | Auto-detect from content or extension: `zone`, `json`, `yaml`, `ini`, `toml`, `xml`, `sh`, `conf` |
| **Category** | Ask the user to pick from `subdirectories` keys, or infer from content type                       |
| **Name**     | Derive from the content (e.g., zone `$ORIGIN` → `arda.kovalchick.me.zone`) or ask                 |
| **Source**   | Ask: what host/system/tool produced this?                                                         |
| **Date**     | Today, unless the user specifies otherwise or the content contains a generation timestamp         |

### 2. Choose storage mode

Recommend based on source:

- Has a generator script / will be re-exported regularly → **raw file** (overwrite-in-place)
- Hand-curated / one-off / needs a rendered URL for cross-linking → **markdown wrapper**

If `raw_dir` is not configured, only wrapper mode is available.

Ask the user to confirm the choice.

### 3. Write the artifact

**Raw file mode:**

Write to `{raw_dir}/{category}/{filename}`. The file content is stored exactly as received — no modification, no wrapping.

**Wrapper mode:**

Write to `{wrapper_dir}/{category}/{slug}.md`:

```markdown
---
title: "{descriptive title}"
---

| Field           | Value                                   |
| --------------- | --------------------------------------- |
| **Type**        | {type — e.g., dns-zone, config, export} |
| **Source**      | {host or system}                        |
| **Exported**    | {YYYY-MM-DD}                            |
| **Description** | {one-line description}                  |

---

\`\`\`{syntax}
{raw content verbatim}
\`\`\`
```

Preserve the raw content exactly — no reformatting, no trailing-whitespace trimming, no line-ending normalization.

### 4. Update the catalog

Add a row to the catalog table in `catalog_file`.

**Placement:** append at the end of the existing table rows (chronological — newest last). If the table is organized by section/category, insert under the matching group.

**Row format** matches `catalog_columns` config. Default:

```markdown
| [`{category}/{filename}`]({link}) | {type} | {source} | {date} |
```

The link format depends on storage mode:

- Raw file: absolute path from site root (e.g., `/artifacts/dns/file.zone`)
- Wrapper: relative path from the catalog (e.g., `dns/slug`)

### 5. Sidebar entry (if configured)

By default, artifacts do NOT get individual sidebar entries — the catalog is the discovery mechanism. If the project's config specifies `sidebar_file` and `sidebar_section`, add an entry there.

### 6. Report

Show:

- File written (with full path)
- Catalog row added
- The URL where the artifact will be accessible on the built site
- If wrapper mode: remind the user to verify the fenced code block renders correctly

---

## Updating an existing artifact

If the target file already exists:

- **Raw file mode:** overwrite in place (this is expected — re-exports update the file). Update the `Last Exported` date in the catalog row.
- **Wrapper mode:** ask before overwriting. Show a diff of the raw content block (old vs. new) so the user can confirm.

In both cases, do NOT create a duplicate catalog entry — update the existing row's date.

---

## Fact-checking hook

After ingesting, scan for inconsistencies between the new artifact and existing documentation:

- If the artifact is a DNS zone: compare IPs and hostnames against what's documented in the lab reference pages.
- If the artifact is a config: compare service names, ports, paths against the relevant service pages.

If discrepancies are found, report them to the user. Do not auto-edit the documentation — flag as potential tasks for review.

---

## Edge cases

- **Binary files** (images, compiled exports) — store as raw files only. Cannot be wrapped in markdown code blocks. Note this in the catalog description.
- **Very large files** (>500 lines) — still store verbatim. For the wrapper format, warn the user that long code blocks may impact page load; suggest raw file mode instead.
- **Missing subdirectory** — create it. No special setup needed beyond the directory.
- **Content with triple-backtick fences** — use a longer fence (``````) or tildes (`~~~`) for the outer wrapper to avoid conflicts.

---

## Trigger phrases

Invoke this skill when:

- User says "ingest this", "add this artifact", "archive this export"
- User pastes raw configuration/zone/export data and says to store it
- User says "/ingest-artifact"
- User provides a file and says "add this to artifacts"

Do not invoke for documentation content — artifacts are raw data, not authored prose.

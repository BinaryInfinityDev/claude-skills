# Claude Skills Repository

A public collection of reusable Claude Code skills — project-agnostic automation for git workflows, artifact management,
and decision recording.

## Repository structure

```
skills/
  {skill-name}/
    SKILL.md        — the skill definition (frontmatter + instructions)
    references/     — optional supporting files (templates, schemas, examples)
rules/
  {category}/
    {rule-name}.md  — an always-loaded instruction block, installed to .claude/rules/
```

Each skill lives in its own directory under `skills/`. The `SKILL.md` file is the complete, self-contained skill
definition that can be copied into any project's `.claude/skills/` directory or linked as a user-level skill in
`~/.claude/skills/`.

Rules are the other half: **skills load on demand, rules load always.** A rule file is copied (or symlinked) into
`.claude/rules/`, where Claude Code loads it at the start of every session at the same priority as `.claude/CLAUDE.md`.
Use a rule for a standing convention that must always be in context, and a skill for a procedure that only matters when
invoked.

Rules are grouped by category directory — `rules/git-etiquette/semi-linear-history.md` — and the catalog in the README
is organized the same way. Claude Code discovers `.md` files under `.claude/rules/` recursively, so the category
directory can be preserved on install.

## Conventions

- Skills are **project-agnostic** unless their name includes a project prefix (e.g., `arda-end-session`).
  Project-specific skills are included as reference implementations.
- Each SKILL.md uses YAML frontmatter with `name` and `description` fields.
- Skills read per-project config from `.claude/*.yaml` files — they never hard-code paths or project-specific details.
- Trigger phrases are documented at the bottom of each SKILL.md.
- A rule file carries **no** `name`/`description` frontmatter — it is installed verbatim, so anything in it costs
  context in every session. Catalog metadata lives in the README table instead. The one frontmatter key a rule may use
  is `paths:`, which scopes it to matching files.
- Rules are written as standing instructions, not documentation about the repo. One topic per file, grouped into a
  category directory.

## Adding a new skill

1. Create `skills/{skill-name}/SKILL.md` with frontmatter and full instructions.
2. If the skill needs reference files (schemas, templates), add them to `skills/{skill-name}/references/`.
3. Update the skill catalog below.

## Adding a new rule

1. Create `rules/{category}/{rule-name}.md` — the complete block, written to be installed verbatim. Reuse an existing
   category directory, or add one when the topic is genuinely new.
2. Add it to the rule catalog in the README, under its category heading.
3. If this repo should follow it too, copy it to `.claude/rules/{category}/{rule-name}.md`.

## This repo's own rules

`.claude/rules/git-etiquette/semi-linear-history.md` is a copy of `rules/git-etiquette/semi-linear-history.md`. **Keep
the two in sync** — edit the canonical copy under `rules/`, then re-copy. This repo follows semi-linear history: branch,
rebase onto `main`, merge with a merge commit, never squash or rebase-merge.

## Skill catalog

| Skill                                                  | Description                                                                         |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| [start-session](skills/start-session/SKILL.md)         | Start or resume a git session branch                                                |
| [end-session](skills/end-session/SKILL.md)             | Finalize a session branch — summary, finalize hook, merge                           |
| [ingest-artifact](skills/ingest-artifact/SKILL.md)     | Ingest raw data into a project's artifact store                                     |
| [record-decision](skills/record-decision/SKILL.md)     | Record a numbered architecture/design decision                                      |
| [arda-end-session](skills/arda-end-session/SKILL.md)   | Project-specific session finalization for Arda Net (reference implementation)       |
| [session-timelog](skills/session-timelog/SKILL.md)     | Record a session's own usage as a content-free timeline on a tracking branch        |
| [time-report](skills/time-report/SKILL.md)             | Build a time report + timesheet from timelines, commits, and PRs/issues             |
| [model-tier-policy](skills/model-tier-policy/SKILL.md) | Fable 5 plans and reviews; Opus 5 / Sonnet 5 do the procedural work — hook-enforced |

## Installing a skill

Copy the skill directory into your project or user-level Claude config:

```bash
# Project-level (available only in that repo)
cp -r skills/start-session /path/to/repo/.claude/skills/

# User-level (available in all repos)
cp -r skills/start-session ~/.claude/skills/
```

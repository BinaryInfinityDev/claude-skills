# Claude Skills Repository

A public collection of reusable Claude Code skills — project-agnostic automation for git workflows, artifact management, and decision recording.

## Repository structure

```
skills/
  {skill-name}/
    SKILL.md        — the skill definition (frontmatter + instructions)
    references/     — optional supporting files (templates, schemas, examples)
```

Each skill lives in its own directory under `skills/`. The `SKILL.md` file is the complete, self-contained skill definition that can be copied into any project's `.claude/skills/` directory or linked as a user-level skill in `~/.claude/skills/`.

## Conventions

- Skills are **project-agnostic** unless their name includes a project prefix (e.g., `arda-end-session`). Project-specific skills are included as reference implementations.
- Each SKILL.md uses YAML frontmatter with `name` and `description` fields.
- Skills read per-project config from `.claude/*.yaml` files — they never hard-code paths or project-specific details.
- Trigger phrases are documented at the bottom of each SKILL.md.

## Adding a new skill

1. Create `skills/{skill-name}/SKILL.md` with frontmatter and full instructions.
2. If the skill needs reference files (schemas, templates), add them to `skills/{skill-name}/references/`.
3. Update the skill catalog below.

## Skill catalog

| Skill | Description |
| ----- | ----------- |
| [start-session](skills/start-session/SKILL.md) | Start or resume a git session branch |
| [end-session](skills/end-session/SKILL.md) | Finalize a session branch — summary, finalize hook, merge |
| [ingest-artifact](skills/ingest-artifact/SKILL.md) | Ingest raw data into a project's artifact store |
| [record-decision](skills/record-decision/SKILL.md) | Record a numbered architecture/design decision |
| [arda-end-session](skills/arda-end-session/SKILL.md) | Project-specific session finalization for Arda Net (reference implementation) |

## Installing a skill

Copy the skill directory into your project or user-level Claude config:

```bash
# Project-level (available only in that repo)
cp -r skills/start-session /path/to/repo/.claude/skills/

# User-level (available in all repos)
cp -r skills/start-session ~/.claude/skills/
```
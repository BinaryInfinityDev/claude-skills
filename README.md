Categorize the skills.# Claude Skills

A collection of reusable [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for git workflows, artifact management, and decision recording.

## Skills

### Git Workflow

| Skill | Description |
| ----- | ----------- |
| [start-session](skills/start-session/SKILL.md) | Start or resume a git session branch |
| [end-session](skills/end-session/SKILL.md) | Finalize a session branch — summary, finalize hook, merge |
| [arda-end-session](skills/arda-end-session/SKILL.md) | Project-specific session finalization for Arda Net |

### Project Management

| Skill | Description |
| ----- | ----------- |
| [ingest-artifact](skills/ingest-artifact/SKILL.md) | Ingest raw data into a project's artifact store |
| [record-decision](skills/record-decision/SKILL.md) | Record a numbered architecture/design decision |

## Installation

Copy a skill directory into your project or user-level Claude config:

```bash
# Project-level (available only in that repo)
cp -r skills/start-session /path/to/repo/.claude/skills/

# User-level (available in all repos)
cp -r skills/start-session ~/.claude/skills/
```

## How skills work

Each skill is a self-contained `SKILL.md` file with YAML frontmatter (`name`, `description`) and detailed instructions that Claude Code follows when the skill is triggered. Skills are project-agnostic by default — they read per-project config from `.claude/*.yaml` files rather than hard-coding paths.

See [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code) for more on custom skills.

## Contributing

1. Create `skills/{skill-name}/SKILL.md` with frontmatter and full instructions.
2. Add reference files (schemas, templates) to `skills/{skill-name}/references/` if needed.
3. Open a PR.

## License

[MIT](LICENSE)

# Claude Skills

A collection of reusable [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for git workflows,
artifact management, and decision recording.

## Skills

### Git Workflow

| Skill                                                | Description                                               |
| ---------------------------------------------------- | --------------------------------------------------------- |
| [start-session](skills/start-session/SKILL.md)       | Start or resume a git session branch                      |
| [end-session](skills/end-session/SKILL.md)           | Finalize a session branch — summary, finalize hook, merge |
| [arda-end-session](skills/arda-end-session/SKILL.md) | Project-specific session finalization for Arda Net        |

### Project Management

| Skill                                              | Description                                     |
| -------------------------------------------------- | ----------------------------------------------- |
| [ingest-artifact](skills/ingest-artifact/SKILL.md) | Ingest raw data into a project's artifact store |
| [record-decision](skills/record-decision/SKILL.md) | Record a numbered architecture/design decision  |

### Time Tracking

| Skill                                              | Description                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------------- |
| [session-timelog](skills/session-timelog/SKILL.md) | Record a session's own usage as a content-free timeline (tracking branch) |
| [time-report](skills/time-report/SKILL.md)         | Build a time report + timesheet from timelines, commits, and PRs/issues   |

The two work as a pipeline: sessions drop `{timestamp, type, sessionId}` timelines onto a dedicated tracking branch
(never via a PR, never the raw transcript), and `time-report` pools them with git/GitHub history into a report and a
per-day timesheet — on demand, at sprint review, or on a schedule. Once a report merges, the consumed timelines can be
folded into a consolidated CSV and the tracking branch cleared.

### Model Budget

| Skill                                                  | Description                                                              |
| ------------------------------------------------------ | ------------------------------------------------------------------------ |
| [model-tier-policy](skills/model-tier-policy/SKILL.md) | Fable 5 plans and reviews; Opus 5 (or Sonnet 5) does the procedural work |

Ships an always-loaded rules file, four pinned-model subagents, and two hooks. A `PreToolUse` guard hard-denies edits,
shell commands, workflows, and unpinned subagent spawns while the main loop is on the premium tier, and a
`UserPromptSubmit` hook re-injects the policy every turn so it survives long sessions and compaction.

## Installation

Copy a skill directory into your project or user-level Claude config:

```bash
# Project-level (available only in that repo)
cp -r skills/start-session /path/to/repo/.claude/skills/

# User-level (available in all repos)
cp -r skills/start-session ~/.claude/skills/
```

## How skills work

Each skill is a self-contained `SKILL.md` file with YAML frontmatter (`name`, `description`) and detailed instructions
that Claude Code follows when the skill is triggered. Skills are project-agnostic by default — they read per-project
config from `.claude/*.yaml` files rather than hard-coding paths.

See [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code) for more on custom skills.

## Contributing

1. Create `skills/{skill-name}/SKILL.md` with frontmatter and full instructions.
2. Add reference files (schemas, templates) to `skills/{skill-name}/references/` if needed.
3. Open a PR.

## License

[MIT](LICENSE)

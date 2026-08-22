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

Six roles, each pinned to a model: `architect` (Fable 5) frames and decides, `senior-developer` (Fable 5) implements the
rare change too entangled to hand off as a plan, `executor` (Opus 5) implements, `scout` (Opus 5, read-only)
investigates and returns findings instead of file contents, `devils-advocate` (Opus 5, read-only) optionally
stress-tests a plan before anyone builds it, and `runner` (Sonnet 5) handles bulk mechanical work, plus a
`build-analyst` specialist (Haiku 4.5) that triages failed-build logs from a path instead of re-running the build.

Unlike the other skills here, copying the directory is not enough — it ships an installer that writes the rules file,
the agents, and the hooks to the paths Claude Code reads, and enforcement comes from those:

```bash
python3 skills/model-tier-policy/references/install.py --target /path/to/repo
```

The hooks are live immediately; no session restart is needed. Ships an always-loaded rules file, those seven subagents,
and two hooks. A `PreToolUse` guard hard-denies edits, shell commands, workflows, and unpinned subagent spawns while the
main loop is on the premium tier, and a `UserPromptSubmit` hook re-injects the policy periodically — in full every 10th
turn and after every compaction, with a one-line marker in between — so it survives long sessions without the reminder
itself becoming a context cost.

## Agents

Agents are reusable subagent definitions — a role, its instructions, and the model it runs on, in one file. Copy one
into `.claude/agents/` (or `~/.claude/agents/`) and Claude Code can delegate to it by name. Every agent here pins its
own `model`, which is the point: a subagent's model otherwise defaults to `inherit`, so an unpinned spawn from a premium
session quietly runs the whole subtask on the premium tier.

Agents are grouped by category: `agents/{category}/{agent-name}.md`.

### Model Tier Policy

The six roles of the [model-tier-policy](skills/model-tier-policy/SKILL.md) skill, plus the specialists that ship
alongside them. Its installer writes these into a target repo for you; copy them by hand only if you want the roles
without the enforcement.

| Agent                                                            | Model     | Description                                                                        |
| ---------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------- |
| [architect](agents/model-tier-policy/architect.md)               | Fable 5   | Framing, trade-offs, and decisions — returns a decision, not code                  |
| [senior-developer](agents/model-tier-policy/senior-developer.md) | Fable 5   | Implementation too novel or entangled to hand off as a plan                        |
| [executor](agents/model-tier-policy/executor.md)                 | Opus 5    | The default worker: edits, refactors, tests, builds, git, debugging                |
| [scout](agents/model-tier-policy/scout.md)                       | Opus 5    | Read-only investigation that returns findings instead of file dumps                |
| [devils-advocate](agents/model-tier-policy/devils-advocate.md)   | Opus 5    | Read-only adversarial review of a plan — ranked objections + verdict               |
| [runner](agents/model-tier-policy/runner.md)                     | Sonnet 5  | Bulk mechanical work and build/test runs — failure logs go to build-analyst        |
| [build-analyst](agents/model-tier-policy/build-analyst.md)       | Haiku 4.5 | Build-log triage from a path: verdict or an honest `undetermined` — never a re-run |

## Installing an agent

Copy the agent file into `.claude/agents/`. Claude Code reads that directory flat, so the category directory is not
preserved on install:

```bash
mkdir -p /path/to/repo/.claude/agents
cp agents/model-tier-policy/*.md /path/to/repo/.claude/agents/
```

## Rules

Rules are always-loaded instruction blocks — the modular form of CLAUDE.md. Drop one in `.claude/rules/` and it enters
context at the start of every session, at the same priority as `.claude/CLAUDE.md`. Unlike skills, they need no trigger;
unlike a growing CLAUDE.md, each covers one topic in its own file.

Rules are grouped by category: `rules/{category}/{rule-name}.md`.

### Git Etiquette

| Rule                                                              | Description                                                                                      |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [semi-linear-history](rules/git-etiquette/semi-linear-history.md) | Branch, rebase onto base, merge with a merge commit — plus commit style and force-push etiquette |

## Installing a rule

Copy the rule file into `.claude/rules/`. Claude Code discovers `.md` files there recursively, so keeping the category
directory works and makes the source obvious:

```bash
mkdir -p /path/to/repo/.claude/rules/git-etiquette
cp rules/git-etiquette/semi-linear-history.md /path/to/repo/.claude/rules/git-etiquette/
```

Or symlink it, if you want one shared copy across several repos — `.claude/rules/` resolves symlinks:

```bash
ln -s ~/src/claude-skills/rules/git-etiquette/semi-linear-history.md \
      /path/to/repo/.claude/rules/git-etiquette/semi-linear-history.md
```

For personal rules that apply everywhere, use `~/.claude/rules/` instead. To scope a rule to part of a repo, add a
`paths:` frontmatter block and it loads only when Claude touches matching files:

```markdown
---
paths:
  - "src/api/**/*.ts"
---
```

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

For a skill:

1. Create `skills/{skill-name}/SKILL.md` with frontmatter and full instructions.
2. Add reference files (schemas, templates) to `skills/{skill-name}/references/` if needed.
3. Add it to the skill catalog above.

For a rule:

1. Create `rules/{category}/{rule-name}.md` — the complete block, written to be installed verbatim, with no `name` or
   `description` frontmatter (it would cost context in every session). Reuse an existing category directory, or add one
   when the topic is genuinely new.
2. Add it to the rule catalog above, under its category heading.

Then open a PR. This repo keeps semi-linear history — see
[semi-linear-history](rules/git-etiquette/semi-linear-history.md), which it follows itself.

## License

[MIT](LICENSE)

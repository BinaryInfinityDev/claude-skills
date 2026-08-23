# Claude Skills

A collection of reusable [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for git workflows,
artifact management, and decision recording — published as a **plugin marketplace**, so installs get real updates
instead of copy-and-forget.

## Installing from the marketplace — the recommended path

```
/plugin marketplace add BinaryInfinityDev/claude-skills
/plugin install model-tier-policy@claude-skills
```

| Plugin               | Contents                                                                                            |
| -------------------- | --------------------------------------------------------------------------------------------------- |
| `model-tier-policy`  | The tier-policy skill, ten pinned-model agents, and both enforcement hooks with their reminder text |
| `git-workflow`       | `start-session`, `end-session`                                                                      |
| `project-management` | `ingest-artifact`, `record-decision`                                                                |
| `time-tracking`      | `session-timelog`, `time-report`                                                                    |

Installed plugins are versioned (`plugin.json` semver) and update through the marketplace: third-party marketplaces do
not auto-update by default, so either toggle auto-update for `claude-skills` in `/plugin` → Marketplaces or pull updates
with `claude plugin marketplace update claude-skills`. Plugin skills are invoked as `/plugin-name:skill-name` (e.g.
`/git-workflow:start-session`).

One deliberate exception: **rules** (always-loaded instruction files) have no plugin component, so they still install by
copy or symlink as documented below — and `model-tier-policy`'s per-repo rules file and config are laid down by its
bundled installer, which stamps the plugin version so the skill can flag drift after an update. Everything else a plugin
carries — skills, agents, hooks, the hooks' injected wording — updates with the plugin, nothing to re-run.

Copying files by hand still works everywhere and is documented per section below; it just has no update channel beyond
`git pull` and re-copy.

## Skills

### Git Workflow

| Skill                                                               | Description                                               |
| ------------------------------------------------------------------- | --------------------------------------------------------- |
| [start-session](plugins/git-workflow/skills/start-session/SKILL.md) | Start or resume a git session branch                      |
| [end-session](plugins/git-workflow/skills/end-session/SKILL.md)     | Finalize a session branch — summary, finalize hook, merge |
| [arda-end-session](skills/arda-end-session/SKILL.md)                | Project-specific session finalization for Arda Net        |

### Project Management

| Skill                                                                         | Description                                     |
| ----------------------------------------------------------------------------- | ----------------------------------------------- |
| [ingest-artifact](plugins/project-management/skills/ingest-artifact/SKILL.md) | Ingest raw data into a project's artifact store |
| [record-decision](plugins/project-management/skills/record-decision/SKILL.md) | Record a numbered architecture/design decision  |

### Time Tracking

| Skill                                                                    | Description                                                               |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| [session-timelog](plugins/time-tracking/skills/session-timelog/SKILL.md) | Record a session's own usage as a content-free timeline (tracking branch) |
| [time-report](plugins/time-tracking/skills/time-report/SKILL.md)         | Build a time report + timesheet from timelines, commits, and PRs/issues   |

The two work as a pipeline: sessions drop `{timestamp, type, sessionId}` timelines onto a dedicated tracking branch
(never via a PR, never the raw transcript), and `time-report` pools them with git/GitHub history into a report and a
per-day timesheet — on demand, at sprint review, or on a schedule. Once a report merges, the consumed timelines can be
folded into a consolidated CSV and the tracking branch cleared.

### Model Budget

| Skill                                                                            | Description                                                                                             |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| [model-tier-policy](plugins/model-tier-policy/skills/model-tier-policy/SKILL.md) | An Opus 5 orchestrator coordinates; Fable 5 plans and reviews; Opus 5 / Sonnet 5 do the procedural work |

Eight roles, each pinned to a model: `orchestrator` (Opus 5) holds the session's main loop in the recommended topology
and coordinates — tickets, plans, dispatch, never implementation; `architect` (Fable 5) frames and decides;
`senior-developer` (Fable 5) implements the rare change too entangled to hand off as a plan; `executor` (Opus 5)
implements; `code-reviewer` (Fable 5 for the first pass per PR, Opus 5 for follow-ups, read-only) reads the proven diff
adversarially before the PR is marked ready; `scout` (Opus 5, read-only) investigates and returns findings instead of
file contents; `devils-advocate` (Opus 5, read-only) optionally stress-tests a plan before anyone builds it; and
`runner` (Sonnet 5) handles bulk mechanical work. Two specialists sit beside them: `build-runner` (Sonnet 5) proves a
ref in an isolated git worktree — one build at a time, lock-enforced, timed against a ledger — and `build-analyst`
(Haiku 4.5) triages failed-build logs from a path instead of re-running the build.

Unlike the other skills here, copying the directory is not enough — it ships an installer that writes the rules file,
the agents, and the hooks to the paths Claude Code reads, and enforcement comes from those:

```bash
python3 plugins/model-tier-policy/skills/model-tier-policy/references/install.py --target /path/to/repo
```

The hooks are live immediately; no session restart is needed. Ships an always-loaded rules file, the subagents above,
and two hooks. A `PreToolUse` guard hard-denies edits, shell commands, workflows, and unpinned subagent spawns while the
main loop is on the premium tier, and a `UserPromptSubmit` hook re-injects the policy periodically — in full every 10th
turn and after every compaction, with a one-line marker in between — so it survives long sessions without the reminder
itself becoming a context cost.

## Agents

Agents are reusable subagent definitions — a role, its instructions, and the model it runs on, in one file. Copy one
into `.claude/agents/` (or `~/.claude/agents/`) and Claude Code can delegate to it by name. Every agent here pins its
own `model`, which is the point: a subagent's model otherwise defaults to `inherit`, so an unpinned spawn from a premium
session quietly runs the whole subtask on the premium tier.

Agents live flat inside their plugin: `plugins/{plugin-name}/agents/{agent-name}.md`.

### Model Tier Policy

The roles of the [model-tier-policy](plugins/model-tier-policy/skills/model-tier-policy/SKILL.md) skill, plus the
specialists that ship alongside them. Its installer writes these into a target repo for you; copy them by hand only if
you want the roles without the enforcement.

| Agent                                                                    | Model     | Description                                                                        |
| ------------------------------------------------------------------------ | --------- | ---------------------------------------------------------------------------------- |
| [orchestrator](plugins/model-tier-policy/agents/orchestrator.md)         | Opus 5    | Coordinates the team from the main loop — tickets, plans, dispatch; never works    |
| [architect](plugins/model-tier-policy/agents/architect.md)               | Fable 5   | Framing, trade-offs, and decisions — returns a decision, not code                  |
| [senior-developer](plugins/model-tier-policy/agents/senior-developer.md) | Fable 5   | Implementation too novel or entangled to hand off as a plan                        |
| [executor](plugins/model-tier-policy/agents/executor.md)                 | Opus 5    | The default worker: edits, refactors, tests, builds, git, debugging                |
| [code-reviewer](plugins/model-tier-policy/agents/code-reviewer.md)       | Fable 5   | Adversarial read of the proven diff before the PR is ready; Opus 5 for follow-ups  |
| [scout](plugins/model-tier-policy/agents/scout.md)                       | Opus 5    | Read-only investigation that returns findings instead of file dumps                |
| [devils-advocate](plugins/model-tier-policy/agents/devils-advocate.md)   | Opus 5    | Read-only adversarial review of a plan — ranked objections + verdict               |
| [runner](plugins/model-tier-policy/agents/runner.md)                     | Sonnet 5  | Bulk mechanical work — heavy builds go to build-runner                             |
| [build-runner](plugins/model-tier-policy/agents/build-runner.md)         | Sonnet 5  | Heavy builds in an isolated worktree — one at a time, timed, cleaned up            |
| [build-analyst](plugins/model-tier-policy/agents/build-analyst.md)       | Haiku 4.5 | Build-log triage from a path: verdict or an honest `undetermined` — never a re-run |

## Installing an agent

Copy the agent file into `.claude/agents/`. Claude Code reads that directory flat, so the category directory is not
preserved on install:

```bash
mkdir -p /path/to/repo/.claude/agents
cp plugins/model-tier-policy/agents/*.md /path/to/repo/.claude/agents/
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

### Build Discipline

| Rule                                                         | Description                                                                                       |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| [worktree-builds](rules/build-discipline/worktree-builds.md) | Long builds run in a dedicated worktree beside development — one at a time, pushes gated on green |

The model-tier-policy installer installs this one automatically alongside the `build-runner` agent, since the agent's
worktree and lock mechanics assume its session-side conventions; other repos can install it by hand as below.

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
cp -r plugins/git-workflow/skills/start-session /path/to/repo/.claude/skills/

# User-level (available in all repos)
cp -r plugins/git-workflow/skills/start-session ~/.claude/skills/
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

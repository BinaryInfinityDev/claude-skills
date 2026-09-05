# Claude Skills Repository

A public collection of reusable Claude Code skills — project-agnostic automation for git workflows, artifact management,
and decision recording.

## Repository structure

```
.claude-plugin/
  marketplace.json  — the plugin marketplace manifest (name, owner, plugins[])
plugins/
  {plugin-name}/    — one self-contained plugin per cohesive unit
    .claude-plugin/plugin.json — plugin manifest (name, version, description)
    skills/{skill-name}/
      SKILL.md      — the skill definition (frontmatter + instructions)
      references/   — optional supporting files (templates, schemas, examples)
    agents/
      {agent-name}.md — model-pinned subagent definitions, flat (plugins do not read nested agent dirs)
    hooks/
      hooks.json    — plugin hook wiring, plus the hook scripts and their context fragments
skills/
  {skill-name}/     — unpackaged skills: project-specific reference implementations only
rules/
  {category}/
    {rule-name}.md  — an always-loaded instruction block, installed to .claude/rules/
```

Each plugin under `plugins/` is **self-contained** — installed plugins are copied out of the repo and cannot reference
files outside their own directory, so everything a plugin needs lives inside it. A `SKILL.md` is still complete on its
own: it can be installed via the marketplace, or copied into any project's `.claude/skills/` directory or linked as a
user-level skill in `~/.claude/skills/`.

Rules are the other half: **skills load on demand, rules load always.** A rule file is copied (or symlinked) into
`.claude/rules/`, where Claude Code loads it at the start of every session at the same priority as `.claude/CLAUDE.md`.
Use a rule for a standing convention that must always be in context, and a skill for a procedure that only matters when
invoked.

Rules are grouped by category directory — `rules/git-etiquette/semi-linear-history.md` — and the catalog in the README
is organized the same way. Claude Code discovers `.md` files under `.claude/rules/` recursively, so the category
directory can be preserved on install.

Agents are the third kind: a subagent definition — role, instructions, and a pinned `model` — that Claude Code delegates
to by name once it sits in `.claude/agents/` or arrives via a plugin. They live flat in their plugin's `agents/`
directory (beside the skill, not inside it, because more than one skill may cite the same role), and both
`.claude/agents/` and plugin agent dirs are read flat. The catalog entries are examples for consuming repos — this repo
does not install them into its own `.claude/`.

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
- A shipped rule carries **no relative links**. Installed, it lives in another tree (`.claude/rules/`) where a relative
  link dangles and nothing checks it; refer to sibling rules by name in prose ("see the coordination-artifacts rule").
  The pre-commit hook (`scripts/check-rule-links.sh`) enforces this over `rules/` and the plugin's shipped copies.
- An agent file carries only the frontmatter Claude Code's subagent format needs — `name`, `description`, `model`, and
  `tools` where the role is restricted. Nothing else; catalog metadata lives in the README table.
- A restricted agent states its boundary in its `description`. A coordinator picks a role from its description
  (`/agents`, the plugin listing) and never reads the body, so a boundary stated only in the body is still discovered by
  dispatching into the role. Every agent that declares `tools:` ends its description with a `Boundary:` clause — what
  the tools exclude and which role covers it — and a restricted role that carries `Bash` says that Bash is not `gh`.
  Write such a description as a `>-` folded scalar: YAML reads `: ` inside a plain scalar as a nested mapping, or
  rejects it, and either way the description is gone. The pre-commit hook (`scripts/check-agent-boundaries.sh`) enforces
  both clauses, and the scalar style, over every plugin's agents.
- Plugins are versioned with semver in `.claude-plugin/plugin.json`. Bump the version on any content change — that is
  the signal installed copies use to know an update exists, and `claude plugin update` reports "already at the latest
  version" over a stale cache when it is skipped. The pre-commit hook (`scripts/check-plugin-versions.sh`) blocks a
  commit that changes a plugin's content without changing its version. Validate with `claude plugin validate .`
  (marketplace) and `claude plugin validate ./plugins/<name>` before merging.

## Adding a new skill

1. Create `plugins/{plugin-name}/skills/{skill-name}/SKILL.md` with frontmatter and full instructions — reuse the plugin
   whose theme fits, or add a new plugin (manifest + marketplace entry) when the unit is genuinely new. Project-specific
   reference implementations go under top-level `skills/` instead, unpackaged.
2. If the skill needs reference files (schemas, templates), add them to its `references/` directory.
3. Bump the plugin's `version` in its `.claude-plugin/plugin.json` — that is what tells installed copies an update
   exists.
4. Update the skill catalog below.

## Adding a new rule

1. Create `rules/{category}/{rule-name}.md` — the complete block, written to be installed verbatim. Reuse an existing
   category directory, or add one when the topic is genuinely new.
2. Add it to the rule catalog in the README, under its category heading.
3. If this repo should follow it too, copy it to `.claude/rules/{category}/{rule-name}.md`.

## Adding a new agent

1. Create `plugins/{plugin-name}/agents/{agent-name}.md` — the complete subagent definition, written to be installed
   verbatim, flat in the plugin's `agents/` directory.
2. Always pin `model:`. An unpinned subagent inherits its caller's model, which is the cost the `model-tier-policy`
   skill exists to prevent.
3. If it declares `tools:`, end its `description` with a `Boundary:` clause (see Conventions) — the pre-commit check
   refuses a restricted agent without one.
4. Add it to the agent catalog in the README, and bump the plugin's `version`.
5. If a skill installs it by hand too, add it to that skill's installer — `model-tier-policy` sources its agents from
   `plugins/model-tier-policy/agents/`, so a new role there needs a line in
   `plugins/model-tier-policy/skills/model-tier-policy/references/install.py`.

## This repo's own rules

`.claude/rules/git-etiquette/semi-linear-history.md` is a copy of `rules/git-etiquette/semi-linear-history.md`. **Keep
the two in sync** — edit the canonical copy under `rules/`, then re-copy. This repo follows semi-linear history: branch,
rebase onto `main`, merge with a merge commit, never squash or rebase-merge.

The same sync discipline applies to every rule the model-tier-policy plugin ships a copy of —
`rules/build-discipline/worktree-builds.md`, `rules/coordination/coordination-artifacts.md`,
`rules/coordination/state-discipline.md`, and `rules/coordination/multi-agent-hygiene.md`: the canonical copy lives in
the top-level `rules/` catalog, and a second copy ships inside the plugin (under
`plugins/model-tier-policy/skills/model-tier-policy/references/rules/`) because an installed plugin cannot reach outside
its own directory. Edit the canonical copy, then re-copy into the plugin.

## Skill catalog

| Skill                                                                                                                    | Description                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| [start-session](plugins/git-workflow/skills/start-session/SKILL.md)                                                      | Start or resume a git session branch                                                         |
| [end-session](plugins/git-workflow/skills/end-session/SKILL.md)                                                          | Finalize a session branch — summary, finalize hook, merge                                    |
| [ingest-artifact](plugins/project-management/skills/ingest-artifact/SKILL.md)                                            | Ingest raw data into a project's artifact store                                              |
| [record-decision](plugins/project-management/skills/record-decision/SKILL.md)                                            | Record a numbered architecture/design decision                                               |
| [arda-end-session](skills/arda-end-session/SKILL.md)                                                                     | Project-specific session finalization for Arda Net (reference implementation)                |
| [session-timelog](plugins/time-tracking/skills/session-timelog/SKILL.md)                                                 | Record a session's own usage as a content-free timeline on a tracking branch                 |
| [time-report](plugins/time-tracking/skills/time-report/SKILL.md)                                                         | Build a time report + timesheet from timelines, commits, and PRs/issues                      |
| [model-tier-policy](plugins/model-tier-policy/skills/model-tier-policy/SKILL.md)                                         | An Opus 5 orchestrator coordinates; Fable 5 plans; Opus 5 / Sonnet 5 execute — hook-enforced |
| [write-in-simplified-technical-english](plugins/technical-writing/skills/write-in-simplified-technical-english/SKILL.md) | ASD-STE100 Simplified Technical English responses — unambiguous language, engineering intact |

## Installing a skill

Copy the skill directory into your project or user-level Claude config:

```bash
# Project-level (available only in that repo)
cp -r plugins/git-workflow/skills/start-session /path/to/repo/.claude/skills/

# User-level (available in all repos)
cp -r plugins/git-workflow/skills/start-session ~/.claude/skills/
```

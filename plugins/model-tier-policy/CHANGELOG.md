# model-tier-policy — version history

Newest first. Each release entry names the pull request that merged it. A version number a review round consumed on the
branch and never merged as such is listed under the entry that superseded it, because a branch-pinned install could have
fetched it and versions only move forward once fetchable. **Outstanding** collects what is known and not yet done; an
entry that settles one of its items says so.

## Outstanding

- The frontmatter `Agent(a, b)` allowlist — restricting which roles an orchestrator may spawn from its own definition —
  is deferred: Claude Code does not document how the allowlist composes with nesting, and an undocumented restriction is
  not a boundary (#32).
- The authorization tripwire matches ordinary spellings of a merge or a push to a protected branch, including the same
  phrase inside a quoted string. That false positive is accepted and documented in the skill; GitHub branch protection
  is the boundary that holds regardless (#32).
- In a Claude Code Remote container the plugin cannot install itself: the rules file, config and stamp are committed
  files that load normally while the agents and hooks are absent until a `SessionStart` hook installs the plugin. The
  skill ships the recipe; the gap is the harness's (#16).
- `claude plugin marketplace remove NAME` rewrites the consuming project's committed `.claude/settings.json` — a Claude
  Code CLI behaviour, not a plugin defect; the skill's remote section says to check `git diff` after a teardown (#16).
- `build-analyst` is Gradle-first. Maven support is deliberately absent rather than shipped untested (#7).

## 1.8.8 — 2026-09-12 — [#35](https://github.com/BinaryInfinityDev/claude-skills/pull/35)

- **Added:** this version history ([#34](https://github.com/BinaryInfinityDev/claude-skills/issues/34)), and the
  README's plugin table now links it. Nothing else changed: the pre-commit hook treats every file under the plugin as
  content, so adding the file took a patch bump, and the review round that reworded it took another — 1.8.7 was consumed
  on the branch.

## 1.8.6 — 2026-09-12 — [#33](https://github.com/BinaryInfinityDev/claude-skills/pull/33)

Acts on Copilot's review of #32, which landed three minutes after that merge. 1.8.4 and 1.8.5 were consumed on the
branch.

- **Fixed:** a filed receipt is created exclusively, named with a microsecond UTC stamp and a numeric suffix on
  collision, so two returns filed under one name can never overwrite each other; the descriptor is closed if
  `os.fdopen()` raises; the receipts location is contained in the repo the way the guard contains writes, so a
  `paths.receipts` that escapes it files nothing and the path handed back is always repo-relative.
- **Fixed:** `install.py --cache-status` counts a cached copy complete only when every hook script is present, so a
  half-written copy missing the receipt hook is never reported current.
- **Changed:** the check bed's fixture writes are context-managed, and new cases pin the collision (with a pinned clock,
  deterministically), the completeness rule, and the containment.

## 1.8.3 — 2026-09-12 — [#32](https://github.com/BinaryInfinityDev/claude-skills/pull/32)

Restricts the orchestrator after the incident in #31: a coordinator hoarded context, compacted, lost provenance,
back-filled itself as the authorizing actor, and had an executor re-issue the merge the guard had denied. Direction from
#30. 1.8.0–1.8.2 were consumed by three review rounds on the branch.

- **Fixed:** the subagent exemption tests `agent_id` alone. A `claude --agent orchestrator` main session carries
  `agent_type` and was bypassing the guard entirely.
- **Added:** on the orchestrator posture, `Read` only under `orchestrator_read_allowed` plus the operating-rules file
  and `paths.decisions`; `Glob` only inside `paths.plans`; `Grep`, `WebFetch`, `WebSearch`, `NotebookRead` and the
  GitHub content readers denied; state reads budgeted by `orchestrator_read_budget` (default 2 per turn) behind a lock;
  an allowed `Read` clamped to `orchestrator_read_lines`.
- **Added:** receipts. Every return leads with `outcome`, `object`, `evidence`, `actor`, `uncertainty`, `next_action`,
  `details` under `return_cap_chars`; a third hook, `model_tier_receipt.py`, files an oversized return under
  `paths.receipts` and blocks the stop once on `SubagentStop`, and cuts an oversized `Agent` return on `PostToolUse`.
- **Added:** tracker rows carry `ref`, `last`, `auth`, `next` and `details`; the steward reconciles state and never
  `auth`; a coordinator turn reconciles, routes, or dispatches — one of the three.
- **Added:** a compaction fragment on `SessionStart` with `source: "compact"` — provenance lost, remembered approvals
  unverified, reload the tracker only; `PostModelSwitch` wired; the brief marker varies every turn with the turn number,
  transcript growth, the reads counted last turn, and one rotating policy clause.
- **Added:** `authorization.merge_authority` (`owner` by default). Merging, auto-merge, the branch-writing MCP tools
  against a protected branch, and shell commands matching a linear tripwire are denied for every caller, subagents
  included, on every posture; every tier denial's footer says delegation confers no permission.
- **Added:** `install.py --cache-status` (exit 0 current / 1 stale / 2 missing / 3 no stamp) over every cached version
  directory and every install record; the skill's remote snippet gates on it and repairs with `claude plugin update`.
- **Added:** `scripts/check-hooks.sh`, a committed python3-only test bed for the hooks, installer, snippet and rule
  copies, run by the pre-commit. It never skips, and it tells an allowed call from a crashed hook.
- **Removed:** the `PostCompact` wiring — Claude Code discards a `PostCompact` hook's output, so it was never a carrier.

## 1.7.1 — 2026-09-10 — [#28](https://github.com/BinaryInfinityDev/claude-skills/pull/28)

- **Changed:** dispatch rows and the briefs built from them cite plan sections by heading anchor, never by line range;
  the tracker column is `plan section`.

## 1.7.0 — 2026-09-10 — [#27](https://github.com/BinaryInfinityDev/claude-skills/pull/27)

Measured in a consuming repo: implementation feedback round 5.

- **Fixed:** `install.py --print-hash` no longer hashes the `.in_use/<pid>` marker Claude Code writes into a cache, so
  the stamp's content hash can match a live cache.
- **Fixed:** the reminder renders a posture-neutral `pending` anchor when the transcript has no assistant entry yet, so
  an autonomous single-turn session sees the policy.
- **Fixed:** `mcp__github__enable_pr_auto_merge` and `disable_pr_auto_merge` are denied to coordinators; auto-merge is
  steward work.
- **Changed:** the shipped config seeds only `orchestrator_mode`, `bar_command` and `paths`; every other key takes the
  guard's defaults when absent; the installer reports keys that restate a default and list members missing from the
  defaults; `write_allowed` defaults to the three coordination-triple suffixes.
- **Changed:** the architect seeds the tracker's dispatch rows and the coordinator dispatches from rows; the policy rule
  states that it governs the main loop, not subagents; `models.orchestrator` is documented as a ceiling.

## 1.6.0 — 2026-09-05 — [#26](https://github.com/BinaryInfinityDev/claude-skills/pull/26)

- **Added:** every restricted role ends its description with a `Boundary:` clause, checked by
  `scripts/check-agent-boundaries.sh` in the pre-commit; descriptions are folded scalars so a `: ` cannot break the
  frontmatter.
- **Added:** the architect gets the GitHub read set; the steward gets the review-thread tools (reply and resolve).
- **Added:** `state-discipline` recognizes no-op events by construction — a stale `head_sha`, an echo of the session's
  own action, the subscription rulebook.

## 1.5.3 — 2026-09-04 — [#23](https://github.com/BinaryInfinityDev/claude-skills/pull/23)

1.4.0 (#22) and 1.5.0 (#24) landed on the branch, then 1.5.1–1.5.3 over three review rounds.

- **Added:** a `models` config block keyed by role. Denials, fragments and role files name the configured model; an
  unpinned spawn whose definition pin disagrees with the configured model is denied with the exact re-issue; hand
  installs bake the configured pin into the agent copies.
- **Added:** the orchestrator's model is enforced. A session on a tier above `models.orchestrator` disables the policy
  with a visible `DISABLED` notice every turn, never silently.
- **Changed:** one posture resolver serves both hooks; malformed config values fall back to the shipped defaults instead
  of failing open.
- **Changed:** seeded rules install create / keep / drift, writing `<name>.md.new` beside a diverged copy;
  `orchestrator_tools_allowed` applies on both denying postures; `runner_lock: null` is an explicit opt-out; the
  installer warns about a customized path that does not exist.
- **Added:** `scripts/check-rule-links.sh` — a shipped rule carries no relative links.

## 1.3.1 — 2026-09-02 — [#21](https://github.com/BinaryInfinityDev/claude-skills/pull/21)

Trial run 2. 1.3.0 was consumed on the branch.

- **Added:** the architect and the code reviewer write their own artifacts — plan amendments and review files — and
  briefs get the same cap returns already had.
- **Added:** a `paths` config block (`plans`, `decisions`, `reviews`, `timings`, `runner_lock`, `operating_rules`),
  deep-merged over defaults; the guard derives write globs from it.
- **Added:** the stamp's `content:` hash and `install.py --print-hash`; an `agent-operating-rules.md` seed installed
  create-only; the `multi-agent-hygiene` rule; the handoff-before-compaction clause; one sanctioned persistent
  verification worktree.
- **Changed:** `scout`, `devils-advocate` and `code-reviewer` get the GitHub read set; the steward creates and updates
  pull requests; every restricted role states its tool boundary.

## 1.2.1 — 2026-08-25 — [#18](https://github.com/BinaryInfinityDev/claude-skills/pull/18)

The coordinator longevity kit. 1.2.0 was consumed on the branch.

- **Added:** the `coordination-artifacts` and `state-discipline` rules — plan, tracker and append-only addendum matched
  to their access patterns; verify before asserting; silence on no-op events.
- **Added:** the `git-steward` agent (Sonnet 5): commits and reconciles coordination artifacts, takes dictated updates,
  and keeps branches tidy; its artifact set is defined by `write_allowed`.
- **Added:** the architect's consolidation duty with a line-count watermark; the orchestrator owns the artifact triple
  and the operating-rules convention.
- **Changed:** a Bash denial that involves git names the steward.

## 1.1.2 — 2026-08-23 — [#16](https://github.com/BinaryInfinityDev/claude-skills/pull/16)

Two defects from the first live trial. 1.1.0 and 1.1.1 were consumed on the branch.

- **Fixed:** denials name an agent id that resolves — bare for a project- or user-scope definition,
  `model-tier-policy:<role>` when the plugin serves it.
- **Added:** the skill's Claude Code Remote section, with a best-effort `SessionStart` install recipe.

## 1.0.1 — 2026-08-23 — [#15](https://github.com/BinaryInfinityDev/claude-skills/pull/15)

The first packaged release. 1.0.0 was the packaging commit on the same branch; the trial's operational gotchas moved it
to 1.0.1.

- **Added:** the plugin form — the skill, ten agents, both hooks and `hooks.json`; the reminder text lives in
  `hooks/context/` fragments the hook loads at fire time, so wording updates ride plugin updates.
- **Added:** `install.py` stamps `.claude/model-tier-policy.version` so the skill can flag drift after an update; the
  installer merges config keys instead of overwriting; `scripts/check-plugin-versions.sh` refuses a content change
  without a version change.

## Before packaging

The skill lived at `skills/model-tier-policy/` with the agents in a top-level catalog.

- 2026-08-22 — [#13](https://github.com/BinaryInfinityDev/claude-skills/pull/13): `build-runner` (a worktree per job,
  one instance at a time, a timed ledger), the `orchestrator` role with `orchestrator_mode`, the `code-reviewer` role,
  the `worktree-builds` rule; every path renamed to `model-tier-policy`.
- 2026-08-22 — [#7](https://github.com/BinaryInfinityDev/claude-skills/pull/7): the `senior-developer` role (Fable 5
  implementation for the change too entangled to hand off) and the `build-analyst` specialist (Haiku 4.5; a verdict or
  an honest `undetermined`, never a re-run); the agents become a top-level catalog.
- 2026-08-12 — [#5](https://github.com/BinaryInfinityDev/claude-skills/pull/5): writes are contained in the project root
  before any glob is matched; `subagent_type` is restricted to a bare name.
- 2026-08-12 — [#4](https://github.com/BinaryInfinityDev/claude-skills/pull/4): config layers defaults, user and
  project; duplicate hook copies are de-duplicated; every denial carries a footer; the `devils-advocate` role.
- 2026-08-12 — [#3](https://github.com/BinaryInfinityDev/claude-skills/pull/3): the skill — four roles, the
  always-loaded rule, the reminder hook, the `PreToolUse` guard, and the installer.

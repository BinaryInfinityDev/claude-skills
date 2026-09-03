# Build discipline — worktree builds and the push gate

Long build and test jobs run in a **dedicated git worktree** pinned at the commit under test, so development continues
in the primary tree while the suite grinds. Quick, known-cheap checks — a formatter, a linter, a focused test — run
in-tree; anything long enough to tie up the working tree does not.

## Worktree jobs

- The `build-runner` agent owns the worktree lifecycle where it is installed: create at the ref under test, run with
  output captured to a log file, remove when done. Without the agent, follow the same steps yourself.
- **A repo's own bar wins over invented invocations.** Where the repo supplies a verification entry point — a
  `bar_command` in `.claude/model-tier-policy.json`, or a script its docs name for exactly this — run that in the
  worktree instead of composing a build command, and treat its machine verdict line as authoritative. The lock, the
  timing ledger, and cleanup still apply around it.
- Name each worktree for the branch under test plus a random identifier (`<branch>-a1b2c3`), outside the primary tree.
  **A repo whose cold build dominates the run may instead keep one persistent verification worktree** (the
  `../.{repo}-verify` pattern) and reuse its build state: still lock-guarded, checked out to the ref under test for each
  run, and never used as a second development tree — it holds build products, not work.
- **One build job at a time per session**, coordinated through the runner lock (`paths.runner_lock` in
  `.claude/model-tier-policy.json`, default `.claude/build-runner.lock`; never committed — gitignore it). More
  concurrency means other sessions on other hosts, which requires the ref already pushed to a branch.
- **Always clean a per-run worktree up**, however the run ends. Copy out anything worth keeping — test reports, the key
  log — before removal, and return those paths with the results. A persistent worktree is cleaned of run artifacts
  (logs, reports) the same way, but keeps its build caches.
- Record completed runs in the timing ledger (`paths.timings`, default `.claude/build-timings.md`) so future runs know
  what "normal" looks like; a run far past its typical wall-clock is hung, not slow.

## Where fixes land

The build runs the code; it never fixes it. Results go back to whoever initiated the job, and that caller owns the fix:
an agent that called the build on its own work handles the results itself; a coordinator that called it on another
agent's behalf passes the results back to that agent; a coordinator that called it for its own reasons picks the
triager. Fixes land as **new commits at the tested ref**, and the commits made in the primary tree since then are
**rebased over them** — the same rebase-before-merge step semi-linear history already requires.

## The push gate

**Do not push a commit to the branch under review until the build covering it has completed green.** Development may run
ahead of the suite locally; the branch that feeds review and merge may not. This is a convention, not a hook — but it is
the difference between a reviewer reading proven code and reviewing a guess.

The one sanctioned exception: pushing unproven commits to a scratch or handoff branch so another session on another host
can run a build you cannot — that push serves the gate rather than violating it.

# Git etiquette — semi-linear history

This repository keeps **semi-linear** history: every pull request is rebased onto the base branch, then merged with a
merge commit. The merge commits form a spine; each one hangs the individual commits of one PR beneath it.

```
*   Merge pull request #4          <- one merge commit per PR
|\
| * Fix config scoping                 <- the PR's own commits, preserved
| * Add devils-advocate role
|/
*   Merge pull request #3
|\
| * Add model-tier-policy skill
|/
* Add Prettier config              <- pre-PR history
```

This is not the same as **linear** history (rebase and fast-forward, no merge commits), and not the same as
**squash-merging** (one commit per PR, individual commits discarded). Semi-linear keeps both properties that matter:
`git log --first-parent` reads as one line per PR, and the full log still shows how each PR got there.

## Working on a change

- **Never commit directly to the default branch.** Branch first, even for a one-line fix.
- Keep the branch current by **rebasing onto the base branch**, not by merging the base branch into it. A merge from
  base into a feature branch is what turns history into a lattice — it is the thing semi-linear exists to prevent.
  ```bash
  git fetch origin main
  git rebase origin/main
  ```
- Resolve conflicts during the rebase. If a rebase gets genuinely hairy, say so in the PR rather than papering over it
  with a merge from base.

## Commits

- Imperative subject, no trailing period, wrapped at ~72 characters: `Add role table to the rules file`, not
  `added role table` or `feat: role table`.
- The body explains **why**, not what — the diff already says what. Wrap at ~72.
- Each commit should build and pass whatever checks the repo has. A commit that only makes sense alongside the next one
  should be the same commit.
- Rewrite freely on your own unmerged branch — amend, squash, reorder to make the series readable before review.

## Merging

- **Merge commit only.** Do not squash-merge and do not rebase-and-merge; both discard the PR as a unit of history.
- The branch must be up to date with the base branch at merge time. If it is not, rebase and push again first.
- Delete the branch after merge.

## After a merge

A merged pull request is finished. Follow-up work starts from a **fresh branch off the updated base branch** — never
stack new commits on top of already-merged history, and never reopen a merged PR to carry new work.

```bash
git fetch origin main
git checkout -B <branch-name> origin/main
```

## Force-pushing

- `--force-with-lease`, never bare `--force`.
- Only onto your own branch, only while it is unmerged and unreviewed or you are the only reviewer.
- Never onto the default branch.
- If `--force-with-lease` reports stale info, **fetch and look** before overriding. The usual cause is that someone else
  pushed — but it is also what you see when the remote branch was deleted after a merge, in which case there is nothing
  to force over and a normal push is correct.

## Pull requests

- Open PRs **ready for review**, not as drafts, unless the PR is genuinely waiting on a decision from someone else.
- The description says what changed and why, and what was verified. If the repo has a PR template, fill in its headings.

## Enforcing this on GitHub

GitHub has no single "semi-linear" switch; it is three settings together.

| Setting                                          | Value   | Why                                                                                |
| ------------------------------------------------ | ------- | ---------------------------------------------------------------------------------- |
| Allow merge commits                              | **on**  | The merge commit is the spine                                                      |
| Allow squash merging                             | **off** | Squashing discards the PR's commits                                                |
| Allow rebase merging                             | **off** | Rebase-merging produces linear history, not semi-linear                            |
| Require branches to be up to date before merging | **on**  | This is what makes the result semi-linear rather than a lattice                    |
| Automatically delete head branches               | **on**  | Keeps follow-up work from stacking on merged history                               |
| Branch protection → **Require linear history**   | **off** | Despite the name, this _forbids merge commits_ — it enforces squash/rebase merging |

That last row is the trap: "Require linear history" sounds like it enforces this policy and does the opposite. Leave it
off and rely on "require branches to be up to date" instead.

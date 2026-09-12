# technical-writing — version history

Newest first. Each release entry names the pull request that merged it. **Outstanding** collects what is known and not
yet done.

## Outstanding

- The skill's `source:` names this repository. The attribution of the original text it was contributed from was left to
  be recorded when #19 landed and has not been (#21).

## 1.0.2 — 2026-09-12 — [#35](https://github.com/BinaryInfinityDev/claude-skills/pull/35)

- **Added:** this version history ([#34](https://github.com/BinaryInfinityDev/claude-skills/issues/34)), and the
  README's plugin table now links it. Nothing else changed: the pre-commit hook treats every file under the plugin as
  content, so adding the file took a patch bump, and the review round that reworded it took another — 1.0.1 was consumed
  on the branch.

## 1.0.0 — 2026-09-02 — [#21](https://github.com/BinaryInfinityDev/claude-skills/pull/21)

- **Added:** `write-in-simplified-technical-english` — ASD-STE100 Simplified Technical English for responses and
  documentation, as contributed in #19. Its description ships as a folded block scalar: the text carries a mid-sentence
  `: `, which in a plain multi-line YAML scalar silently drops the whole frontmatter.

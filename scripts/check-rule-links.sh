#!/usr/bin/env bash
# A shipped rule carries no relative links. Rules are installed verbatim into another tree (.claude/rules/), where a
# relative link — to a sibling rule, a README, a plugin file — dangles, and nothing downstream checks it. Refer to
# sibling rules by name in prose instead. Checked over the canonical catalog and every plugin's shipped copies.
set -euo pipefail
fail=0
while IFS= read -r file; do
  # Any link target with no scheme and no leading `#` is a relative path — `./x`, `../x`, `dir/x`, and the bare
  # sibling filename an author writes naturally (`[x](state-discipline.md)`). URLs carry a `:`; anchors start with `#`.
  if grep -nE '\]\([^):#][^):]*\)' "$file" >&2; then
    echo "error: $file contains a relative link — shipped rules must refer to other files by name in prose" >&2
    fail=1
  fi
done < <(find rules plugins/*/skills/*/references/rules -name '*.md' 2>/dev/null)
exit $fail

#!/usr/bin/env bash
# A plugin's content must not change without its version changing: installed copies and `claude plugin update`
# compare versions, so an un-bumped content change is invisible to every consumer — it reports "already at the
# latest version" over a stale cache. This bit during the #15 branch-pinned trial; hence the hook.
set -euo pipefail
fail=0
for plugin in plugins/*/; do
  name=$(basename "$plugin")
  manifest="${plugin}.claude-plugin/plugin.json"
  changed=$(git diff --cached --name-only -- "$plugin" | grep -v -F "$manifest" || true)
  [ -z "$changed" ] && continue
  old=$(git show HEAD:"$manifest" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || echo "")
  new=$(git show :"$manifest" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || echo "")
  if [ -n "$old" ] && [ "$old" = "$new" ]; then
    echo "error: plugin '$name' content changed but its version is still $new — bump $manifest" >&2
    echo "       (installed copies and 'claude plugin update' compare versions; an un-bumped change is invisible)" >&2
    fail=1
  fi
done
exit $fail

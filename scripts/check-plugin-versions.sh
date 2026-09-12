#!/usr/bin/env bash
# A plugin's content must not change without its version changing: installed copies and `claude plugin update`
# compare versions, so an un-bumped content change is invisible to every consumer — it reports "already at the
# latest version" over a stale cache. This bit during the #15 branch-pinned trial; hence the hook.
#
# A version must not change without its history changing either (#34): the plugin's CHANGELOG.md carries a
# `## <version>` entry, and the README's plugin table names the version and links that history. Both go stale
# silently otherwise, so they are checked against the index — the content a commit is about to record.
set -euo pipefail
fail=0
version_of() {
  git show "$1" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || echo ""
}
for plugin in plugins/*/; do
  name=$(basename "$plugin")
  manifest="${plugin}.claude-plugin/plugin.json"
  changed=$(git diff --cached --name-only -- "$plugin" | grep -v -F "$manifest" || true)
  old=$(version_of "HEAD:$manifest")
  new=$(version_of ":$manifest")
  if [ -z "$changed" ] && [ "$old" = "$new" ]; then
    continue
  fi
  if [ -n "$changed" ] && [ -n "$old" ] && [ "$old" = "$new" ]; then
    echo "error: plugin '$name' content changed but its version is still $new — bump $manifest" >&2
    echo "       (installed copies and 'claude plugin update' compare versions; an un-bumped change is invisible)" >&2
    fail=1
  fi
  [ -z "$new" ] && continue
  version_re=$(printf '%s' "$new" | sed 's/\./\\./g')
  if ! git show ":${plugin}CHANGELOG.md" 2>/dev/null | grep -qE "^## ${version_re}( |\$)"; then
    echo "error: plugin '$name' is at $new but ${plugin}CHANGELOG.md has no '## $new' entry — record the change" >&2
    fail=1
  fi
  if ! git show :README.md 2>/dev/null | grep -qE "^\| \`${name}\` *\| \[${version_re}\]\(plugins/${name}/CHANGELOG\.md\)"; then
    echo "error: README.md's plugin table does not show '$name' at $new linking plugins/$name/CHANGELOG.md" >&2
    fail=1
  fi
done
exit $fail

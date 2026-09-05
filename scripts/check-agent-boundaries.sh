#!/usr/bin/env bash
# A role whose tool list is narrower than its description implies must say so in the description. A coordinator picks a
# role from its description (`/agents`, the plugin listing) and never reads the body, so a boundary stated only in the
# body is still discovered by dispatching into the role (#25). Every agent that declares `tools:` therefore ends its
# description with a `Boundary:` clause — what the tools exclude and which role covers it — and a restricted role that
# carries `Bash` says that Bash is not `gh`, because a shell reads as "can reach GitHub" and generally cannot.
# Unrestricted roles (no `tools:` line) have no gap to state. Checked over every plugin's agents.
set -euo pipefail
fail=0
while IFS= read -r file; do
  # Frontmatter only — the block between the first two `---` lines. A value may be a plain scalar or a `>-` block spanning
  # several indented lines, so each top-level key's text is joined onto one tab-separated line before checking.
  fm=$(awk '
    NR == 1 { if ($0 != "---") exit; next }
    $0 == "---" { exit }
    /^[A-Za-z_-]+:/ { key = $0; sub(/:.*/, "", key); text[key] = substr($0, index($0, ":") + 1); order[++n] = key; next }
    key != "" { text[key] = text[key] " " $0 }
    END { for (i = 1; i <= n; i++) print order[i] "\t" text[order[i]] }
  ' "$file")
  tools=$(awk -F'\t' '$1 == "tools" { print $2 }' <<<"$fm")
  [ -z "$tools" ] && continue
  desc=$(awk -F'\t' '$1 == "description" { print $2 }' <<<"$fm")
  if ! grep -q 'Boundary:' <<<"$desc"; then
    echo "error: $file declares tools: but its description has no 'Boundary:' clause — say what the tools exclude and which role covers it" >&2
    fail=1
  fi
  if grep -qE '(^|[^A-Za-z_])Bash([^A-Za-z_]|$)' <<<"$tools" && ! grep -q '`gh`' <<<"$desc"; then
    echo "error: $file grants Bash to a restricted role but its description does not say Bash is not \`gh\`" >&2
    fail=1
  fi
done < <(find plugins/*/agents -name '*.md' 2>/dev/null)
exit $fail

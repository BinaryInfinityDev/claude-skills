#!/usr/bin/env bash
# A role whose tool list is narrower than its description implies must say so in the description. A coordinator picks a
# role from its description (`/agents`, the plugin listing) and never reads the body, so a boundary stated only in the
# body is still discovered by dispatching into the role (#25). Every agent that declares `tools:` therefore ends its
# description with a `Boundary:` clause — what the tools exclude and which role covers it — and a restricted role that
# carries `Bash` says that Bash is not `gh`, because a shell reads as "can reach GitHub" and generally cannot.
# Unrestricted roles (no `tools:` line) have no gap to state. Checked over every `.md` in every plugin's `agents/`
# directory, all of which are agent files.
#
# The clause puts `: ` into the description, which YAML reads as a nested mapping — or rejects — unless the value is a
# block (`>-`) or quoted scalar, and Claude Code drops an agent whose frontmatter does not parse as expected. So the check
# also fails a plain-scalar description containing `: ` or ` #` (a comment start, which silently truncates the text),
# and any agent file whose frontmatter it cannot read, find, or close: a file the check silently skipped is exactly the
# gap it exists to close.
set -euo pipefail
US=$'\037'
fail=0

# The value of one frontmatter key, joined across continuation lines (n=3), or the text on the key's own line (n=2).
field() {
  awk -v k="$1" -v n="$2" 'BEGIN { FS = "\037" } $1 == k { if (n == 2) { print $2 } else { s = substr($0, index($0, FS) + 1); print substr(s, index(s, FS) + 1) } }' <<<"$3"
}

while IFS= read -r file; do
  # Frontmatter only — the block between the first two `---` lines, CR and BOM stripped. Each top-level key becomes one
  # record: key, the value on the key's own line (which tells the scalar style), and the value joined across lines.
  # A `#` line is a YAML comment except inside a block scalar, where it is text; anything else that is neither a key
  # nor an indented continuation is not YAML the frontmatter parser will accept — reported after the scan, so a missing
  # closing fence is named as such rather than as the first body line.
  fm=$(awk -v US="$US" '
    { sub(/\r$/, "") }
    NR == 1 { sub(/^\357\273\277/, ""); if ($0 != "---") { print "NOFRONTMATTER"; done = 1; exit } opened = 1; next }
    $0 == "---" { closed = 1; exit }
    /^[A-Za-z_][A-Za-z0-9_-]*:/ {
      key = $0; sub(/:.*/, "", key)
      val = substr($0, index($0, ":") + 1); sub(/^[ \t]+/, "", val)
      first[key] = val; text[key] = val; order[++n] = key; next
    }
    /^[ \t]*#/ && (key == "" || first[key] !~ /^[>|]/) { next }
    /^[ \t]/ && key != "" { text[key] = text[key] " " $0; next }
    NF == 0 { next }
    { if (!malformed) malformed = NR; next }
    END {
      if (done) { } else if (!closed) print (opened ? "UNCLOSED" : "NOFRONTMATTER"); else if (malformed) print "MALFORMED " malformed
      for (i = 1; i <= n; i++) print order[i] US first[order[i]] US text[order[i]]
    }
  ' "$file" 2>/dev/null) || {
    echo "error: $file could not be read" >&2
    fail=1
    continue
  }
  case "$fm" in
    NOFRONTMATTER*) echo "error: $file has no frontmatter — an agent file starts with --- on its first line" >&2; fail=1; continue ;;
    UNCLOSED*) echo "error: $file frontmatter never closes — no second --- line" >&2; fail=1; continue ;;
    MALFORMED*) echo "error: $file frontmatter line ${fm#MALFORMED } is neither a key, an indented continuation, nor a comment — YAML will not parse it" >&2; fail=1; continue ;;
  esac
  desc=$(field description 3 "$fm")
  if [ -z "$desc" ]; then
    echo "error: $file has no description in its frontmatter" >&2
    fail=1
    continue
  fi
  case "$(field description 2 "$fm")" in
    '>'* | '|'* | '"'* | "'"*) ;; # block or quoted scalar: `: ` and ` #` are literal text
    *)
      if grep -qE ': |:$| #' <<<"$desc"; then
        echo "error: $file description is a plain scalar containing ': ' or ' #' — YAML reads a nested mapping, rejects it, or starts a comment there; write the description as a \`>-\` folded block" >&2
        fail=1
      fi
      ;;
  esac
  tools=$(field tools 3 "$fm")
  [ -z "$tools" ] && continue
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

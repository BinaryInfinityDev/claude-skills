#!/usr/bin/env bash
# The plugin's hooks and installer are Python with no CI, so this is their test bed, run per commit: python3 only, no
# network, a few seconds. It never skips — a case that cannot run fails — because a gate that reports PASS with cases
# omitted answers a different question than the one it appears to (#29; #31 finding 2).
set -euo pipefail
exec python3 "$(dirname "$0")/check_hooks.py" "$@"

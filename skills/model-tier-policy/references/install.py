#!/usr/bin/env python3
"""Install the model tier policy into a repository.

Copies the rules file, pinned-model agents, hooks, and default config into <target>/.claude/, then merges the hook
wiring into <target>/.claude/settings.json without disturbing existing settings.

Idempotent: re-running updates the shipped files and leaves your config and any other hooks alone.

    python3 install.py --target /path/to/repo [--user] [--force] [--dry-run]

    --user   install agents and hooks under ~/.claude instead (applies to every repo)
    --force  overwrite .claude/model-tiers.json, which is otherwise preserved once created
"""

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# (source relative to references/, destination relative to .claude/)
FILES = [
    ("rules/model-tiers.md", "rules/model-tiers.md"),
    ("agents/executor.md", "agents/executor.md"),
    ("agents/runner.md", "agents/runner.md"),
    ("agents/scout.md", "agents/scout.md"),
    ("agents/architect.md", "agents/architect.md"),
    ("hooks/model_tier_guard.py", "hooks/model_tier_guard.py"),
    ("hooks/model_tier_context.py", "hooks/model_tier_context.py"),
]
CONFIG = ("model-tiers.json", "model-tiers.json")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        sys.exit("error: %s is not valid JSON (%s) — fix or move it, then re-run." % (path, exc))


def hook_command(entry):
    return tuple(sorted(h.get("command", "") for h in entry.get("hooks", []) if isinstance(h, dict)))


def merge_hooks(settings, snippet):
    """Add snippet hook entries that aren't already present. Returns the number added."""
    added = 0
    hooks = settings.setdefault("hooks", {})
    for event, entries in snippet.get("hooks", {}).items():
        existing = hooks.setdefault(event, [])
        present = {hook_command(e) for e in existing if isinstance(e, dict)}
        for entry in entries:
            if hook_command(entry) not in present:
                existing.append(entry)
                added += 1
    return added


def main():
    parser = argparse.ArgumentParser(description="Install the model tier policy.")
    parser.add_argument("--target", default=os.getcwd(), help="repository root (default: cwd)")
    parser.add_argument("--user", action="store_true", help="install into ~/.claude instead of the repo")
    parser.add_argument("--force", action="store_true", help="overwrite an existing model-tiers.json")
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    args = parser.parse_args()

    root = os.path.expanduser("~") if args.user else os.path.abspath(args.target)
    if not os.path.isdir(root):
        sys.exit("error: %s is not a directory" % root)
    claude = os.path.join(root, ".claude")

    plan = []
    for src, dest in FILES + [CONFIG]:
        src_path = os.path.join(HERE, src)
        dest_path = os.path.join(claude, dest)
        if not os.path.exists(src_path):
            sys.exit("error: missing source file %s" % src_path)
        if (src, dest) == CONFIG and os.path.exists(dest_path) and not args.force:
            plan.append(("keep", dest_path))
            continue
        verb = "update" if os.path.exists(dest_path) else "create"
        plan.append((verb, dest_path, src_path))

    settings_path = os.path.join(claude, "settings.json")
    settings = load_json(settings_path)
    snippet = load_json(os.path.join(HERE, "settings-snippet.json"))
    if args.user:
        # A user-level install lives outside any one project, so $CLAUDE_PROJECT_DIR would point at the wrong tree.
        snippet = json.loads(json.dumps(snippet).replace("$CLAUDE_PROJECT_DIR", "$HOME"))
    added = merge_hooks(settings, snippet)

    for item in plan:
        print("  %-6s %s" % (item[0], item[1]))
    print("  %-6s %s (%d hook entr%s added)" % ("merge", settings_path, added, "y" if added == 1 else "ies"))

    if args.dry_run:
        print("\ndry run — nothing written")
        return

    for item in plan:
        if item[0] == "keep":
            continue
        _, dest_path, src_path = item
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copyfile(src_path, dest_path)
        if dest_path.endswith(".py"):
            os.chmod(dest_path, 0o755)

    if added:
        os.makedirs(claude, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")

    print(
        "\nInstalled. Start a new session (hooks and rules load at launch) and accept the workspace trust prompt.\n"
        "Verify: `/context` lists the rules file, and asking a Fable session to edit a file is denied.\n"
        "Disable at any time with MODEL_TIER_POLICY=off or \"enabled\": false in .claude/model-tiers.json."
    )


if __name__ == "__main__":
    main()

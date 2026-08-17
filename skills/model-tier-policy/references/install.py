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
    ("agents/senior-developer.md", "agents/senior-developer.md"),
    ("agents/devils-advocate.md", "agents/devils-advocate.md"),
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


def policy_installed(root):
    """True when a settings.json under root already wires up either of our hooks."""
    settings = load_json(os.path.join(root, ".claude", "settings.json"))
    for entries in (settings.get("hooks") or {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            for command in hook_command(entry if isinstance(entry, dict) else {}):
                if "model_tier_guard.py" in command or "model_tier_context.py" in command:
                    return True
    return False


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

    other = os.path.abspath(args.target) if args.user else os.path.expanduser("~")
    if os.path.normpath(other) != os.path.normpath(root) and policy_installed(other):
        print(
            "warning: the policy is already installed at %s.\n"
            "         Installing at both scopes runs two copies of each hook per event. The hooks de-duplicate, so\n"
            "         the read budget and reminder cadence stay correct, but the second copy is wasted work — and\n"
            "         two configs means edits to one silently do nothing. Pick one scope and remove the other.\n"
            % os.path.join(other, ".claude")
        )

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
        "\nInstalled. No session restart needed — the hooks are live on the next tool call, so a premium session will\n"
        "be denied its next edit or build immediately. Accept the workspace trust prompt if asked.\n"
        "The rules file loads at your next session start; until then the reminder hook carries the same policy, so\n"
        "nothing is unenforced in the meantime.\n"
        "Verify: ask the premium tier to run a build — it should be denied with the delegation to use instead.\n"
        "Disable at any time with MODEL_TIER_POLICY=off or \"enabled\": false in .claude/model-tiers.json."
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Install the model tier policy into a repository.

Copies the rules file, pinned-model agents, hooks, and default config into <target>/.claude/, then merges the hook
wiring into <target>/.claude/settings.json without disturbing existing settings.

Idempotent: re-running updates the shipped files and leaves your config and any other hooks alone.

    python3 install.py --target /path/to/repo [--user] [--force] [--dry-run]

    --user   install agents and hooks under ~/.claude instead (applies to every repo)
    --force  reset .claude/model-tier-policy.json to shipped defaults (a .bak is written first); plain re-runs
             only add newly shipped keys and never touch values you set
"""

import argparse
import datetime
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The plugin root carries the components that are not skill-private: agents and hooks sit beside the skill so the
# plugin loads them natively, and this installer sources them from there for repos that install by hand instead.
PLUGIN_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
AGENTS_SRC = os.path.join(PLUGIN_ROOT, "agents")
HOOKS_SRC = os.path.join(PLUGIN_ROOT, "hooks")

# (source relative to references/, destination relative to .claude/)
FILES = [
    ("rules/model-tier-policy.md", "rules/model-tier-policy.md"),
    # For each rule below, the canonical copy lives in the repo-level rules/ catalog; these ship with the plugin so an
    # installed plugin is self-contained. Keep each pair in sync (see CLAUDE.md).
    ("rules/build-discipline/worktree-builds.md", "rules/build-discipline/worktree-builds.md"),
    ("rules/coordination/coordination-artifacts.md", "rules/coordination/coordination-artifacts.md"),
    ("rules/coordination/state-discipline.md", "rules/coordination/state-discipline.md"),
    ("rules/coordination/multi-agent-hygiene.md", "rules/coordination/multi-agent-hygiene.md"),
]
# Seed for the operating-rules file — created only when the configured path has nothing, never updated: the file is the
# repo's own once it exists. Shipping a skeleton matters because an absent designated home is what invites briefs to
# restate their constants inline.
OPERATING_RULES_TEMPLATE = "agent-operating-rules.md"
# (source relative to HOOKS_SRC, destination relative to .claude/)
HOOK_FILES = [
    ("model_tier_guard.py", "hooks/model_tier_guard.py"),
    ("model_tier_context.py", "hooks/model_tier_context.py"),
    # The reminder hook is a loader; these fragments are the text it injects, resolved beside the script.
    ("context/premium.md", "hooks/context/premium.md"),
    ("context/premium-brief.md", "hooks/context/premium-brief.md"),
    ("context/orchestrator.md", "hooks/context/orchestrator.md"),
    ("context/orchestrator-brief.md", "hooks/context/orchestrator-brief.md"),
    ("context/worker.md", "hooks/context/worker.md"),
    ("context/worker-brief.md", "hooks/context/worker-brief.md"),
]
# (source relative to AGENTS_SRC, destination relative to .claude/)
AGENT_FILES = [
    ("build-analyst.md", "agents/build-analyst.md"),
    ("build-runner.md", "agents/build-runner.md"),
    ("code-reviewer.md", "agents/code-reviewer.md"),
    ("executor.md", "agents/executor.md"),
    ("orchestrator.md", "agents/orchestrator.md"),
    ("runner.md", "agents/runner.md"),
    ("scout.md", "agents/scout.md"),
    ("architect.md", "agents/architect.md"),
    ("senior-developer.md", "agents/senior-developer.md"),
    ("devils-advocate.md", "agents/devils-advocate.md"),
    ("git-steward.md", "agents/git-steward.md"),
]
CONFIG = ("model-tier-policy.json", "model-tier-policy.json")
# Provenance stamp: which plugin version these installed files came from, so the skill can flag drift after a plugin
# update and offer a re-run. Deliberately a text file, not part of the user-owned config.
STAMP = "model-tier-policy.version"


def plugin_version():
    """The version from the plugin manifest this installer ships inside, or 'unversioned' for a bare checkout."""
    try:
        with open(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version") or "unversioned"
    except Exception:
        return "unversioned"


def content_hash():
    """A short hash over the plugin's tracked content, so drift is detectable when the version number is not moving.

    A branch-pinned install makes every push a de facto release, but the version in the manifest only changes when
    someone bumps it — so two different contents can share a version, and a version compare reports "current" over a
    stale cache. Hashing relative path + bytes for every file under the plugin root gives the comparison the version
    number cannot: run with --print-hash in a plugin cache directory and in the source checkout, and different hashes
    mean different content, whatever the versions claim.
    """
    import hashlib

    digest = hashlib.sha256()
    entries = []
    # The walk must stay lazy for the dirs mutation to prune traversal — sorted(os.walk(...)) would materialize
    # every directory before the loop runs, turning the prune into dead code. Determinism comes from sorting the
    # collected paths instead.
    for base, dirs, files in os.walk(PLUGIN_ROOT):
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")
        for name in files:
            if not name.endswith(".pyc"):
                entries.append(os.path.join(base, name))
    for path in sorted(entries):
        rel = os.path.relpath(path, PLUGIN_ROOT)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        try:
            with open(path, "rb") as fh:
                digest.update(fh.read())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def stamp_source():
    """Where this install came from, in terms a reader of the committed stamp can act on.

    Never a filesystem path: the stamp is meant to be committed, and an absolute path under one person's home is
    meaningless to everyone else and churns on every re-install. The marketplace name is derived from the plugin
    cache layout (~/.claude/plugins/cache/{marketplace}/{plugin}/{version}); anything else is a checkout.
    """
    parts = PLUGIN_ROOT.split(os.sep)
    try:
        cache_index = len(parts) - 1 - parts[::-1].index("cache")
        if parts[cache_index - 1] == "plugins" and cache_index + 1 < len(parts):
            return "%s marketplace" % parts[cache_index + 1]
    except ValueError:
        pass
    return "checkout"
# Pre-rename paths (relative to .claude/) still found in repos installed before the policy was named consistently.
LEGACY_CONFIG = "model-tiers.json"
LEGACY_RULE = "rules/model-tiers.md"


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


def strip_policy_hooks(settings):
    """Remove this policy's hook entries from settings, leaving everyone else's alone. Returns how many dropped."""
    removed = 0
    hooks = settings.get("hooks") or {}
    for event in list(hooks.keys()):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept = []
        for entry in entries:
            commands = hook_command(entry if isinstance(entry, dict) else {})
            if any("model_tier_guard.py" in c or "model_tier_context.py" in c for c in commands):
                removed += 1
            else:
                kept.append(entry)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks and "hooks" in settings:
        del settings["hooks"]
    return removed


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
    parser.add_argument(
        "--force",
        action="store_true",
        help="reset model-tier-policy.json to shipped defaults, backing the old file up first — without this, "
        "re-runs only add newly shipped keys and never touch values you set",
    )
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    parser.add_argument(
        "--print-hash",
        action="store_true",
        help="print this plugin directory's version and content hash, then exit — run it in an installed cache and "
        "in a checkout to tell whether a branch-pinned install drifted at an unchanged version",
    )
    parser.add_argument(
        "--files-only",
        action="store_true",
        help="install only the pieces the plugin cannot serve (rules, config, stamp) and remove any hook/agent "
        "copies from an earlier full install — the default when running from an installed plugin",
    )
    parser.add_argument("--full", action="store_true", help="copy hooks and agents even when running from a plugin")
    args = parser.parse_args()

    if args.print_hash:
        print("model-tier-policy %s content %s" % (plugin_version(), content_hash()))
        return

    # Local copies do not defer to the plugin: a project-scope agent file shadows the plugin's on a name collision,
    # and a doubled reminder hook injects whichever copy fires first. So when this installer runs from inside an
    # installed plugin, the plugin is serving the hooks and agents already, and the right install is files-only —
    # plus removing any copies an earlier hand-install left to go stale.
    in_plugin_cache = (os.sep + os.path.join("plugins", "cache") + os.sep) in PLUGIN_ROOT
    files_only = args.files_only or (in_plugin_cache and not args.full)

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

    if not os.path.isdir(AGENTS_SRC) or not os.path.isdir(HOOKS_SRC):
        sys.exit(
            "error: agent or hook sources not found under %s — run install.py from a full model-tier-policy "
            "plugin directory (the skill directory alone does not carry the agents and hooks)" % PLUGIN_ROOT
        )

    # Migrate installs that predate the consistent model-tier-policy naming: the config is renamed so its contents
    # survive, and the superseded rules file is removed so both copies don't load into every session.
    migrations = []
    legacy_config = os.path.join(claude, LEGACY_CONFIG)
    if os.path.exists(legacy_config) and not os.path.exists(os.path.join(claude, CONFIG[1])):
        migrations.append(("rename", legacy_config, os.path.join(claude, CONFIG[1])))
    legacy_rule = os.path.join(claude, LEGACY_RULE)
    if os.path.exists(legacy_rule):
        migrations.append(("remove", legacy_rule, "superseded by the model-tier-policy name"))

    plan = []
    sources = [(os.path.join(HERE, src), dest) for src, dest in FILES]
    if files_only:
        # The plugin serves hooks and agents; copies left from an earlier full install would shadow it, so they go.
        for _src, dest in HOOK_FILES + AGENT_FILES:
            stale = os.path.join(claude, dest)
            if os.path.exists(stale):
                migrations.append(("remove", stale, "the plugin serves this now"))
    else:
        sources += [(os.path.join(HOOKS_SRC, src), dest) for src, dest in HOOK_FILES]
        sources += [(os.path.join(AGENTS_SRC, src), dest) for src, dest in AGENT_FILES]
    for src_path, dest in sources:
        dest_path = os.path.join(claude, dest)
        if not os.path.exists(src_path):
            sys.exit("error: missing source file %s" % src_path)
        verb = "update" if os.path.exists(dest_path) else "create"
        plan.append((verb, dest_path, src_path))

    # The config is the user's file, not ours: re-runs only ADD newly shipped keys (so a repo picks up e.g. a new
    # bar_command default without losing the values it set), and --force — the full reset — backs the file up and
    # says which local values it is discarding. A silent reset of repo-specific config is how a trial site lost its
    # bar command to a habitual --force.
    config_src = os.path.join(HERE, CONFIG[0])
    config_dest = os.path.join(claude, CONFIG[1])
    shipped_cfg = load_json(config_src)
    rename_pending = any(v == "rename" and n == config_dest for v, _o, n in migrations)
    existing_cfg_path = config_dest if os.path.exists(config_dest) else (legacy_config if rename_pending else None)
    stale_members = {}
    if existing_cfg_path is None:
        config_action = "create"
        config_note = ""
    elif args.force:
        user_cfg = load_json(existing_cfg_path)
        overridden = sorted(k for k in user_cfg if user_cfg[k] != shipped_cfg.get(k, object()))
        config_action = "reset"
        config_note = " (backup: %s.bak%s)" % (
            os.path.basename(config_dest),
            "; discarding local: " + ", ".join(overridden) if overridden else "",
        )
    else:
        user_cfg = load_json(existing_cfg_path)
        new_keys = [k for k in shipped_cfg if k not in user_cfg]
        config_action = "merge" if new_keys else "keep"
        config_note = " (new key%s: %s)" % ("" if len(new_keys) == 1 else "s", ", ".join(new_keys)) if new_keys else ""
        # List values are the user's whole and entire once set: silently re-adding a member they removed would be the
        # --force lesson again. But a shipped member they simply never received (added after their install) looks
        # identical, so the skipped members are reported — the user decides which case each one is.
        for key in shipped_cfg:
            if isinstance(shipped_cfg[key], list) and isinstance(user_cfg.get(key), list):
                missing = [m for m in shipped_cfg[key] if m not in user_cfg[key]]
                if missing:
                    stale_members[key] = missing

    settings_path = os.path.join(claude, "settings.json")
    settings = load_json(settings_path)
    settings_changed = 0
    if files_only:
        settings_changed = strip_policy_hooks(settings)
        settings_note = "%d hook entr%s removed — the plugin wires its own" % (
            settings_changed,
            "y" if settings_changed == 1 else "ies",
        )
    else:
        snippet = load_json(os.path.join(HERE, "settings-snippet.json"))
        if args.user:
            # A user-level install lives outside any one project, so $CLAUDE_PROJECT_DIR would point at the wrong tree.
            snippet = json.loads(json.dumps(snippet).replace("$CLAUDE_PROJECT_DIR", "$HOME"))
        settings_changed = merge_hooks(settings, snippet)
        settings_note = "%d hook entr%s added" % (settings_changed, "y" if settings_changed == 1 else "ies")

    if files_only:
        print(
            "files-only install%s: the plugin serves the skill, agents, and hooks; laying down rules, config, "
            "and the version stamp." % (" (running from an installed plugin)" if in_plugin_cache else "")
        )
    for verb, old, new in migrations:
        if verb == "rename":
            print("  %-6s %s -> %s" % (verb, old, os.path.basename(new)))
        else:
            print("  %-6s %s (%s)" % (verb, old, new))
    # The operating-rules seed goes wherever the repo's config points paths.operating_rules; a config the installer is
    # about to create or reset means the shipped default applies.
    paths_cfg = dict(shipped_cfg.get("paths") or {})
    if existing_cfg_path is not None and not args.force:
        user_paths = load_json(existing_cfg_path).get("paths")
        if isinstance(user_paths, dict):
            paths_cfg.update({k: v for k, v in user_paths.items() if isinstance(v, str) and v})
    op_rules_src = os.path.join(HERE, OPERATING_RULES_TEMPLATE)
    op_rules_dest = os.path.join(root, paths_cfg.get("operating_rules") or ".claude/agent-operating-rules.md")
    op_rules_create = os.path.exists(op_rules_src) and not os.path.exists(op_rules_dest)

    for item in plan:
        print("  %-6s %s" % (item[0], item[1]))
    print("  %-6s %s%s" % (config_action, config_dest, config_note))
    for key, members in sorted(stale_members.items()):
        print(
            "  note   %s: shipped member%s not in your list (left alone — add if wanted): %s"
            % (key, "" if len(members) == 1 else "s", ", ".join(str(m) for m in members))
        )
    print("  %-6s %s (operating-rules seed%s)" % ("create" if op_rules_create else "keep", op_rules_dest,
                                                  "" if op_rules_create else " — yours once it exists"))
    stamp_path = os.path.join(claude, STAMP)
    print("  %-6s %s (%s)" % ("update" if os.path.exists(stamp_path) else "create", stamp_path, plugin_version()))
    print("  %-6s %s (%s)" % ("merge", settings_path, settings_note))

    if args.dry_run:
        print("\ndry run — nothing written")
        return

    for verb, old, new in migrations:
        if verb == "rename":
            os.replace(old, new)
        else:
            os.remove(old)
    if files_only:
        for leftover in ("hooks/context", "hooks", "agents"):
            try:
                os.rmdir(os.path.join(claude, leftover))  # only if empty — a dir with anyone else's files stays
            except OSError:
                pass

    for item in plan:
        if item[0] == "keep":
            continue
        _, dest_path, src_path = item
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copyfile(src_path, dest_path)
        if dest_path.endswith(".py"):
            os.chmod(dest_path, 0o755)

    os.makedirs(claude, exist_ok=True)
    if config_action == "create":
        shutil.copyfile(config_src, config_dest)
    elif config_action == "merge":
        merged = load_json(config_dest)  # the migration has run, so the user's file is at its current path now
        for key, value in shipped_cfg.items():
            if key not in merged:
                merged[key] = value
        with open(config_dest, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
            fh.write("\n")
    elif config_action == "reset":
        shutil.copyfile(config_dest, config_dest + ".bak")
        shutil.copyfile(config_src, config_dest)

    if op_rules_create:
        os.makedirs(os.path.dirname(op_rules_dest) or ".", exist_ok=True)
        shutil.copyfile(op_rules_src, op_rules_dest)

    os.makedirs(claude, exist_ok=True)
    with open(stamp_path, "w", encoding="utf-8") as fh:
        fh.write(
            "model-tier-policy %s\ncontent: %s\nsource: %s\ninstalled: %s\n"
            % (
                plugin_version(),
                content_hash(),
                stamp_source(),
                datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            )
        )

    if settings_changed:
        os.makedirs(claude, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")

    if files_only:
        print(
            "\nInstalled the file-shaped pieces; the plugin serves the skill, agents, and hooks live, so those never\n"
            "drift. Re-run this after a plugin update to bring the rules file and config up to the new version.\n"
            "Disable at any time with MODEL_TIER_POLICY=off or \"enabled\": false in .claude/model-tier-policy.json."
        )
    else:
        print(
            "\nInstalled. No session restart needed — the hooks are live on the next tool call, so a premium session "
            "will\nbe denied its next edit or build immediately. Accept the workspace trust prompt if asked.\n"
            "The rules file loads at your next session start; until then the reminder hook carries the same policy, "
            "so\nnothing is unenforced in the meantime.\n"
            "Verify: ask the premium tier to run a build — it should be denied with the delegation to use instead.\n"
            "Disable at any time with MODEL_TIER_POLICY=off or \"enabled\": false in .claude/model-tier-policy.json."
        )


if __name__ == "__main__":
    main()

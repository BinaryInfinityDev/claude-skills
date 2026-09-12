#!/usr/bin/env python3
"""Caps what a subagent hands back to a coordinating session — the receipt hook.

"Return a concise result" in a brief is advisory, and an executor that returns a 400-line diff has just spent the
coordinator's context on text it did not need. This hook makes the cap mechanical, at the source:

  - SubagentStop: when the parent session is on a coordinating posture (premium or orchestrator) and the subagent's
    final message exceeds `return_cap_chars`, the full text is filed under `paths.receipts` and the stop is blocked
    once, with the instruction to return the seven-line receipt that names the file. `stop_hook_active` guards the
    loop: the second stop is never blocked, whatever its length.
  - PostToolUse on Agent/Task: the backstop. A return that still exceeds the cap is filed the same way, cut down in
    the tool output where the tool's output shape allows it, and one line of context says where the full text went.

The receipts location is a handle, not a read — it sits outside the orchestrator's read allowlist by design. Every
failure path exits 0 with no output: a hook that breaks a subagent's return is worse than one that lets a long one by.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from model_tier_guard import cfg_int, live_model, load_config, posture, project_dir, resolved_paths
except Exception:  # pragma: no cover - guard missing means policy is not installed
    sys.exit(0)

RECEIPT_FIELDS = "outcome, object, evidence, actor, uncertainty, next_action, details"


def coordinating(cfg, payload):
    """True when the session that receives this return is a coordinator — the postures whose context the cap protects.

    `transcript_path` is the main session's transcript on every event this hook handles, so the parent's model, and
    with it the posture, resolves the same way the guard resolves it.
    """
    model = live_model(payload.get("transcript_path"))
    return posture(cfg, model) in ("premium", "orchestrator")


def file_receipt(root, cfg, payload, name, text):
    """Write the full return under the receipts directory; returns the repo-relative path, or None."""
    base = (resolved_paths(cfg).get("receipts") or "").rstrip("/")
    if not base:
        return None
    session = re.sub(r"[^A-Za-z0-9._-]", "", str(payload.get("session_id") or "session"))[:64] or "session"
    name = re.sub(r"[^A-Za-z0-9._-]", "", str(name))[:64] or "return"
    directory = os.path.join(root, base, session)
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "%s-%d.md" % (name, int(time.time())))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "# Filed return — %s\n\nagent: %s\nfiled: %s\nchars: %d\n\n---\n\n"
                % (name, payload.get("agent_type") or "unknown", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), len(text))
            )
            fh.write(text)
    except Exception:
        return None
    return os.path.relpath(path, root)


def response_text(response):
    """The text a tool response carries, for measuring — a string, a text-block list, or a dict's longest string."""
    if isinstance(response, str):
        return response
    if isinstance(response, list):
        parts = [block.get("text") for block in response if isinstance(block, dict) and isinstance(block.get("text"), str)]
        return "\n".join(parts) if parts else json.dumps(response)
    if isinstance(response, dict):
        strings = [value for value in response.values() if isinstance(value, str)]
        return max(strings, key=len) if strings else json.dumps(response)
    return "" if response is None else str(response)


def cut(text, cap, path):
    trailer = "\n\n[model tier policy: return cut to %d of %d chars; the full text is at %s]" % (cap, len(text), path or "(not filed)")
    return text[:cap] + trailer


def replaced_response(response, cap, path):
    """The tool response with its text cut down, in the same shape — a mismatched shape is ignored by Claude Code,
    which is the safe failure: the original output stands and the context line still says where the full text is."""
    if isinstance(response, str):
        return cut(response, cap, path)
    if isinstance(response, list):
        out = []
        for block in response:
            if isinstance(block, dict) and isinstance(block.get("text"), str) and len(block["text"]) > cap:
                block = dict(block, text=cut(block["text"], cap, path))
            out.append(block)
        return out
    if isinstance(response, dict):
        strings = [(key, value) for key, value in response.items() if isinstance(value, str)]
        if not strings:
            return None
        key, value = max(strings, key=lambda item: len(item[1]))
        return dict(response, **{key: cut(value, cap, path)})
    return None


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)
    if os.environ.get("MODEL_TIER_POLICY", "").lower() in ("off", "0", "false"):
        sys.exit(0)

    root = project_dir(payload)
    cfg = load_config(root)
    if not cfg.get("enabled", True):
        sys.exit(0)
    cap = cfg_int(cfg, "return_cap_chars")
    if cap <= 0 or not coordinating(cfg, payload):
        sys.exit(0)

    event = payload.get("hook_event_name")

    if event == "SubagentStop":
        if payload.get("stop_hook_active"):
            sys.exit(0)  # already continuing after a block: never a second one
        text = payload.get("last_assistant_message")
        if not isinstance(text, str) or len(text) <= cap:
            sys.exit(0)
        path = file_receipt(root, cfg, payload, payload.get("agent_id") or "agent", text)
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        "Model tier policy: your return is %d characters and the coordinator takes at most %d. The full "
                        "text is saved at %s — nothing is lost. Reply with the receipt only, seven lines: %s — with "
                        "`details:` naming that path. No file contents, no transcripts, no diffs; the coordinator acts "
                        "on the receipt and hands the path on."
                        % (len(text), cap, path or "(could not be filed — shorten it yourself)", RECEIPT_FIELDS)
                    ),
                }
            )
        )
        sys.exit(0)

    if event == "PostToolUse" and payload.get("tool_name") in ("Agent", "Task"):
        response = payload.get("tool_response")
        text = response_text(response)
        if len(text) <= cap:
            sys.exit(0)
        path = file_receipt(root, cfg, payload, payload.get("tool_use_id") or "return", text)
        output = {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "[model tier policy: the return above was %d chars, over the %d-char receipt cap; its full text is at "
                "%s. Act on the receipt — outcome, object, evidence, actor, uncertainty, next_action, details — and "
                "treat the path as a handle, not a read. If the receipt is missing, re-brief with the cap.]"
                % (len(text), cap, path or "(could not be filed)")
            ),
        }
        replacement = replaced_response(response, cap, path)
        if replacement is not None:
            output["updatedToolOutput"] = replacement
        print(json.dumps({"hookSpecificOutput": output}))
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

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
    """Write the full return under the receipts directory; returns the repo-relative path, or None.

    The file is created exclusively, never truncated: parallel dispatch ends subagents in the same second, the
    fallback names (`agent`, `return`) are shared, and an overwrite would leave an earlier receipt's `details:` path
    pointing at another agent's text. The name carries a microsecond UTC stamp and, on a collision, a numeric suffix.
    """
    base = (resolved_paths(cfg).get("receipts") or "").rstrip("/")
    if not base:
        return None
    session = re.sub(r"[^A-Za-z0-9._-]", "", str(payload.get("session_id") or "session"))[:64] or "session"
    name = re.sub(r"[^A-Za-z0-9._-]", "", str(name))[:64] or "return"
    directory = os.path.join(root, base, session)
    try:
        os.makedirs(directory, exist_ok=True)
        now = time.time()
        stamp = "%s.%06d" % (time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)), int((now - int(now)) * 1000000))
        for attempt in range(1000):
            path = os.path.join(directory, "%s-%s%s.md" % (name, stamp, "-%d" % attempt if attempt else ""))
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                continue
            try:
                fh = os.fdopen(fd, "w", encoding="utf-8")
            except Exception:
                os.close(fd)  # the descriptor is ours until the file object owns it
                raise
            with fh:
                fh.write(
                    "# Filed return — %s\n\nagent: %s\nfiled: %s\nchars: %d\n\n---\n\n"
                    % (name, payload.get("agent_type") or "unknown", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), len(text))
                )
                fh.write(text)
            break
        else:
            return None
    except Exception:
        return None
    return os.path.relpath(path, root)


# The keys of a dict response that carry the subagent's text, in the order tried. The Agent tool's response is a dict
# with the return under `content` (a list of text blocks) beside the coordinator's own `prompt` — which must never be
# what gets measured or cut: a long brief is not a long return.
TEXT_KEYS = ("content", "text", "result", "output")


def response_body(response):
    """(the part of a response that is the subagent's text, its key) — the key is None for a bare string or list."""
    if isinstance(response, dict):
        for key in TEXT_KEYS:
            if key in response and isinstance(response[key], (str, list)):
                return response[key], key
        return None, None
    return response, None


def response_text(response):
    """The text a tool response carries, for measuring — a string, a text-block list, or a dict's text field."""
    body, _key = response_body(response)
    if isinstance(body, str):
        return body
    if isinstance(body, list):
        parts = [block.get("text") for block in body if isinstance(block, dict) and isinstance(block.get("text"), str)]
        return "\n".join(parts)
    return ""


def cut(text, cap, path, total=None):
    trailer = "\n\n[model tier policy: return cut to %d of %d chars; the full text is at %s]" % (
        cap, total if total is not None else len(text), path or "(not filed)")
    return text[:cap] + trailer


def cut_body(body, cap, path, total):
    """The body cut to the cap — for a block list, cumulatively: the cap is a budget over the whole return, the block
    that crosses it is cut to what remains, and every block after it is dropped. Cutting each block on its own let a
    return of many short blocks pass whole while being announced as over the cap."""
    if isinstance(body, str):
        return cut(body, cap, path, total)
    if isinstance(body, list):
        # Budgeted the way it is measured: the blocks joined by a newline, so the separator counts one character.
        out, used, first = [], 0, True
        for block in body:
            if not (isinstance(block, dict) and isinstance(block.get("text"), str)):
                out.append(block)
                continue
            text = block["text"]
            separator = 0 if first else 1
            first = False
            if used + separator + len(text) <= cap:
                out.append(block)
                used += separator + len(text)
                continue
            out.append(dict(block, text=cut(text, max(cap - used - separator, 0), path, total)))
            return out
        return out
    return None


def replaced_response(response, cap, path):
    """The tool response with its text cut down, in the same shape — a mismatched shape is ignored by Claude Code,
    which is the safe failure: the original output stands and the context line still says where the full text is.
    Only the text field is touched; every other field, the coordinator's `prompt` included, is echoed untouched."""
    body, key = response_body(response)
    replacement = cut_body(body, cap, path, len(response_text(response)))
    if replacement is None:
        return None
    if key is None:
        return replacement
    return dict(response, **{key: replacement})


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
        if os.environ.get("MODEL_TIER_DEBUG"):  # surface the traceback for the check; still fail open
            import traceback

            traceback.print_exc()
        sys.exit(0)

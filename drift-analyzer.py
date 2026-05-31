#!/usr/bin/env python3
"""
Drift analyzer — counts drift signals from the current session JSONL transcript
and merges drift fields into gate-state.json.

Called from prompt-gate.sh on every UserPromptSubmit hook.

Signals:
  1. Gate denials — the instance tried to act without permission (gate_blocked count)
  2. Unauthorized files — tool_use calls targeting files not mentioned in the last user directive

Reads JSONL directly — no SQLite dependency.
"""

import json
import re
import glob
from pathlib import Path

GATE_DIR = Path(__file__).parent
STATE_FILE = GATE_DIR / "gate-state.json"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Window: inspect the last N entries from the most recent session
WINDOW_SIZE = 30

# Threshold: drift_halt = True when drift_score >= this
DRIFT_THRESHOLD = 3


def find_latest_jsonl():
    """Find the most recently modified JSONL file under ~/.claude/projects/."""
    if not CLAUDE_PROJECTS_DIR.exists():
        return None
    jsonl_files = list(CLAUDE_PROJECTS_DIR.rglob("*.jsonl"))
    if not jsonl_files:
        return None
    return max(jsonl_files, key=lambda p: p.stat().st_mtime)


def read_recent_entries(jsonl_path, count):
    """Read the last N entries from a JSONL file efficiently."""
    entries = []
    # Read from the end of file
    with open(jsonl_path, "r", encoding="utf-8") as f:
        # Read all lines (JSONL files are line-delimited)
        lines = f.readlines()

    # Parse the last `count` valid entries
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("type") in ("user", "assistant"):
                entries.append(entry)
                if len(entries) >= count:
                    break
        except json.JSONDecodeError:
            continue

    entries.reverse()
    return entries


def extract_tool_uses(entry):
    """Extract tool_use blocks from an assistant entry."""
    msg = entry.get("message", {})
    content = msg.get("content", "")
    if not isinstance(content, list):
        return []
    tools = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tools.append({
                "name": block.get("name", ""),
                "input": block.get("input", {}),
            })
    return tools


def extract_text(entry):
    """Extract plain text from an assistant entry."""
    msg = entry.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def get_last_user_directive(entries):
    """Find the last user message that likely contains a directive (has hao or mode 2 trigger)."""
    for entry in reversed(entries):
        if entry.get("type") == "user":
            msg = entry.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                content = "\n".join(parts)
            if isinstance(content, str):
                return content.lower()
    return ""


def extract_file_paths_from_directive(directive):
    """Extract file paths mentioned in a user directive."""
    paths = set()
    # Match common path patterns
    for match in re.finditer(r'[\w./\\-]+\.\w{1,10}', directive):
        paths.add(match.group().lower())
    return paths


def find_last_orient_index(entries):
    """Find the index of the most recent assistant entry containing an orient MCP call."""
    for i in range(len(entries) - 1, -1, -1):
        entry = entries[i]
        if entry.get("type") != "assistant":
            continue
        for tool in extract_tool_uses(entry):
            if "orient" in tool["name"].lower():
                return i
    return -1


def find_last_hao_index(entries):
    """Find the index of the most recent user message containing 'hao'."""
    for i in range(len(entries) - 1, -1, -1):
        entry = entries[i]
        if entry.get("type") == "user":
            text = extract_text(entry).lower()
            tokens = set(re.findall(r"\b\w+\b", text))
            if "hao" in tokens:
                return i
    return -1


def count_drift_signals(entries, current_mode):
    """Count structural drift signals from recent entries.
    Only counts unauthorized_files AFTER the most recent hao."""
    signals = {"gate_blocked": 0, "unauthorized_files": 0}

    # gate_blocked counts across the full window
    for entry in entries:
        if entry.get("type") == "user":
            text = extract_text(entry)
            if "gate blocked" in text.lower():
                signals["gate_blocked"] += 1

    # Structural checks only apply after the most recent hao
    hao_idx = find_last_hao_index(entries)
    if hao_idx < 0 or current_mode != 2:
        return signals

    directive = get_last_user_directive(entries)
    directive_files = extract_file_paths_from_directive(directive)

    for entry in entries[hao_idx + 1:]:
        if entry.get("type") != "assistant":
            continue

        # Check tool_use calls for unauthorized files
        for tool in extract_tool_uses(entry):
            name = tool["name"]
            inp = tool["input"]
            if name in ("Write", "Edit"):
                file_path = inp.get("file_path", "").lower()
                if file_path and directive_files:
                    matched = any(df in file_path for df in directive_files)
                    if not matched:
                        signals["unauthorized_files"] += 1

    return signals


def check_done(entries):
    """Check if the most recent assistant text contains [DONE]."""
    for entry in reversed(entries):
        if entry.get("type") == "assistant":
            text = extract_text(entry)
            if text.strip():
                return "[DONE]" in text
    return False


def detect_task_list(entries):
    """True if the most recent assistant message presents a task list.
    A task list = an explicit 'task list'/'[Task' marker, or two or more
    numbered items. Reinforces: no task list, hao does nothing."""
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        text = extract_text(entry)
        if not text.strip():
            continue
        lower = text.lower()
        if "task list" in lower or "[task " in lower:
            return True
        numbered = 0
        for line in text.split("\n"):
            if re.match(r"^\s*\d+\.\s", line):
                numbered += 1
        return numbered >= 2
    return False


AUTH_BLOCK_RE = re.compile(r"```authorization\s*(.+?)```", re.DOTALL)


def extract_authorizations(entries):
    """Parse a fenced ```authorization JSON array from the latest assistant message.
    Each entry needs action, resource_type, resource. Returns [] if none/invalid."""
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        text = extract_text(entry)
        if not text.strip():
            continue
        m = AUTH_BLOCK_RE.search(text)
        if not m:
            return []
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        out = []
        for e in data:
            if isinstance(e, dict) and "action" in e and "resource_type" in e and "resource" in e:
                out.append({"action": e["action"],
                            "resource_type": e["resource_type"],
                            "resource": e["resource"]})
        return out
    return []


def merge_into_state(drift_score, drift_halt, signals, mode=None, has_tasklist=False, authorizations=None):
    """Merge drift fields into gate-state.json, preserving other fields."""
    state = {}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except Exception:
            state = {}

    state["drift_score"] = drift_score
    state["drift_halt"] = drift_halt
    state["drift_signals"] = signals
    state["has_tasklist"] = has_tasklist
    state["authorizations"] = authorizations if authorizations is not None else []
    if mode is not None:
        state["mode"] = mode

    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    drift_score = 0
    drift_halt = False
    signals = {"gate_blocked": 0, "unauthorized_files": 0}

    try:
        jsonl_path = find_latest_jsonl()
        if not jsonl_path:
            merge_into_state(drift_score, drift_halt, signals)
            return

        entries = read_recent_entries(jsonl_path, WINDOW_SIZE)
        if not entries:
            merge_into_state(drift_score, drift_halt, signals)
            return

        # Reset window after orient call — orient clears gate state, don't re-score before it
        orient_idx = find_last_orient_index(entries)
        if orient_idx >= 0:
            entries = entries[orient_idx + 1:]
            if not entries:
                merge_into_state(drift_score, drift_halt, signals)
                return

        # Read current mode from state
        current_mode = 1
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    current_mode = json.load(f).get("mode", 1)
            except Exception:
                pass

        # [DONE] in assistant output resets mode to 1
        if check_done(entries):
            current_mode = 1

        signals = count_drift_signals(entries, current_mode)
        drift_score = signals["gate_blocked"] + signals["unauthorized_files"]
        drift_halt = drift_score >= DRIFT_THRESHOLD
        has_tasklist = detect_task_list(entries)
        authorizations = extract_authorizations(entries)

        merge_into_state(drift_score, drift_halt, signals, current_mode, has_tasklist, authorizations)
    except Exception as e:
        merge_into_state(0, False, {"error": str(e)[:200]})


if __name__ == "__main__":
    main()

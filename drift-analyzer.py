#!/usr/bin/env python3
"""
Drift analyzer — counts drift signals in recent messages from conversations.db
and merges drift fields into gate-state.json.

Called from prompt-gate.sh on every UserPromptSubmit hook.
Two signals:
  1. Gate denials in recent tool_result messages (the instance tried to act without permission)
  2. Drift phrases in recent assistant messages (over-explanation, initiative language)
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

# Make sibling modules importable (conversation_logger_server lives in the same dir)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from conversation_logger_server import ConversationIndexer
except Exception:
    ConversationIndexer = None

GATE_DIR = Path(__file__).parent
DB_PATH = GATE_DIR / "conversations.db"
STATE_FILE = GATE_DIR / "gate-state.json"

# Window: inspect the last N messages from the most recent session
WINDOW_SIZE = 10

# Threshold: drift_halt = True when drift_score >= this
DRIFT_THRESHOLD = 3

# Deterministic drift phrases to count in assistant messages (lowercase)
DRIFT_PHRASES = [
    # Verbose narrator drift
    "let me",
    "i could also",
    "i might also",
    "additionally",
    "furthermore",
    "also worth noting",
    "i went ahead",
    "i took the liberty",
    "i assumed",
    "i also fixed",
    "while i was at it",
    "thinking about this",
    "stepping back",
    "on reflection",
    "reconsidering",
    # Scope creep / unsolicited initiative
    "i'll also",
    "i've also",
    "we should also",
    "i should also",
    "one more thing",
    "while we're at it",
    "before we do that",
    "it would be good to",
    "i noticed",
    "i'll go ahead",
    "to be safe",
    # Post-drift signals
    "i apologize",
]


def get_latest_session_id(conn):
    c = conn.cursor()
    c.execute("SELECT session_id FROM messages ORDER BY timestamp DESC LIMIT 1")
    row = c.fetchone()
    return row[0] if row else None


def get_recent_messages(conn, session_id, limit):
    c = conn.cursor()
    c.execute(
        """
        SELECT role, content FROM messages
        WHERE session_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    return c.fetchall()


def count_drift_signals(messages):
    signals = {"gate_blocked": 0, "drift_phrases": 0}
    for role, content in messages:
        if not content:
            continue
        lower = content.lower()
        if role == "user":
            # Gate denials show up as tool_result text in user-role messages
            if "gate blocked" in lower:
                signals["gate_blocked"] += 1
        elif role == "assistant":
            for phrase in DRIFT_PHRASES:
                if phrase in lower:
                    signals["drift_phrases"] += 1
    return signals


def merge_into_state(drift_score, drift_halt, signals):
    """Merge drift fields into gate-state.json, preserving other fields."""
    state = {}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except Exception:
            state = {}

    # Testing override: 'kaisuo' in the current prompt forces drift_halt off
    prompt = state.get("prompt", "")
    tokens = set(re.findall(r"\b\w+\b", prompt.lower()))
    if "kaisuo" in tokens:
        drift_halt = False
        signals["kaisuo_override"] = True

    state["drift_score"] = drift_score
    state["drift_halt"] = drift_halt
    state["drift_signals"] = signals

    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    # Fail-safe defaults — if anything goes wrong, do not trigger a halt
    drift_score = 0
    drift_halt = False
    signals = {"gate_blocked": 0, "drift_phrases": 0}

    try:
        # Pull fresh JSONL content into the DB before analyzing.
        # Without this, the analyzer reads stale data and drift never
        # actually fires on current-session behavior.
        if ConversationIndexer is not None:
            try:
                ConversationIndexer().index_all()
            except Exception:
                # Don't fail drift analysis if indexing errors
                pass

        if not DB_PATH.exists():
            merge_into_state(drift_score, drift_halt, signals)
            return

        conn = sqlite3.connect(str(DB_PATH))
        try:
            session_id = get_latest_session_id(conn)
            if not session_id:
                merge_into_state(drift_score, drift_halt, signals)
                return

            messages = get_recent_messages(conn, session_id, WINDOW_SIZE)
            signals = count_drift_signals(messages)
            drift_score = signals["gate_blocked"] + signals["drift_phrases"]
            drift_halt = drift_score >= DRIFT_THRESHOLD
        finally:
            conn.close()

        merge_into_state(drift_score, drift_halt, signals)
    except Exception as e:
        # On any error, write a safe state with error logged
        merge_into_state(0, False, {"error": str(e)[:200]})


if __name__ == "__main__":
    main()

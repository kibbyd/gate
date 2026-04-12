#!/usr/bin/env python3
"""
Conversation Logger - Indexes Claude Code JSONL transcripts into searchable SQLite.
"""

import json
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import logging
import glob

log_file = Path(__file__).parent / "conversation_logger.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file, mode='a')]
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "conversations.db"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def init_database():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        model TEXT,
        git_branch TEXT,
        cwd TEXT,
        metadata TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        project_path TEXT,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        message_count INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS index_state (
        file_path TEXT PRIMARY KEY,
        last_offset INTEGER DEFAULT 0,
        last_indexed TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_msg_timestamp ON messages(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_msg_role ON messages(role)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_msg_content ON messages(content)')
    conn.commit()
    conn.close()


def extract_text_content(message_data):
    """Extract readable text from a Claude message content field."""
    content = message_data.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool_use: {block.get('name', '?')}]")
                elif block.get("type") == "tool_result":
                    # Recurse into tool result content
                    sub = block.get("content", "")
                    if isinstance(sub, str):
                        parts.append(f"[tool_result: {sub[:200]}]")
                    elif isinstance(sub, list):
                        for s in sub:
                            if isinstance(s, dict) and s.get("type") == "text":
                                parts.append(f"[tool_result: {s.get('text', '')[:200]}]")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)[:500]


class ConversationIndexer:
    def __init__(self):
        init_database()

    def index_all(self, force=False):
        """Scan all JSONL files under ~/.claude/projects/ and index new entries."""
        if not CLAUDE_PROJECTS_DIR.exists():
            logger.warning(f"Projects dir not found: {CLAUDE_PROJECTS_DIR}")
            return {"indexed": 0, "files": 0}

        conn = sqlite3.connect(str(DB_PATH))
        total_indexed = 0
        files_processed = 0

        # Find all JSONL files
        for jsonl_path in CLAUDE_PROJECTS_DIR.rglob("*.jsonl"):
            path_str = str(jsonl_path)
            try:
                file_size = jsonl_path.stat().st_size
                # Check last offset
                c = conn.cursor()
                c.execute('SELECT last_offset FROM index_state WHERE file_path = ?', (path_str,))
                row = c.fetchone()
                last_offset = row[0] if row else 0

                if not force and last_offset >= file_size:
                    continue  # Already fully indexed

                # Read new lines from offset
                count = self._index_file(conn, jsonl_path, last_offset if not force else 0)
                total_indexed += count
                files_processed += 1

                # Update offset
                new_offset = jsonl_path.stat().st_size
                c.execute('''INSERT INTO index_state (file_path, last_offset, last_indexed)
                             VALUES (?, ?, ?) ON CONFLICT(file_path)
                             DO UPDATE SET last_offset = ?, last_indexed = ?''',
                          (path_str, new_offset, datetime.now().isoformat(),
                           new_offset, datetime.now().isoformat()))
                conn.commit()
            except Exception as e:
                logger.error(f"Error indexing {path_str}: {e}")

        conn.close()
        return {"indexed": total_indexed, "files": files_processed}

    def _index_file(self, conn, jsonl_path, offset):
        """Index a single JSONL file from the given byte offset."""
        c = conn.cursor()
        count = 0
        # Derive project path from file location
        project_path = str(jsonl_path.parent)

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                if entry_type not in ("user", "assistant"):
                    continue

                uuid = entry.get("uuid", "")
                session_id = entry.get("sessionId", "")
                message = entry.get("message", {})
                role = message.get("role", entry_type)
                content = extract_text_content(message)
                model = message.get("model", "")
                git_branch = entry.get("gitBranch", "")
                cwd = entry.get("cwd", "")
                timestamp = ""

                # Try to get timestamp from message
                if "timestamp" in entry:
                    timestamp = entry["timestamp"]
                elif "created_at" in message:
                    timestamp = message["created_at"]
                else:
                    timestamp = datetime.now().isoformat()

                if not uuid or not content:
                    continue

                # Upsert message
                try:
                    c.execute('''INSERT OR IGNORE INTO messages
                                 (id, session_id, timestamp, role, content, model, git_branch, cwd)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                              (uuid, session_id, timestamp, role, content, model, git_branch, cwd))
                    if c.rowcount > 0:
                        count += 1
                        # Upsert session
                        c.execute('''INSERT INTO sessions (id, project_path, first_seen, last_seen, message_count)
                                     VALUES (?, ?, ?, ?, 1)
                                     ON CONFLICT(id) DO UPDATE SET
                                     last_seen = ?, message_count = message_count + 1''',
                                  (session_id, project_path, timestamp, timestamp, timestamp))
                except sqlite3.IntegrityError:
                    pass  # Already indexed

        conn.commit()
        return count


class ConversationLogger:
    def __init__(self):
        self.name = "conversation-logger"
        self.version = "2.0.0"
        self.indexer = ConversationIndexer()
        # Auto-index on startup
        result = self.indexer.index_all()
        logger.info(f"Startup index: {result}")

    def get_capabilities(self):
        return {
            "name": self.name,
            "version": self.version,
            "tools": [
                {
                    "name": "reindex",
                    "description": "Re-scan Claude Code JSONL transcripts and index new messages into the database",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "force": {
                                "type": "boolean",
                                "description": "Force full re-index (default: false, only indexes new content)",
                                "default": False
                            }
                        }
                    }
                },
                {
                    "name": "search_conversations",
                    "description": "Full-text search through all indexed conversation messages",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query (substring match)"},
                            "role": {"type": "string", "enum": ["user", "assistant"], "description": "Filter by role"},
                            "session_id": {"type": "string", "description": "Filter by session ID"},
                            "limit": {"type": "integer", "description": "Max results (default: 30)", "default": 30}
                        }
                    }
                },
                {
                    "name": "get_session_history",
                    "description": "Get chronological message history for a session",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Session ID"},
                            "limit": {"type": "integer", "description": "Max messages (default: 100)", "default": 100},
                            "offset": {"type": "integer", "description": "Skip first N messages", "default": 0}
                        },
                        "required": ["session_id"]
                    }
                },
                {
                    "name": "get_sessions_list",
                    "description": "List all indexed conversation sessions",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Max sessions (default: 20)", "default": 20}
                        }
                    }
                },
                {
                    "name": "get_stats",
                    "description": "Get database statistics",
                    "inputSchema": {"type": "object", "properties": {}}
                },
                {
                    "name": "get_recent",
                    "description": "Get most recent messages across all sessions",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "hours": {"type": "integer", "description": "Look back N hours (default: 24)", "default": 24},
                            "limit": {"type": "integer", "description": "Max results (default: 50)", "default": 50}
                        }
                    }
                }
            ]
        }

    def reindex(self, force=False):
        result = self.indexer.index_all(force=force)
        return {"success": True, **result}

    def search_conversations(self, query=None, role=None, session_id=None, limit=30):
        # First, index any new messages
        self.indexer.index_all()

        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        conditions = []
        params = []

        if query:
            conditions.append("content LIKE ?")
            params.append(f"%{query}%")
        if role:
            conditions.append("role = ?")
            params.append(role)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        c.execute(f'''SELECT id, session_id, timestamp, role,
                      SUBSTR(content, 1, 500) as content, model
                      FROM messages {where}
                      ORDER BY timestamp DESC LIMIT ?''',
                  params + [limit])

        results = [{"id": r[0], "session_id": r[1], "timestamp": r[2],
                     "role": r[3], "content": r[4], "model": r[5]}
                    for r in c.fetchall()]
        conn.close()
        return {"success": True, "results": results, "count": len(results)}

    def get_session_history(self, session_id, limit=100, offset=0):
        self.indexer.index_all()

        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''SELECT id, timestamp, role, content, model
                     FROM messages WHERE session_id = ?
                     ORDER BY timestamp ASC LIMIT ? OFFSET ?''',
                  (session_id, limit, offset))
        messages = [{"id": r[0], "timestamp": r[1], "role": r[2],
                      "content": r[3], "model": r[4]}
                     for r in c.fetchall()]

        c.execute('SELECT project_path, first_seen, last_seen, message_count FROM sessions WHERE id = ?',
                  (session_id,))
        session = c.fetchone()
        conn.close()

        if session:
            return {"success": True, "session_id": session_id,
                    "project_path": session[0], "first_seen": session[1],
                    "last_seen": session[2], "total_messages": session[3],
                    "messages": messages, "returned": len(messages)}
        return {"success": False, "error": "Session not found"}

    def get_sessions_list(self, limit=20):
        self.indexer.index_all()

        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''SELECT id, project_path, first_seen, last_seen, message_count
                     FROM sessions ORDER BY last_seen DESC LIMIT ?''', (limit,))
        sessions = [{"id": r[0], "project_path": r[1], "first_seen": r[2],
                      "last_seen": r[3], "message_count": r[4]}
                     for r in c.fetchall()]
        conn.close()
        return {"success": True, "sessions": sessions, "count": len(sessions)}

    def get_stats(self):
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''SELECT COUNT(*) as total,
                     COUNT(CASE WHEN role='user' THEN 1 END) as user_msgs,
                     COUNT(CASE WHEN role='assistant' THEN 1 END) as asst_msgs,
                     COUNT(DISTINCT session_id) as sessions
                     FROM messages''')
        r = c.fetchone()
        c.execute('SELECT COUNT(*) FROM index_state')
        files = c.fetchone()[0]
        conn.close()

        db_size = round(os.path.getsize(str(DB_PATH)) / 1024 / 1024, 2) if DB_PATH.exists() else 0
        return {
            "success": True,
            "total_messages": r[0], "user_messages": r[1],
            "assistant_messages": r[2], "total_sessions": r[3],
            "files_tracked": files, "database_size_mb": db_size
        }

    def get_recent(self, hours=24, limit=50):
        self.indexer.index_all()

        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        # Get messages from last N hours based on created_at
        c.execute('''SELECT id, session_id, timestamp, role,
                     SUBSTR(content, 1, 500) as content, model
                     FROM messages
                     ORDER BY timestamp DESC LIMIT ?''', (limit,))
        results = [{"id": r[0], "session_id": r[1], "timestamp": r[2],
                     "role": r[3], "content": r[4], "model": r[5]}
                    for r in c.fetchall()]
        conn.close()
        return {"success": True, "results": results, "count": len(results)}

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


class MemoryEngine:
    """Conversational Memory Engine."""

    def __init__(self, db_path: Path | str = "data/jarvis.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def close(self) -> None:
        """Close resources (no-op since connection per-op)."""
        pass

    async def initialize(self) -> None:
        """Initialize the database tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT NOT NULL
                )
                '''
            )
            await db.commit()

    async def add_message(
        self, role: str, content: str, session_id: str = "default", metadata: dict | None = None
    ) -> None:
        """Add a message to the conversational history."""
        async with aiosqlite.connect(self.db_path) as db:
            timestamp = datetime.now().isoformat()
            meta_str = json.dumps(metadata) if metadata is not None else None
            await db.execute(
                '''
                INSERT INTO conversations (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (session_id, role, content, timestamp, meta_str)
            )
            await db.commit()

    async def get_recent_history(self, limit: int = 10, session_id: str = "default") -> list[dict]:
        """Get recent conversational history."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                '''
                SELECT id, session_id, role, content, timestamp, metadata
                FROM conversations
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                ''',
                (session_id, limit)
            )
            rows = await cursor.fetchall()
            
            results = []
            for row in reversed(rows):
                res = dict(row)
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else None
                results.append(res)
            return results

    async def search_memory(self, query: str, limit: int = 5) -> list[dict]:
        """Search memory using LIKE."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            like_query = f"%{query}%"
            cursor = await db.execute(
                '''
                SELECT id, session_id, role, content, timestamp, metadata
                FROM conversations
                WHERE content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
                ''',
                (like_query, limit)
            )
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                res = dict(row)
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else None
                results.append(res)
            return results

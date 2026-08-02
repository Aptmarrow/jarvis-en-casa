from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


class PreferencesManager:
    """Preferences Helper."""

    def __init__(self, db_path: Path | str = "data/jarvis.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a preference value."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT value FROM user_preferences WHERE key = ?', (key,))
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return default

    async def set(self, key: str, value: Any) -> None:
        """Set a preference value."""
        async with aiosqlite.connect(self.db_path) as db:
            timestamp = datetime.now().isoformat()
            val_str = json.dumps(value)
            await db.execute(
                '''
                INSERT INTO user_preferences (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                ''',
                (key, val_str, timestamp)
            )
            await db.commit()

    async def all(self) -> dict[str, Any]:
        """Get all preferences."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT key, value FROM user_preferences')
            rows = await cursor.fetchall()
            return {row[0]: json.loads(row[1]) for row in rows}

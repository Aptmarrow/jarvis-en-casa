"""Persistent Device Registry for J.A.R.V.I.S.

Tracks historical presence of devices on local networks (MAC, IP, hostname, alias, first_seen, last_seen, status).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Persistent registry of all discovered and known network devices."""

    def __init__(self, db_path: Path | str = "data/jarvis.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Create the devices table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    mac TEXT PRIMARY KEY,
                    ip TEXT,
                    hostname TEXT,
                    alias TEXT,
                    vendor TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    status TEXT DEFAULT 'online',
                    metadata TEXT
                )
                """
            )
            await db.commit()

    async def register_or_update(
        self,
        mac: str,
        ip: str | None = None,
        hostname: str | None = None,
        alias: str | None = None,
        vendor: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a newly discovered device or update an existing device's status and last_seen."""
        now = datetime.now().isoformat()
        mac_clean = mac.lower().strip()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM devices WHERE mac = ?", (mac_clean,)
            )
            row = await cursor.fetchone()

            if row:
                # Update existing device
                current_alias = alias or row["alias"]
                current_hostname = hostname or row["hostname"]
                current_ip = ip or row["ip"]
                meta_str = json.dumps(metadata) if metadata else row["metadata"]

                await db.execute(
                    """
                    UPDATE devices
                    SET ip = ?, hostname = ?, alias = ?, last_seen = ?, status = 'online', metadata = ?
                    WHERE mac = ?
                    """,
                    (current_ip, current_hostname, current_alias, now, meta_str, mac_clean),
                )
                await db.commit()
                return {
                    "mac": mac_clean,
                    "ip": current_ip,
                    "hostname": current_hostname,
                    "alias": current_alias,
                    "first_seen": row["first_seen"],
                    "last_seen": now,
                    "status": "online",
                    "is_new": False,
                }
            else:
                # Insert new device
                meta_str = json.dumps(metadata or {})
                await db.execute(
                    """
                    INSERT INTO devices (mac, ip, hostname, alias, vendor, first_seen, last_seen, status, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'online', ?)
                    """,
                    (mac_clean, ip, hostname, alias, vendor, now, now, meta_str),
                )
                await db.commit()
                logger.info(f"New device registered in Device Registry: {mac_clean} ({hostname or ip})")
                return {
                    "mac": mac_clean,
                    "ip": ip,
                    "hostname": hostname,
                    "alias": alias,
                    "first_seen": now,
                    "last_seen": now,
                    "status": "online",
                    "is_new": True,
                }

    async def get_device(self, mac_or_alias_or_ip: str) -> dict[str, Any] | None:
        """Find a device by MAC, alias, hostname, or IP address."""
        query = mac_or_alias_or_ip.lower().strip()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM devices 
                WHERE mac = ? OR LOWER(alias) = ? OR LOWER(hostname) = ? OR ip = ?
                """,
                (query, query, query, query),
            )
            row = await cursor.fetchone()
            if row:
                res = dict(row)
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
                return res
            return None

    async def list_devices(self, online_only: bool = False) -> list[dict[str, Any]]:
        """List all devices in the registry."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if online_only:
                cursor = await db.execute(
                    "SELECT * FROM devices WHERE status = 'online' ORDER BY last_seen DESC"
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM devices ORDER BY last_seen DESC"
                )
            rows = await cursor.fetchall()

            results = []
            for row in rows:
                res = dict(row)
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
                results.append(res)
            return results

    async def close(self) -> None:
        """No-op for connection lifecycle."""
        pass

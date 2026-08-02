from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite
import yaml


class KnowledgeGraph:
    """Knowledge Graph Engine."""

    def __init__(self, db_path: Path | str = "data/jarvis.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def close(self) -> None:
        """Close resources (no-op since connection per-op)."""
        pass

    async def initialize(self, seed_path: Path | None = None) -> None:
        """Initialize the database tables and optionally seed them."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT,
                    aliases TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY(source_id) REFERENCES entities(id),
                    FOREIGN KEY(target_id) REFERENCES entities(id)
                )
                '''
            )
            await db.commit()

            # Check if entities table is empty
            cursor = await db.execute('SELECT COUNT(*) FROM entities')
            count = (await cursor.fetchone())[0]

            if count == 0 and seed_path is not None and seed_path.exists():
                await self._seed_data(db, seed_path)

    async def _seed_data(self, db: aiosqlite.Connection, seed_path: Path) -> None:
        """Populate database from YAML seed."""
        with open(seed_path, 'r', encoding='utf-8') as f:
            seed_data = yaml.safe_load(f)

        if not seed_data:
            return

        name_to_id = {}

        for ent in seed_data.get("entities", []):
            ent_id = await self._add_entity_internal(
                db,
                name=ent["name"],
                entity_type=ent.get("type", "unknown"),
                aliases=ent.get("aliases", []),
                metadata=ent.get("metadata", {})
            )
            name_to_id[ent["name"]] = ent_id

        for rel in seed_data.get("relations", []):
            source = rel["source"]
            target = rel["target"]
            source_id = name_to_id.get(source, source)
            target_id = name_to_id.get(target, target)
            await self._add_relation_internal(
                db,
                source_id=source_id,
                relation_type=rel["type"],
                target_id=target_id,
                metadata=rel.get("metadata", {})
            )
            
        await db.commit()

    async def _add_entity_internal(self, db: aiosqlite.Connection, name: str, entity_type: str, aliases: list[str] | None = None, metadata: dict | None = None) -> str:
        ent_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        aliases_str = json.dumps(aliases or [])
        meta_str = json.dumps(metadata or {})
        
        await db.execute(
            '''
            INSERT INTO entities (id, name, type, aliases, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (ent_id, name, entity_type, aliases_str, meta_str, timestamp)
        )
        return ent_id

    async def add_entity(self, name: str, entity_type: str, aliases: list[str] | None = None, metadata: dict | None = None) -> str:
        """Add a new entity."""
        async with aiosqlite.connect(self.db_path) as db:
            ent_id = await self._add_entity_internal(db, name, entity_type, aliases, metadata)
            await db.commit()
            return ent_id
            
    async def _add_relation_internal(self, db: aiosqlite.Connection, source_id: str, relation_type: str, target_id: str, metadata: dict | None = None) -> str:
        rel_id = str(uuid.uuid4())
        meta_str = json.dumps(metadata or {})
        
        await db.execute(
            '''
            INSERT INTO relations (id, source_id, relation_type, target_id, metadata)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (rel_id, source_id, relation_type, target_id, meta_str)
        )
        return rel_id

    async def add_relation(self, source_name_or_id: str, relation_type: str, target_name_or_id: str, metadata: dict | None = None) -> str:
        """Add a relation between entities."""
        async with aiosqlite.connect(self.db_path) as db:
            source = await self._resolve_internal(db, source_name_or_id)
            if not source:
                raise ValueError(f"Source entity not found: {source_name_or_id}")
                
            target = await self._resolve_internal(db, target_name_or_id)
            if not target:
                raise ValueError(f"Target entity not found: {target_name_or_id}")
                
            rel_id = await self._add_relation_internal(db, source["id"], relation_type, target["id"], metadata)
            await db.commit()
            return rel_id
            
    async def _resolve_internal(self, db: aiosqlite.Connection, query: str) -> dict | None:
        db.row_factory = aiosqlite.Row
        
        cursor = await db.execute('SELECT * FROM entities WHERE id = ? OR name = ?', (query, query))
        row = await cursor.fetchone()
        
        if row:
            res = dict(row)
            res["aliases"] = json.loads(res["aliases"]) if res["aliases"] else []
            res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
            return res
            
        cursor = await db.execute('SELECT * FROM entities')
        rows = await cursor.fetchall()
        for r in rows:
            res = dict(r)
            aliases = json.loads(res["aliases"]) if res["aliases"] else []
            if query in aliases:
                res["aliases"] = aliases
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
                return res
            for alias in aliases:
                if query.lower() in alias.lower():
                    res["aliases"] = aliases
                    res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
                    return res
        return None

    async def resolve(self, query: str) -> dict | None:
        """Search name, exact aliases, or partial aliases."""
        async with aiosqlite.connect(self.db_path) as db:
            return await self._resolve_internal(db, query)

    async def get_entity(self, name_or_id: str) -> dict | None:
        """Get an entity by name or ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM entities WHERE id = ? OR name = ?', (name_or_id, name_or_id))
            row = await cursor.fetchone()
            if row:
                res = dict(row)
                res["aliases"] = json.loads(res["aliases"]) if res["aliases"] else []
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
                return res
            return None

    async def search_entities(self, query: str, entity_type: str | None = None) -> list[dict]:
        """Search entities by name or aliases."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            like_query = f"%{query}%"
            
            if entity_type:
                cursor = await db.execute(
                    '''
                    SELECT * FROM entities 
                    WHERE type = ? AND (name LIKE ? OR aliases LIKE ?)
                    ''', 
                    (entity_type, like_query, like_query)
                )
            else:
                cursor = await db.execute(
                    '''
                    SELECT * FROM entities 
                    WHERE name LIKE ? OR aliases LIKE ?
                    ''', 
                    (like_query, like_query)
                )
                
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                res = dict(row)
                res["aliases"] = json.loads(res["aliases"]) if res["aliases"] else []
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
                results.append(res)
            return results

    async def get_relations(self, entity_name_or_id: str) -> list[dict]:
        """Get all relations for an entity."""
        async with aiosqlite.connect(self.db_path) as db:
            entity = await self._resolve_internal(db, entity_name_or_id)
            if not entity:
                return []
                
            ent_id = entity["id"]
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                '''
                SELECT * FROM relations 
                WHERE source_id = ? OR target_id = ?
                ''', 
                (ent_id, ent_id)
            )
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                res = dict(row)
                res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
                results.append(res)
            return results

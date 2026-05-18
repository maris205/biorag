"""SQLite graph store for DRAG expansion."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class GraphNode:
    entity_id: str
    entity_type: str
    name: str | None
    source: str | None
    description: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    source: str | None
    confidence: float | None
    metadata: dict[str, Any]


class GraphStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    @property
    def exists(self) -> bool:
        return self.db_path.exists()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Graph index not found: {self.db_path}")
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def status(self) -> dict[str, Any]:
        if not self.exists:
            return {"graph_db": str(self.db_path), "exists": False}
        with self.connect() as conn:
            nodes = conn.execute("SELECT entity_type, COUNT(*) AS n FROM nodes GROUP BY entity_type").fetchall()
            edges = conn.execute("SELECT relation_type, COUNT(*) AS n FROM edges GROUP BY relation_type").fetchall()
        return {
            "graph_db": str(self.db_path),
            "exists": True,
            "nodes": {str(row["entity_type"]): int(row["n"]) for row in nodes},
            "edges": {str(row["relation_type"]): int(row["n"]) for row in edges},
        }

    def resolve_aliases(self, query: str, limit: int = 8) -> list[GraphNode]:
        clean = str(query or "").strip()
        if not clean or not self.exists:
            return []
        pattern = f"%{clean}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT n.entity_id, n.entity_type, n.name, n.source, n.description, n.metadata_json
                FROM aliases a
                JOIN nodes n ON n.entity_id = a.entity_id
                WHERE upper(a.alias) = upper(?)
                   OR a.alias LIKE ?
                   OR n.name LIKE ?
                ORDER BY
                  CASE WHEN upper(a.alias) = upper(?) THEN 0 ELSE 1 END,
                  n.entity_type,
                  n.entity_id
                LIMIT ?
                """,
                (clean, pattern, pattern, clean, max(int(limit), 1)),
            ).fetchall()
        return [_node_from_row(row) for row in rows]

    def expand(self, entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if not entity_id or not self.exists:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.source_entity_id, e.relation_type, e.target_entity_id, e.source,
                       e.confidence, e.metadata_json,
                       src.entity_type AS source_type, src.name AS source_name,
                       dst.entity_type AS target_type, dst.name AS target_name
                FROM edges e
                JOIN nodes src ON src.entity_id = e.source_entity_id
                JOIN nodes dst ON dst.entity_id = e.target_entity_id
                WHERE e.source_entity_id = ? OR e.target_entity_id = ?
                ORDER BY e.relation_type, e.target_entity_id
                LIMIT ?
                """,
                (entity_id, entity_id, max(int(limit), 1)),
            ).fetchall()
        return [
            {
                "source_entity_id": row["source_entity_id"],
                "source_type": row["source_type"],
                "source_name": row["source_name"],
                "relation_type": row["relation_type"],
                "target_entity_id": row["target_entity_id"],
                "target_type": row["target_type"],
                "target_name": row["target_name"],
                "source": row["source"],
                "confidence": row["confidence"],
                "metadata": _json_load(row["metadata_json"]),
            }
            for row in rows
        ]


def _node_from_row(row: sqlite3.Row) -> GraphNode:
    return GraphNode(
        entity_id=str(row["entity_id"]),
        entity_type=str(row["entity_type"]),
        name=row["name"],
        source=row["source"],
        description=row["description"],
        metadata=_json_load(row["metadata_json"]),
    )


def _json_load(value: Any) -> dict[str, Any]:
    if value in {None, ""}:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}

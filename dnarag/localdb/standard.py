"""Adapter for the Open-Rosalind Standard SQLite FTS index."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class StandardDocument:
    id: int
    kind: str
    source_id: str
    symbol: str | None
    name: str | None
    organism: str | None
    description: str | None
    source: str
    source_url: str | None
    payload: dict[str, Any]
    score: float | None = None

    @property
    def entity_id(self) -> str:
        return f"{self.kind}:{self.source_id}"

    def to_evidence(self, route: str = "fts") -> dict[str, Any]:
        return {
            "route": route,
            "entity_id": self.entity_id,
            "kind": self.kind,
            "source_id": self.source_id,
            "symbol": self.symbol,
            "title": self.name or self.symbol or self.source_id,
            "snippet": self.description or "",
            "score": self.score,
            "source": self.source,
            "source_url": self.source_url,
            "metadata": self.payload,
        }


class StandardKB:
    """Read-only interface to the Standard text index built by Open-Rosalind."""

    def __init__(self, sqlite_path: str | Path, manifest_path: str | Path | None = None):
        self.sqlite_path = Path(sqlite_path)
        self.manifest_path = Path(manifest_path) if manifest_path else self.sqlite_path.parent / "manifest.json"

    @property
    def exists(self) -> bool:
        return self.sqlite_path.exists()

    def connect(self) -> sqlite3.Connection:
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"Standard SQLite index not found: {self.sqlite_path}")
        conn = sqlite3.connect(f"file:{self.sqlite_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "sqlite_path": str(self.sqlite_path),
            "sqlite_exists": self.sqlite_path.exists(),
            "manifest_path": str(self.manifest_path),
            "manifest_exists": self.manifest_path.exists(),
        }
        if self.manifest_path.exists():
            status["manifest"] = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if self.sqlite_path.exists():
            with self.connect() as conn:
                counts = conn.execute(
                    "SELECT kind, COUNT(*) AS n FROM documents GROUP BY kind ORDER BY kind"
                ).fetchall()
            status["document_counts"] = {str(row["kind"]): int(row["n"]) for row in counts}
        return status

    def iter_documents(self, limit: int = 0, kinds: Iterable[str] | None = None) -> Iterable[StandardDocument]:
        where = ""
        params: list[Any] = []
        selected_kinds = [str(kind) for kind in kinds or [] if str(kind)]
        if selected_kinds:
            placeholders = ",".join("?" for _ in selected_kinds)
            where = f"WHERE kind IN ({placeholders})"
            params.extend(selected_kinds)
        sql = f"""
            SELECT id, kind, source_id, symbol, name, organism, description, source, source_url, payload_json
            FROM documents
            {where}
            ORDER BY id
        """
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_document_from_row(row) for row in rows]

    def get_document(self, kind: str, source_id: str) -> StandardDocument | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, kind, source_id, symbol, name, organism, description, source, source_url, payload_json
                FROM documents
                WHERE kind = ? AND source_id = ?
                LIMIT 1
                """,
                (kind, source_id),
            ).fetchone()
        return _document_from_row(row) if row else None

    def search_text(self, query: str, limit: int = 10, kinds: Iterable[str] | None = None) -> list[StandardDocument]:
        clean_query = str(query or "").strip()
        if not clean_query:
            return []
        selected_kinds = [str(kind) for kind in kinds or [] if str(kind)]
        exact = clean_query.upper()
        params: list[Any] = [fts_query(clean_query), exact]
        kind_filter = ""
        if selected_kinds:
            placeholders = ",".join("?" for _ in selected_kinds)
            kind_filter = f"AND d.kind IN ({placeholders})"
            params.extend(selected_kinds)
        params.append(max(int(limit), 1))
        sql = f"""
            SELECT d.id, d.kind, d.source_id, d.symbol, d.name, d.organism, d.description,
                   d.source, d.source_url, d.payload_json, bm25(search_index) AS score
            FROM search_index
            JOIN documents d ON d.id = search_index.rowid
            WHERE search_index MATCH ? {kind_filter}
            ORDER BY
              CASE WHEN upper(coalesce(d.symbol, '')) = ? THEN 0 ELSE 1 END,
              score
            LIMIT ?
        """
        try:
            with self.connect() as conn:
                rows = conn.execute(sql, params).fetchall()
            return [_document_from_row(row) for row in rows]
        except sqlite3.OperationalError:
            return self._fallback_like_search(clean_query, limit=limit, kinds=selected_kinds)

    def _fallback_like_search(self, query: str, limit: int, kinds: list[str]) -> list[StandardDocument]:
        tokens = [token for token in query.split() if token]
        if not tokens:
            return []
        clauses = []
        params: list[Any] = []
        for token in tokens:
            like = f"%{token}%"
            clauses.append("(symbol LIKE ? OR name LIKE ? OR description LIKE ?)")
            params.extend([like, like, like])
        kind_filter = ""
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            kind_filter = f"AND kind IN ({placeholders})"
            params.extend(kinds)
        params.append(max(int(limit), 1))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, kind, source_id, symbol, name, organism, description, source, source_url,
                       payload_json, NULL AS score
                FROM documents
                WHERE {' OR '.join(clauses)} {kind_filter}
                ORDER BY id
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_document_from_row(row) for row in rows]


def fts_query(query: str) -> str:
    tokens = [token.replace('"', "") for token in str(query or "").split() if token.strip()]
    if not tokens:
        return '""'
    return " OR ".join(f'"{token}"' for token in tokens)


def _document_from_row(row: sqlite3.Row) -> StandardDocument:
    payload = _json_load(row["payload_json"], default={})
    score = row["score"] if "score" in row.keys() else None
    return StandardDocument(
        id=int(row["id"]),
        kind=str(row["kind"]),
        source_id=str(row["source_id"]),
        symbol=row["symbol"],
        name=row["name"],
        organism=row["organism"],
        description=row["description"],
        source=str(row["source"]),
        source_url=row["source_url"],
        payload=payload if isinstance(payload, dict) else {},
        score=float(score) if score is not None else None,
    )


def _json_load(value: Any, default: Any) -> Any:
    if value in {None, ""}:
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default

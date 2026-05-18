"""Build text-style DRAG view graphs from vector collections."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from dnarag.config import BioKBConfig
from dnarag.localdb.graph_builder import _counts, _graph_schema, _insert_aliases, _insert_edge, _upsert_node
from dnarag.retrieval.vector_db import ChromaVectorDB


@dataclass(frozen=True, slots=True)
class ViewGraphBuildResult:
    graph_db: Path
    target: str
    node_count: int
    edge_count: int
    alias_count: int
    record_count: int
    neighbor_count: int
    min_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_db": str(self.graph_db),
            "target": self.target,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "alias_count": self.alias_count,
            "record_count": self.record_count,
            "neighbor_count": self.neighbor_count,
            "min_score": self.min_score,
        }


class VectorViewGraphBuilder:
    """Create a method-agnostic graph view from vector nearest neighbors.

    The graph intentionally uses the same recipe that a normal text RAG POC
    would use: records become nodes, vector neighbors become evidence edges.
    Biological relation types can be layered in later as explicit ablations.
    """

    def __init__(self, config: BioKBConfig):
        self.config = config
        self.vector_db = ChromaVectorDB(config.vector_dir)

    def build(
        self,
        *,
        target: str,
        limit: int = 1000,
        neighbors: int = 5,
        min_score: float | None = None,
        output: str | Path | None = None,
    ) -> ViewGraphBuildResult:
        if limit <= 0:
            raise ValueError("limit must be positive for vector view graph construction")
        if neighbors <= 0:
            raise ValueError("neighbors must be positive")
        records = self.vector_db.get_records(target, limit=limit, include_embeddings=True)
        records = [record for record in records if record.get("embedding") is not None]
        graph_db = Path(output) if output else self.config.graph_dir / "views" / f"{_safe_name(target)}.sqlite"
        graph_db.parent.mkdir(parents=True, exist_ok=True)
        if graph_db.exists():
            graph_db.unlink()
        with sqlite3.connect(graph_db) as conn:
            conn.executescript(_graph_schema())
            conn.execute("CREATE TABLE graph_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            for record in records:
                _insert_record_node(conn, target, record)
            _insert_neighbor_edges(
                conn,
                target,
                records,
                neighbors=neighbors,
                min_score=min_score,
            )
            counts = _counts(conn)
            conn.executemany(
                """
                INSERT INTO graph_meta(key, value)
                VALUES (?, ?)
                """,
                [
                    ("view_graph", "true"),
                    ("recipe", "text_style_vector_neighbors"),
                    ("target", target),
                    ("record_count", str(len(records))),
                    ("neighbor_count", str(neighbors)),
                    ("min_score", "" if min_score is None else str(min_score)),
                ],
            )
        return ViewGraphBuildResult(
            graph_db=graph_db,
            target=target,
            node_count=counts["node_count"],
            edge_count=counts["edge_count"],
            alias_count=counts["alias_count"],
            record_count=len(records),
            neighbor_count=neighbors,
            min_score=min_score,
        )


def _insert_record_node(conn: sqlite3.Connection, target: str, record: dict[str, Any]) -> None:
    metadata = dict(record.get("metadata") or {})
    record_id = str(record.get("record_id") or record.get("id") or "")
    entity_id = record_id or f"{target}:{record.get('row_idx')}"
    source_id = _first(metadata.get("source_id"), metadata.get("accession"), record_id)
    name = _first(metadata.get("symbol"), metadata.get("accession"), metadata.get("header"), source_id)
    document = str(record.get("document") or "")
    _upsert_node(
        conn,
        entity_id=entity_id,
        entity_type=_entity_type(target, metadata),
        canonical_id=str(source_id) if source_id else None,
        name=str(name) if name else entity_id,
        source=str(metadata.get("source") or f"Chroma:{target}"),
        description=_compact(document, limit=800),
        organism=_optional_str(metadata.get("organism")),
        metadata={
            "target": target,
            "row_idx": record.get("row_idx"),
            "chroma_id": record.get("id"),
            "kind": metadata.get("kind"),
            "alphabet": metadata.get("alphabet"),
            "length": metadata.get("length"),
            "source_url": metadata.get("source_url"),
            "graph_recipe": "text_style_vector_neighbors",
        },
    )
    _insert_aliases(conn, entity_id, _aliases(record, metadata), source=str(metadata.get("source") or target))


def _insert_neighbor_edges(
    conn: sqlite3.Connection,
    target: str,
    records: list[dict[str, Any]],
    *,
    neighbors: int,
    min_score: float | None,
) -> None:
    if len(records) < 2:
        return
    matrix = np.asarray([record["embedding"] for record in records], dtype=np.float32)
    matrix = _normalize_rows(matrix)
    scores = matrix @ matrix.T
    np.fill_diagonal(scores, -np.inf)
    relation = "vector_neighbor"
    for row_idx, record in enumerate(records):
        source_entity_id = _entity_id(target, record)
        top = np.argsort(-scores[row_idx])[: min(neighbors, len(records) - 1)]
        for rank, neighbor_idx in enumerate(top, start=1):
            score = float(scores[row_idx, neighbor_idx])
            if np.isneginf(score) or np.isnan(score):
                continue
            if min_score is not None and score < min_score:
                continue
            target_entity_id = _entity_id(target, records[int(neighbor_idx)])
            if target_entity_id == source_entity_id:
                continue
            _insert_edge(
                conn,
                source_entity_id,
                relation,
                target_entity_id,
                source=f"Chroma:{target}",
                confidence=score,
                metadata={
                    "target": target,
                    "rank": rank,
                    "score": score,
                    "graph_recipe": "text_style_vector_neighbors",
                    "biological_rules_used": False,
                },
            )


def _entity_id(target: str, record: dict[str, Any]) -> str:
    return str(record.get("record_id") or record.get("id") or f"{target}:{record.get('row_idx')}")


def _entity_type(target: str, metadata: dict[str, Any]) -> str:
    kind = str(metadata.get("kind") or target).lower()
    alphabet = str(metadata.get("alphabet") or "").lower()
    if alphabet == "dna" or "dna" in kind or "cdna" in kind:
        return "dna_sequence"
    if alphabet == "protein" or "protein" in kind or "peptide" in kind:
        return "protein_sequence"
    if "pathway" in kind:
        return "pathway"
    if "go" in kind:
        return "go_term"
    if "gene" in kind:
        return "gene"
    return "text_knowledge"


def _aliases(record: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    values = [
        record.get("record_id"),
        record.get("id"),
        metadata.get("source_id"),
        metadata.get("accession"),
        metadata.get("symbol"),
    ]
    header = metadata.get("header")
    if header:
        values.append(str(header).split()[0])
    return [str(value) for value in values if value not in {None, ""}]


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _safe_name(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value)).strip("_")
    return safe or "view"


def _first(*values: Any) -> Any:
    for value in values:
        if value not in {None, ""}:
            return value
    return None


def _compact(value: Any, *, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)

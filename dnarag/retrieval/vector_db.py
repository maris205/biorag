"""Small local vector database backed by SQLite metadata and NumPy vectors."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class VectorDBHit:
    row_idx: int
    score: float
    record_id: str
    target: str
    metadata: dict[str, Any]
    document: str | None = None


class SimpleVectorDB:
    """Minimal local vector store.

    Vectors stay in the existing compressed NumPy files. SQLite stores collection
    metadata and row metadata, giving us a small vector database without running
    a separate service.
    """

    def __init__(self, vector_dir: str | Path, db_name: str = "vector.sqlite"):
        self.vector_dir = Path(vector_dir)
        self.db_path = self.vector_dir / db_name

    @property
    def exists(self) -> bool:
        return self.db_path.exists()

    def initialize(self) -> None:
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    target TEXT PRIMARY KEY,
                    vector_path TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    count INTEGER NOT NULL,
                    metric TEXT NOT NULL,
                    backend TEXT,
                    model TEXT,
                    pooling TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    target TEXT NOT NULL,
                    row_idx INTEGER NOT NULL,
                    record_id TEXT NOT NULL,
                    text_sha256 TEXT,
                    kind TEXT,
                    source_id TEXT,
                    symbol TEXT,
                    source TEXT,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (target, row_idx)
                );
                CREATE INDEX IF NOT EXISTS idx_vector_records_record_id
                    ON records(target, record_id);
                CREATE INDEX IF NOT EXISTS idx_vector_records_symbol
                    ON records(target, symbol);
                CREATE INDEX IF NOT EXISTS idx_vector_records_kind
                    ON records(target, kind);
                """
            )

    def status(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {"db_path": str(self.db_path), "exists": False, "collections": {}}
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT target, vector_path, dim, count, metric, backend, model, pooling, updated_at
                FROM collections
                ORDER BY target
                """
            ).fetchall()
        return {
            "db_path": str(self.db_path),
            "exists": True,
            "collections": {str(row["target"]): _collection_row_to_dict(row) for row in rows},
        }

    def collection_info(self, target: str) -> dict[str, Any] | None:
        if not self.db_path.exists():
            return None
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                """
                SELECT target, vector_path, dim, count, metric, backend, model, pooling, updated_at
                FROM collections
                WHERE target = ?
                """,
                (target,),
            ).fetchone()
        return _collection_row_to_dict(row) if row else None

    def has_collection(self, target: str) -> bool:
        info = self.collection_info(target)
        if not info:
            return False
        return self._resolve_vector_path(str(info["vector_path"])).exists()

    def upsert_collection(
        self,
        *,
        target: str,
        vector_path: str | Path,
        matrix: np.ndarray,
        records: Iterable[dict[str, Any]],
        backend: str | None = None,
        model: str | None = None,
        pooling: str | None = None,
        metric: str = "cosine",
    ) -> dict[str, Any]:
        self.initialize()
        matrix = np.asarray(matrix, dtype=np.float32)
        if matrix.ndim != 2:
            raise ValueError(f"Expected a 2D vector matrix for {target}, got shape {matrix.shape}")
        rows = list(records)
        if len(rows) != matrix.shape[0]:
            raise ValueError(f"Record count {len(rows)} does not match vector count {matrix.shape[0]}")
        rel_vector_path = self._store_path(vector_path)
        updated_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM records WHERE target = ?", (target,))
            conn.execute(
                """
                INSERT INTO collections
                (target, vector_path, dim, count, metric, backend, model, pooling, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(target) DO UPDATE SET
                    vector_path=excluded.vector_path,
                    dim=excluded.dim,
                    count=excluded.count,
                    metric=excluded.metric,
                    backend=excluded.backend,
                    model=excluded.model,
                    pooling=excluded.pooling,
                    updated_at=excluded.updated_at
                """,
                (
                    target,
                    rel_vector_path,
                    int(matrix.shape[1]) if matrix.size else 0,
                    int(matrix.shape[0]),
                    metric,
                    backend,
                    model,
                    pooling,
                    updated_at,
                ),
            )
            conn.executemany(
                """
                INSERT INTO records
                (target, row_idx, record_id, text_sha256, kind, source_id, symbol, source, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        target,
                        row_idx,
                        str(record.get("record_id") or ""),
                        _optional_str(record.get("text_sha256")),
                        _optional_str((record.get("metadata") or {}).get("kind")),
                        _optional_str((record.get("metadata") or {}).get("source_id")),
                        _optional_str((record.get("metadata") or {}).get("symbol")),
                        _optional_str((record.get("metadata") or {}).get("source")),
                        json.dumps(record.get("metadata") or {}, ensure_ascii=False),
                    )
                    for row_idx, record in enumerate(rows)
                ],
            )
        return self.collection_info(target) or {}

    def import_legacy(self, target: str) -> dict[str, Any]:
        matrix_path = self.vector_dir / f"{target}.npz"
        id_map_path = self.vector_dir / f"{target}_id_map.jsonl"
        manifest_path = self.vector_dir / "manifest.json"
        if not matrix_path.exists() or not id_map_path.exists():
            raise FileNotFoundError(f"Missing legacy vector artifacts for target '{target}' in {self.vector_dir}")
        manifest = _read_json(manifest_path) if manifest_path.exists() else {}
        matrix = np.load(matrix_path)["vectors"]
        records = _read_jsonl(id_map_path)
        return self.upsert_collection(
            target=target,
            vector_path=matrix_path,
            matrix=matrix,
            records=records,
            backend=_optional_str(manifest.get("backend")),
            model=_optional_str(manifest.get("model")),
            pooling=_optional_str(manifest.get("pooling")),
        )

    def search(self, target: str, query_vector: np.ndarray, top_k: int = 10) -> list[VectorDBHit]:
        info = self.collection_info(target)
        if not info:
            return []
        matrix_path = self._resolve_vector_path(str(info["vector_path"]))
        if not matrix_path.exists():
            raise FileNotFoundError(f"Vector matrix not found for target '{target}': {matrix_path}")
        matrix = np.load(matrix_path)["vectors"]
        if matrix.size == 0:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm > 0:
            query = query / query_norm
        scores = matrix @ query
        top = np.argsort(-scores)[: max(int(top_k), 1)]
        record_map = self.records_by_row(target, [int(idx) for idx in top])
        hits: list[VectorDBHit] = []
        for idx in top:
            score = float(scores[idx])
            if np.isnan(score):
                continue
            record = record_map.get(int(idx))
            if not record:
                continue
            hits.append(
                VectorDBHit(
                    row_idx=int(idx),
                    score=score,
                    record_id=str(record["record_id"]),
                    target=target,
                    metadata=dict(record["metadata"]),
                    document=None,
                )
            )
        return hits

    def records_by_row(self, target: str, row_indices: Iterable[int]) -> dict[int, dict[str, Any]]:
        indices = [int(idx) for idx in row_indices]
        if not indices:
            return {}
        placeholders = ",".join("?" for _ in indices)
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                f"""
                SELECT row_idx, record_id, text_sha256, kind, source_id, symbol, source, metadata_json
                FROM records
                WHERE target = ? AND row_idx IN ({placeholders})
                """,
                [target, *indices],
            ).fetchall()
        return {
            int(row["row_idx"]): {
                "record_id": row["record_id"],
                "text_sha256": row["text_sha256"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
            for row in rows
        }

    def _connect(self, readonly: bool) -> sqlite3.Connection:
        if readonly:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _store_path(self, path: str | Path) -> str:
        vector_path = Path(path)
        try:
            return str(vector_path.resolve().relative_to(self.vector_dir.resolve()))
        except ValueError:
            return str(vector_path)

    def _resolve_vector_path(self, stored_path: str) -> Path:
        path = Path(stored_path)
        return path if path.is_absolute() else self.vector_dir / path


class ChromaVectorDB:
    """Chroma-backed vector store for RAG POC workflows."""

    def __init__(self, vector_dir: str | Path, persist_name: str = "chroma"):
        self.vector_dir = Path(vector_dir)
        self.persist_dir = self.vector_dir / persist_name

    @property
    def exists(self) -> bool:
        return self.persist_dir.exists()

    def status(self) -> dict[str, Any]:
        if not self.persist_dir.exists():
            return {"persist_dir": str(self.persist_dir), "exists": False, "collections": {}}
        client = self._client()
        collections: dict[str, Any] = {}
        for collection in client.list_collections():
            name = collection.name if hasattr(collection, "name") else str(collection)
            target = _target_from_collection_name(name)
            loaded = client.get_collection(name)
            collections[target] = {
                "name": name,
                "count": loaded.count(),
                "metadata": dict(loaded.metadata or {}),
            }
        return {"persist_dir": str(self.persist_dir), "exists": True, "collections": collections}

    def has_collection(self, target: str) -> bool:
        if not self.persist_dir.exists():
            return False
        try:
            self._collection(target)
            return True
        except Exception:
            return False

    def collection_info(self, target: str) -> dict[str, Any] | None:
        if not self.persist_dir.exists():
            return None
        try:
            collection = self._collection(target)
        except Exception:
            return None
        return {
            "name": collection.name,
            "count": collection.count(),
            "metadata": dict(collection.metadata or {}),
        }

    def ensure_collection(self, target: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        collection = self._collection(
            target,
            create=True,
            metadata={"hnsw:space": "cosine", "target": target, **dict(metadata or {})},
        )
        if metadata:
            try:
                collection.modify(metadata={"hnsw:space": "cosine", "target": target, **dict(metadata)})
            except Exception:
                pass
        return self.collection_info(target) or {}

    def import_legacy(self, target: str, batch_size: int = 1000, reset: bool = True) -> dict[str, Any]:
        matrix_path = self.vector_dir / f"{target}.npz"
        id_map_path = self.vector_dir / f"{target}_id_map.jsonl"
        manifest_path = self.vector_dir / "manifest.json"
        if not matrix_path.exists() or not id_map_path.exists():
            raise FileNotFoundError(f"Missing legacy vector artifacts for target '{target}' in {self.vector_dir}")
        manifest = _read_json(manifest_path) if manifest_path.exists() else {}
        matrix = np.load(matrix_path)["vectors"]
        records = _read_jsonl(id_map_path)
        return self.upsert_collection(
            target=target,
            matrix=matrix,
            records=records,
            backend=_optional_str(manifest.get("backend")),
            model=_optional_str(manifest.get("model")),
            pooling=_optional_str(manifest.get("pooling")),
            batch_size=batch_size,
            reset=reset,
        )

    def upsert_collection(
        self,
        *,
        target: str,
        matrix: np.ndarray,
        records: Iterable[dict[str, Any]],
        backend: str | None = None,
        model: str | None = None,
        pooling: str | None = None,
        batch_size: int = 1000,
        reset: bool = False,
    ) -> dict[str, Any]:
        rows = list(records)
        embeddings = np.asarray(matrix, dtype=np.float32)
        if embeddings.ndim != 2:
            raise ValueError(f"Expected a 2D vector matrix for {target}, got shape {embeddings.shape}")
        if len(rows) != embeddings.shape[0]:
            raise ValueError(f"Record count {len(rows)} does not match vector count {embeddings.shape[0]}")
        if reset:
            self.delete_collection(target, missing_ok=True)
        collection = self._collection(
            target,
            create=True,
            metadata={
                "hnsw:space": "cosine",
                "target": target,
                "backend": backend or "",
                "model": model or "",
                "pooling": pooling or "",
                "dim": int(embeddings.shape[1]) if embeddings.size else 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        batch = max(int(batch_size or 1000), 1)
        for start in range(0, len(rows), batch):
            end = min(start + batch, len(rows))
            batch_rows = rows[start:end]
            collection.upsert(
                ids=[_chroma_id(target, start + offset, row) for offset, row in enumerate(batch_rows)],
                embeddings=embeddings[start:end].tolist(),
                metadatas=[
                    _chroma_metadata(target, start + offset, row)
                    for offset, row in enumerate(batch_rows)
                ],
                documents=[_chroma_document(row) for row in batch_rows],
            )
        return self.collection_info(target) or {}

    def add_records(
        self,
        target: str,
        records: Sequence[dict[str, Any]],
        embeddings: np.ndarray,
        documents: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        collection = self._collection(target, create=True, metadata={"hnsw:space": "cosine", "target": target})
        rows = list(records)
        matrix = np.asarray(embeddings, dtype=np.float32)
        _validate_record_embeddings(rows, matrix)
        collection.add(
            ids=[_chroma_id(target, int(row.get("row_idx", idx)), row) for idx, row in enumerate(rows)],
            embeddings=matrix.tolist(),
            metadatas=[_chroma_metadata(target, int(row.get("row_idx", idx)), row) for idx, row in enumerate(rows)],
            documents=list(documents) if documents is not None else [_chroma_document(row) for row in rows],
        )
        return self.collection_info(target) or {}

    def upsert_records(
        self,
        target: str,
        records: Sequence[dict[str, Any]],
        embeddings: np.ndarray,
        documents: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        collection = self._collection(target, create=True, metadata={"hnsw:space": "cosine", "target": target})
        rows = list(records)
        matrix = np.asarray(embeddings, dtype=np.float32)
        _validate_record_embeddings(rows, matrix)
        collection.upsert(
            ids=[_chroma_id(target, int(row.get("row_idx", idx)), row) for idx, row in enumerate(rows)],
            embeddings=matrix.tolist(),
            metadatas=[_chroma_metadata(target, int(row.get("row_idx", idx)), row) for idx, row in enumerate(rows)],
            documents=list(documents) if documents is not None else [_chroma_document(row) for row in rows],
        )
        return self.collection_info(target) or {}

    def update_records(
        self,
        target: str,
        records: Sequence[dict[str, Any]],
        embeddings: np.ndarray | None = None,
        documents: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        collection = self._collection(target)
        rows = list(records)
        matrix = np.asarray(embeddings, dtype=np.float32) if embeddings is not None else None
        if matrix is not None:
            _validate_record_embeddings(rows, matrix)
        ids = [_chroma_id(target, int(row.get("row_idx", idx)), row) for idx, row in enumerate(rows)]
        collection.update(
            ids=ids,
            embeddings=matrix.tolist() if matrix is not None else None,
            metadatas=[_chroma_metadata(target, int(row.get("row_idx", idx)), row) for idx, row in enumerate(rows)],
            documents=list(documents) if documents is not None else [_chroma_document(row) for row in rows],
        )
        return self.collection_info(target) or {}

    def delete_records(
        self,
        target: str,
        *,
        ids: Sequence[str] | None = None,
        record_ids: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        collection = self._collection(target)
        before = collection.count()
        if ids:
            collection.delete(ids=list(ids))
        elif record_ids:
            collection.delete(where={"record_id": {"$in": [str(item) for item in record_ids]}})
        elif where:
            collection.delete(where=dict(where))
        else:
            raise ValueError("delete_records requires ids, record_ids, or where")
        after = collection.count()
        return {"target": target, "deleted": before - after, "count": after}

    def get_records(
        self,
        target: str,
        *,
        ids: Sequence[str] | None = None,
        record_ids: Sequence[str] | None = None,
        limit: int = 10,
        include_embeddings: bool = False,
    ) -> list[dict[str, Any]]:
        collection = self._collection(target)
        include = ["metadatas", "documents"]
        if include_embeddings:
            include.append("embeddings")
        if ids:
            result = collection.get(ids=list(ids), include=include)
        elif record_ids:
            result = collection.get(
                where={"record_id": {"$in": [str(item) for item in record_ids]}},
                limit=max(int(limit), 1),
                include=include,
            )
        else:
            result = collection.get(limit=max(int(limit), 1), include=include)
        return _chroma_get_to_records(result)

    def search(
        self,
        target: str,
        query_vector: np.ndarray,
        top_k: int = 10,
        where: Mapping[str, Any] | None = None,
    ) -> list[VectorDBHit]:
        collection = self._collection(target)
        result = collection.query(
            query_embeddings=[np.asarray(query_vector, dtype=np.float32).tolist()],
            n_results=max(int(top_k), 1),
            where=dict(where) if where else None,
            include=["metadatas", "documents", "distances"],
        )
        hits: list[VectorDBHit] = []
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        documents = result.get("documents", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for index, (item_id, metadata, distance) in enumerate(zip(ids, metadatas, distances)):
            parsed = _metadata_from_chroma(metadata or {})
            document = documents[index] if index < len(documents) else None
            hits.append(
                VectorDBHit(
                    row_idx=int(parsed.get("row_idx", -1)),
                    score=1.0 - float(distance),
                    record_id=str(parsed.get("record_id") or item_id),
                    target=target,
                    metadata=dict(parsed.get("metadata") or {}),
                    document=str(document) if document is not None else None,
                )
            )
        return hits

    def delete_collection(self, target: str, missing_ok: bool = False) -> None:
        client = self._client()
        name = _collection_name(target)
        try:
            client.delete_collection(name)
        except Exception:
            if not missing_ok:
                raise

    def _client(self) -> Any:
        try:
            import chromadb
            from chromadb.config import Settings
        except Exception as exc:
            raise RuntimeError("Install chromadb to use the Chroma vector database backend") from exc
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

    def _collection(
        self,
        target: str,
        *,
        create: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> Any:
        client = self._client()
        name = _collection_name(target)
        if create:
            return client.get_or_create_collection(name=name, metadata=dict(metadata or {}))
        return client.get_collection(name=name)


def _collection_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "target": row["target"],
        "vector_path": row["vector_path"],
        "dim": int(row["dim"]),
        "count": int(row["count"]),
        "metric": row["metric"],
        "backend": row["backend"],
        "model": row["model"],
        "pooling": row["pooling"],
        "updated_at": row["updated_at"],
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _collection_name(target: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(target)).strip("_")
    return f"dnarag_{safe or 'default'}"


def _target_from_collection_name(name: str) -> str:
    return name.removeprefix("dnarag_")


def _chroma_id(target: str, row_idx: int, record: Mapping[str, Any]) -> str:
    raw = record.get("id") or record.get("chroma_id")
    if raw:
        return str(raw)
    return f"{target}:{row_idx}"


def _chroma_metadata(target: str, row_idx: int, record: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(record.get("metadata") or {})
    payload = {
        "target": target,
        "row_idx": int(row_idx),
        "record_id": str(record.get("record_id") or ""),
        "text_sha256": _optional_str(record.get("text_sha256")) or "",
        "kind": _optional_str(metadata.get("kind")) or "",
        "source_id": _optional_str(metadata.get("source_id") or metadata.get("accession")) or "",
        "symbol": _optional_str(metadata.get("symbol")) or "",
        "source": _optional_str(metadata.get("source")) or "",
        "source_url": _optional_str(metadata.get("source_url")) or "",
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }
    return {key: value for key, value in payload.items() if value not in {None, ""}}


def _chroma_document(record: Mapping[str, Any]) -> str:
    document = record.get("document") or record.get("text")
    if document:
        return str(document)
    metadata = dict(record.get("metadata") or {})
    parts = [
        str(record.get("record_id") or ""),
        str(metadata.get("symbol") or ""),
        str(metadata.get("accession") or ""),
        str(metadata.get("kind") or ""),
        str(metadata.get("source") or ""),
    ]
    return " ".join(part for part in parts if part)


def _metadata_from_chroma(metadata: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(metadata)
    try:
        nested = json.loads(str(raw.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        nested = {}
    return {
        "row_idx": int(raw.get("row_idx", -1)),
        "record_id": str(raw.get("record_id") or ""),
        "metadata": nested,
    }


def _chroma_get_to_records(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []
    embeddings = result.get("embeddings")
    rows: list[dict[str, Any]] = []
    for idx, metadata in enumerate(metadatas):
        parsed = _metadata_from_chroma(metadata or {})
        row = {
            "id": ids[idx] if idx < len(ids) else "",
            "record_id": parsed.get("record_id"),
            "row_idx": parsed.get("row_idx"),
            "metadata": parsed.get("metadata"),
            "document": documents[idx] if idx < len(documents) else None,
        }
        if embeddings is not None and idx < len(embeddings):
            row["embedding"] = np.asarray(embeddings[idx], dtype=np.float32).tolist()
        rows.append(row)
    return rows


def _validate_record_embeddings(records: Sequence[dict[str, Any]], embeddings: np.ndarray) -> None:
    if embeddings.ndim != 2:
        raise ValueError(f"Expected 2D embeddings, got shape {embeddings.shape}")
    if len(records) != embeddings.shape[0]:
        raise ValueError(f"Record count {len(records)} does not match embedding count {embeddings.shape[0]}")


def _optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)

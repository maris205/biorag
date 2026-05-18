import json
from pathlib import Path

import numpy as np
import pytest

from dnarag.retrieval.vector_db import ChromaVectorDB, SimpleVectorDB


def test_simple_vector_db_upsert_and_search(tmp_path: Path):
    vector_dir = tmp_path / "vector"
    vector_dir.mkdir()
    matrix_path = vector_dir / "text.npz"
    matrix = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    np.savez_compressed(matrix_path, vectors=matrix)
    records = [
        {"record_id": "gene:BRCA1", "text_sha256": "a", "metadata": {"kind": "gene", "symbol": "BRCA1"}},
        {"record_id": "gene:TP53", "text_sha256": "b", "metadata": {"kind": "gene", "symbol": "TP53"}},
    ]

    db = SimpleVectorDB(vector_dir)
    info = db.upsert_collection(
        target="text",
        vector_path=matrix_path,
        matrix=matrix,
        records=records,
        backend="hashing",
        pooling="mean",
    )
    hits = db.search("text", np.asarray([1.0, 0.0, 0.0], dtype=np.float32), top_k=1)

    assert info["count"] == 2
    assert info["dim"] == 3
    assert hits[0].record_id == "gene:BRCA1"
    assert hits[0].metadata["symbol"] == "BRCA1"


def test_simple_vector_db_import_legacy(tmp_path: Path):
    vector_dir = tmp_path / "vector"
    vector_dir.mkdir()
    np.savez_compressed(vector_dir / "text.npz", vectors=np.asarray([[0.0, 1.0]], dtype=np.float32))
    (vector_dir / "text_id_map.jsonl").write_text(
        json.dumps(
            {
                "record_id": "gene:TP53",
                "text_sha256": "b",
                "metadata": {"kind": "gene", "symbol": "TP53"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (vector_dir / "manifest.json").write_text(
        json.dumps({"backend": "hashing", "pooling": "mean"}),
        encoding="utf-8",
    )

    db = SimpleVectorDB(vector_dir)
    info = db.import_legacy("text")

    assert info["count"] == 1
    assert db.status()["collections"]["text"]["backend"] == "hashing"


def test_chroma_vector_db_crud(tmp_path: Path):
    pytest.importorskip("chromadb")
    db = ChromaVectorDB(tmp_path / "vector")
    records = [
        {
            "row_idx": 0,
            "record_id": "gene:BRCA1",
            "text_sha256": "a",
            "metadata": {"kind": "gene", "symbol": "BRCA1"},
        },
        {
            "row_idx": 1,
            "record_id": "gene:TP53",
            "text_sha256": "b",
            "metadata": {"kind": "gene", "symbol": "TP53"},
        },
    ]
    matrix = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)

    db.add_records("text", records, matrix)
    hits = db.search("text", np.asarray([1.0, 0.0, 0.0], dtype=np.float32), top_k=1)
    assert hits[0].record_id == "gene:BRCA1"

    updated = [
        {
            "row_idx": 0,
            "record_id": "gene:BRCA1",
            "text_sha256": "c",
            "metadata": {"kind": "gene", "symbol": "BRCA1A"},
        }
    ]
    db.update_records("text", updated, embeddings=np.asarray([[0.0, 0.0, 1.0]], dtype=np.float32))
    fetched = db.get_records("text", record_ids=["gene:BRCA1"])
    assert fetched[0]["metadata"]["symbol"] == "BRCA1A"

    upserted = [
        {
            "row_idx": 2,
            "record_id": "gene:EGFR",
            "text_sha256": "d",
            "metadata": {"kind": "gene", "symbol": "EGFR"},
        }
    ]
    db.upsert_records("text", upserted, np.asarray([[0.0, 0.0, 1.0]], dtype=np.float32))
    assert db.collection_info("text")["count"] == 3

    result = db.delete_records("text", record_ids=["gene:TP53"])
    assert result["deleted"] == 1
    assert db.collection_info("text")["count"] == 2

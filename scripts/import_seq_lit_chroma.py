#!/usr/bin/env python3
"""Import SeqLit-DAG documents into Chroma with a CPU smoke-test embedder."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.retrieval.vector import HashingEmbedder
from dnarag.retrieval.vector_db import ChromaVectorDB


def main() -> None:
    args = parse_args()
    rows = load_documents(Path(args.documents), args.limit)
    embedder = HashingEmbedder(dim=args.dim)
    matrix = embedder.embed([str(row["text"]) for row in rows])
    records = [to_vector_record(row, index) for index, row in enumerate(rows)]
    db = ChromaVectorDB(Path(args.vector_dir))
    info = db.upsert_collection(
        target=args.target,
        matrix=matrix,
        records=records,
        backend="hashing-smoke-test",
        model="blake2b-token-hashing",
        pooling="bag-of-tokens",
        batch_size=args.batch_size,
        reset=args.reset,
    )
    print(json.dumps({"scientific_baseline": False, "gpu_required": False, "collection": info}, indent=2))


def load_documents(path: Path, limit: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows


def to_vector_record(row: dict[str, object], row_idx: int) -> dict[str, object]:
    text = str(row.get("text") or "")
    metadata = dict(row.get("metadata") or {})
    metadata.update(
        {
            "kind": str(row.get("modality") or ""),
            "source_id": str(row.get("accession") or row.get("record_id") or ""),
            "symbol": str(row.get("symbol") or ""),
            "source": str(row.get("source") or ""),
            "partition": str(row.get("partition") or ""),
            "labels": row.get("labels") or {},
        }
    )
    return {
        "id": str(row["id"]),
        "row_idx": row_idx,
        "record_id": str(row["record_id"]),
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "metadata": metadata,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import SeqLit-DAG documents into persistent Chroma")
    parser.add_argument("--documents", default="data/seq_lit_dag_swissprot_sample/documents.jsonl")
    parser.add_argument("--vector-dir", default="indexes/seq_lit_dag_swissprot_sample/vector")
    parser.add_argument("--target", default="seq_lit_dag_smoke")
    parser.add_argument("--dim", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--reset", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()

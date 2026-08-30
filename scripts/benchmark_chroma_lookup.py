#!/usr/bin/env python3
"""Benchmark lookup-only latency of a persistent Chroma collection."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.retrieval.vector_db import ChromaVectorDB
from scripts.benchmark_faiss_lookup import load_chroma_embeddings


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    db = ChromaVectorDB(config.vector_dir)
    info = db.collection_info(args.target)
    if not info or int(info.get("count") or 0) == 0:
        raise SystemExit(f"Missing or empty Chroma collection: {args.target}")

    embeddings = load_chroma_embeddings(
        db,
        args.target,
        limit=min(int(args.limit), int(info.get("count") or args.limit)),
        batch_size=int(args.fetch_batch_size),
    )
    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise SystemExit(f"No embeddings returned for Chroma collection: {args.target}")
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-12)

    rng = random.Random(args.seed)
    query_count = min(max(int(args.queries), 1), embeddings.shape[0])
    query_indices = [rng.randrange(embeddings.shape[0]) for _ in range(query_count)]
    queries = np.ascontiguousarray(embeddings[query_indices].astype(np.float32))
    collection = db._collection(args.target)
    warmup = min(int(args.warmup), query_count)
    if warmup:
        collection.query(query_embeddings=queries[:warmup].tolist(), n_results=int(args.top_k), include=["distances"])

    started = time.perf_counter()
    for start in range(0, query_count, int(args.batch_size)):
        batch = queries[start : start + int(args.batch_size)]
        collection.query(query_embeddings=batch.tolist(), n_results=int(args.top_k), include=["distances"])
    elapsed_s = time.perf_counter() - started
    result: dict[str, Any] = {
        "target": args.target,
        "collection_count": int(info.get("count") or 0),
        "indexed_count": int(embeddings.shape[0]),
        "dim": int(embeddings.shape[1]),
        "top_k": int(args.top_k),
        "query_count": int(query_count),
        "batch_size": int(args.batch_size),
        "search_elapsed_s": round(elapsed_s, 6),
        "queries_per_second": round(query_count / elapsed_s, 3) if elapsed_s > 0 else None,
        "lookup_ms_per_query": round((elapsed_s / query_count) * 1000, 6) if query_count else None,
        "notes": "Chroma lookup only; query vectors are sampled from the resident collection and query embedding is excluded.",
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark lookup-only latency of a Chroma collection")
    parser.add_argument("--config", required=True)
    parser.add_argument("--target", default="dna_sequence_window")
    parser.add_argument("--limit", type=int, default=20000)
    parser.add_argument("--fetch-batch-size", type=int, default=5000)
    parser.add_argument("--queries", type=int, default=10000)
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--warmup", type=int, default=128)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()

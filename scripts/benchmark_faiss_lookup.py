#!/usr/bin/env python3
"""Benchmark FAISS lookup latency from an existing Chroma collection.

This intentionally measures vector-index lookup only. It does not include
OmniGene query embedding time, BLAST time, graph expansion, or evidence merging.
"""
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


def main() -> None:
    args = parse_args()
    try:
        import faiss
    except Exception as exc:
        raise SystemExit("Install faiss-cpu or faiss-gpu to run this benchmark") from exc

    config = load_config(args.config)
    db = ChromaVectorDB(config.vector_dir)
    info = db.collection_info(args.target)
    if not info or int(info.get("count") or 0) == 0:
        raise SystemExit(f"Missing or empty Chroma collection: {args.target}")

    load_limit = min(int(args.limit), int(info.get("count") or args.limit))
    embeddings = load_chroma_embeddings(
        db,
        args.target,
        limit=load_limit,
        batch_size=int(args.fetch_batch_size),
    )
    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise SystemExit(f"No embeddings returned for Chroma collection: {args.target}")

    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(np.ascontiguousarray(embeddings))

    gpu_requested = bool(args.gpu)
    gpu_used = False
    gpu_count = int(faiss.get_num_gpus()) if hasattr(faiss, "get_num_gpus") else 0
    if gpu_requested:
        if gpu_count <= 0:
            raise SystemExit("FAISS reports zero GPUs; install faiss-gpu in a CUDA-enabled environment")
        if args.blackwell_guard and is_blackwell_gpu():
            raise SystemExit(
                "FAISS GPU is installed, but this machine appears to use a Blackwell GPU "
                "(compute capability >= 12.0). The current faiss-gpu-cu12 wheel can abort "
                "with CUDA error 209: no kernel image is available for execution on the device. "
                "Use CPU mode, a Blackwell-compatible FAISS build/container, or pass "
                "--no-blackwell-guard to try anyway."
            )
        resources = faiss.StandardGpuResources()
        index = faiss.index_cpu_to_gpu(resources, int(args.gpu_id), index)
        gpu_used = True

    rng = random.Random(args.seed)
    query_count = min(max(int(args.queries), 1), embeddings.shape[0])
    query_indices = [rng.randrange(embeddings.shape[0]) for _ in range(query_count)]
    queries = np.ascontiguousarray(embeddings[query_indices].astype(np.float32))
    faiss.normalize_L2(queries)

    warmup = min(int(args.warmup), query_count)
    if warmup:
        index.search(queries[:warmup], int(args.top_k))

    started = time.perf_counter()
    for start in range(0, query_count, int(args.batch_size)):
        batch = queries[start : start + int(args.batch_size)]
        index.search(batch, int(args.top_k))
    elapsed_s = time.perf_counter() - started

    result: dict[str, Any] = {
        "target": args.target,
        "collection_count": int(info.get("count") or 0),
        "indexed_count": int(embeddings.shape[0]),
        "dim": int(embeddings.shape[1]),
        "top_k": int(args.top_k),
        "query_count": int(query_count),
        "batch_size": int(args.batch_size),
        "faiss_gpu_requested": gpu_requested,
        "faiss_gpu_used": gpu_used,
        "faiss_gpu_count": gpu_count,
        "search_elapsed_s": round(elapsed_s, 6),
        "queries_per_second": round(query_count / elapsed_s, 3) if elapsed_s > 0 else None,
        "lookup_ms_per_query": round((elapsed_s / query_count) * 1000, 6) if query_count else None,
        "notes": "FAISS lookup only; excludes query embedding and hybrid merge/rerank.",
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def load_chroma_embeddings(
    db: ChromaVectorDB,
    target: str,
    *,
    limit: int,
    batch_size: int,
) -> np.ndarray:
    """Fetch embeddings in batches to avoid Chroma/SQLite variable limits."""
    collection = db._collection(target)
    rows: list[np.ndarray] = []
    fetch_batch = max(int(batch_size), 1)
    for offset in range(0, max(int(limit), 1), fetch_batch):
        current = min(fetch_batch, int(limit) - offset)
        result = collection.get(
            limit=current,
            offset=offset,
            include=["embeddings"],
        )
        embeddings = result.get("embeddings")
        if embeddings is None:
            continue
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim == 2 and matrix.shape[0] > 0:
            rows.append(matrix)
    if not rows:
        return np.zeros((0, 0), dtype=np.float32)
    return np.vstack(rows).astype(np.float32, copy=False)


def is_blackwell_gpu() -> bool:
    try:
        import torch
    except Exception:
        return False
    try:
        if not torch.cuda.is_available():
            return False
        major, _minor = torch.cuda.get_device_capability(0)
    except Exception:
        return False
    return int(major) >= 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark FAISS lookup from a Chroma collection")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--target", default="protein_sequence_window")
    parser.add_argument("--limit", type=int, default=10000, help="Embeddings to load from Chroma")
    parser.add_argument("--fetch-batch-size", type=int, default=5000, help="Chroma embedding fetch batch size")
    parser.add_argument("--queries", type=int, default=1000, help="Sampled in-index query vectors")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--warmup", type=int, default=32)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--gpu", action="store_true", help="Move the FAISS index to GPU")
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument(
        "--no-blackwell-guard",
        dest="blackwell_guard",
        action="store_false",
        help="Try FAISS GPU even on Blackwell GPUs where the wheel may lack sm_120 kernels",
    )
    parser.set_defaults(blackwell_guard=True)
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    return parser.parse_args()


if __name__ == "__main__":
    main()

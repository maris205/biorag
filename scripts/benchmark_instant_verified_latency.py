#!/usr/bin/env python3
"""Benchmark latency components for instant and verified BioRAG modes.

This script measures online retrieval stages that can be served from existing
indexes:

- Chroma vector lookup with precomputed in-index query embeddings.
- Local BLAST for sequence queries from a benchmark JSONL file.
- SQLite DRAG graph expansion from existing view graphs.

It intentionally excludes model cold start, query embedding generation, LLM
answer generation, and network calls. For an instant UI, query embeddings should
be produced by a resident GPU model service; this benchmark isolates the indexed
retrieval work that happens after that embedding is available.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.localdb.graph import GraphStore
from dnarag.retrieval.sequence import BlastUnavailable, LocalBlastSearch, detect_sequence
from dnarag.retrieval.vector_db import ChromaVectorDB


DEFAULT_GRAPHS = (
    "indexes/standard/graph/views/dna_sequence_window_hybrid_10k.sqlite,"
    "indexes/standard/graph/views/protein_sequence_window_hybrid_10k.sqlite"
)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    result: dict[str, Any] = {
        "benchmark": {
            "config": args.config,
            "vector_dir": str(config.vector_dir),
            "benchmark_jsonl": args.benchmark,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "scope": {
            "query_embedding_generation": "excluded",
            "model_cold_start": "excluded",
            "llm_generation": "excluded",
            "network_calls": "excluded",
            "vector_lookup_note": (
                "Chroma lookup is measured with sampled existing embeddings as query vectors. "
                "This approximates online lookup after a resident embedding service has produced the query vector."
            ),
        },
        "vector_lookup": {},
        "blast": {},
        "graph_expansion": {},
        "composite_profiles": {},
    }

    if not args.skip_vector:
        result["vector_lookup"] = benchmark_vector_lookup(
            config_vector_dir=config.vector_dir,
            targets=split_csv(args.targets),
            sample_count=args.vector_samples,
            top_k=args.vector_top_k,
            warmup=args.vector_warmup,
        )
    if not args.skip_blast:
        result["blast"] = benchmark_blast(
            benchmark_path=Path(args.benchmark),
            blast_db=config.blast_db,
            blastn_db=config.blastn_db,
            per_modality_limit=args.blast_query_limit,
            max_targets=args.blast_max_targets,
        )
    if not args.skip_graph:
        result["graph_expansion"] = benchmark_graph_expansion(
            graph_paths=[Path(item) for item in split_csv(args.graphs)],
            sample_count=args.graph_samples,
            expand_limit=args.graph_expand_limit,
        )

    result["composite_profiles"] = composite_profiles(
        vector=result.get("vector_lookup") or {},
        blast=result.get("blast") or {},
        graph=result.get("graph_expansion") or {},
    )

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def benchmark_vector_lookup(
    *,
    config_vector_dir: Path,
    targets: list[str],
    sample_count: int,
    top_k: int,
    warmup: int,
) -> dict[str, Any]:
    db = ChromaVectorDB(config_vector_dir)
    results: dict[str, Any] = {}
    for target in targets:
        info = db.collection_info(target)
        if not info or int(info.get("count") or 0) <= 0:
            results[target] = {"status": "missing_or_empty", "target": target}
            continue
        fetch_count = max(int(sample_count) + int(warmup), 1)
        records = db.get_records(target, limit=fetch_count, include_embeddings=True)
        query_rows = [
            {
                "record_id": record.get("record_id"),
                "row_idx": record.get("row_idx"),
                "embedding": np.asarray(record.get("embedding"), dtype=np.float32),
            }
            for record in records
            if record.get("embedding") is not None
        ]
        query_rows = [row for row in query_rows if row["embedding"].ndim == 1 and row["embedding"].size]
        if not query_rows:
            results[target] = {"status": "no_embeddings", "target": target, "collection": info}
            continue

        warmup_rows = query_rows[: min(int(warmup), len(query_rows))]
        timed_rows = query_rows[len(warmup_rows) : len(warmup_rows) + int(sample_count)]
        if not timed_rows:
            timed_rows = query_rows[: min(int(sample_count), len(query_rows))]

        for row in warmup_rows:
            db.search(target, row["embedding"], top_k=top_k)

        durations_ms: list[float] = []
        hit_counts: list[int] = []
        for row in timed_rows:
            started = time.perf_counter()
            hits = db.search(target, row["embedding"], top_k=top_k)
            durations_ms.append((time.perf_counter() - started) * 1000)
            hit_counts.append(len(hits))

        results[target] = {
            "status": "ok",
            "target": target,
            "collection_count": int(info.get("count") or 0),
            "dim": int((info.get("metadata") or {}).get("dim") or 0),
            "backend": (info.get("metadata") or {}).get("backend"),
            "model": (info.get("metadata") or {}).get("model"),
            "top_k": int(top_k),
            "query_count": len(timed_rows),
            "warmup_count": len(warmup_rows),
            "hit_count_summary": summarize_values(hit_counts),
            "latency_ms": summarize_values(durations_ms),
        }
    return results


def benchmark_blast(
    *,
    benchmark_path: Path,
    blast_db: Path,
    blastn_db: Path,
    per_modality_limit: int,
    max_targets: int,
) -> dict[str, Any]:
    if not benchmark_path.exists():
        return {"status": "missing_benchmark", "path": str(benchmark_path)}

    queries = load_sequence_queries(benchmark_path, per_modality_limit=per_modality_limit)
    searcher = LocalBlastSearch(blast_db, nucleotide_db=blastn_db)
    results: dict[str, Any] = {}
    for modality, rows in sorted(queries.items()):
        durations_ms: list[float] = []
        hit_counts: list[int] = []
        statuses: dict[str, int] = defaultdict(int)
        unavailable_error: str | None = None
        for row in rows:
            started = time.perf_counter()
            try:
                outcome = searcher.search(str(row["query"]), max_targets=max_targets)
            except BlastUnavailable as exc:
                unavailable_error = str(exc)
                statuses["unavailable"] += 1
                break
            durations_ms.append((time.perf_counter() - started) * 1000)
            status = str(outcome.get("status") or "unknown")
            statuses[status] += 1
            hit_counts.append(len(outcome.get("hits") or []))
        results[modality] = {
            "status": "unavailable" if unavailable_error else "ok",
            "error": unavailable_error,
            "query_count": len(durations_ms),
            "requested_query_count": len(rows),
            "max_targets": int(max_targets),
            "status_counts": dict(statuses),
            "hit_count_summary": summarize_values(hit_counts),
            "latency_ms": summarize_values(durations_ms),
        }
    return results


def benchmark_graph_expansion(
    *,
    graph_paths: list[Path],
    sample_count: int,
    expand_limit: int,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for graph_path in graph_paths:
        key = graph_path.stem
        if not graph_path.exists():
            results[key] = {"status": "missing", "graph": str(graph_path)}
            continue
        seeds = graph_seed_nodes(graph_path, sample_count=sample_count)
        graph = GraphStore(graph_path)
        durations_ms: list[float] = []
        edge_counts: list[int] = []
        for seed in seeds:
            started = time.perf_counter()
            edges = graph.expand(seed, limit=expand_limit)
            durations_ms.append((time.perf_counter() - started) * 1000)
            edge_counts.append(len(edges))
        results[key] = {
            "status": "ok",
            "graph": str(graph_path),
            "meta": graph_meta(graph_path),
            "seed_count": len(seeds),
            "expand_limit": int(expand_limit),
            "edge_count_summary": summarize_values(edge_counts),
            "latency_ms": summarize_values(durations_ms),
        }
    return results


def load_sequence_queries(path: Path, *, per_modality_limit: int) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {"dna": [], "protein": []}
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            seq = detect_sequence(str(row.get("query") or ""))
            if seq is None:
                continue
            if seq.alphabet == "dna":
                key = "dna"
            elif seq.alphabet == "protein":
                key = "protein"
            else:
                continue
            if len(groups[key]) < per_modality_limit:
                groups[key].append(row)
    return {key: value for key, value in groups.items() if value}


def graph_seed_nodes(graph_path: Path, *, sample_count: int) -> list[str]:
    with sqlite3.connect(f"file:{graph_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """
            SELECT entity_id
            FROM nodes
            ORDER BY entity_id
            LIMIT ?
            """,
            (max(int(sample_count), 1),),
        ).fetchall()
    return [str(row[0]) for row in rows]


def graph_meta(graph_path: Path) -> dict[str, str]:
    with sqlite3.connect(f"file:{graph_path}?mode=ro", uri=True) as conn:
        exists = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'graph_meta'
            """
        ).fetchone()
        if not exists:
            return {}
        rows = conn.execute("SELECT key, value FROM graph_meta ORDER BY key").fetchall()
    return {str(key): str(value) for key, value in rows}


def composite_profiles(
    *,
    vector: dict[str, Any],
    blast: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    profiles: dict[str, Any] = {
        "notes": [
            "Composite values are sums of median route latencies from the same run.",
            "They exclude query embedding and LLM generation.",
            "Verified mode is an engineering profile, not a claim that vector search replaces BLAST.",
        ],
        "instant_vector_only": {},
        "verified_vector_blast_graph": {},
    }
    modality_map = {
        "dna": {
            "vector_target": "dna_sequence_window",
            "graph_contains": "dna_sequence_window",
        },
        "protein": {
            "vector_target": "protein_sequence_window",
            "graph_contains": "protein_sequence_window",
        },
    }
    for modality, mapping in modality_map.items():
        vector_row = vector.get(mapping["vector_target"]) or {}
        vector_latency = nested_latency(vector_row)
        if vector_latency is not None:
            profiles["instant_vector_only"][modality] = {
                "vector_target": mapping["vector_target"],
                "median_ms": round(vector_latency, 6),
                "routes": ["vector"],
            }

        blast_row = blast.get(modality) or {}
        blast_latency = nested_latency(blast_row)
        graph_key, graph_row = first_graph_for_modality(graph, str(mapping["graph_contains"]))
        graph_latency = nested_latency(graph_row)
        parts = {
            "vector_ms": vector_latency,
            "blast_ms": blast_latency,
            "graph_ms": graph_latency,
        }
        if all(value is not None for value in parts.values()):
            profiles["verified_vector_blast_graph"][modality] = {
                "vector_target": mapping["vector_target"],
                "graph": graph_key,
                "median_ms": round(sum(float(value) for value in parts.values() if value is not None), 6),
                "parts_ms": {key: round(float(value), 6) for key, value in parts.items() if value is not None},
                "routes": ["vector", "blast", "graph"],
            }
    return profiles


def first_graph_for_modality(graph: dict[str, Any], contains: str) -> tuple[str | None, dict[str, Any]]:
    for key, row in graph.items():
        if contains in str(key) or contains in str(row.get("graph") or ""):
            return str(key), row
    return None, {}


def nested_latency(row: dict[str, Any]) -> float | None:
    latency = row.get("latency_ms") if isinstance(row, dict) else None
    if not isinstance(latency, dict):
        return None
    value = latency.get("median")
    return float(value) if value is not None else None


def summarize_values(values: Iterable[float | int]) -> dict[str, Any]:
    data = [float(value) for value in values]
    if not data:
        return {"count": 0}
    ordered = sorted(data)
    total = sum(ordered)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 6),
        "median": round(percentile(ordered, 50), 6),
        "mean": round(total / len(ordered), 6),
        "p95": round(percentile(ordered, 95), 6),
        "max": round(ordered[-1], 6),
    }


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark instant and verified BioRAG latency components")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--benchmark", default="benchmarks/sequence_search_100_seed20260516_bio.jsonl")
    parser.add_argument("--targets", default="dna_sequence_window,protein_sequence_window")
    parser.add_argument("--vector-samples", type=int, default=50)
    parser.add_argument("--vector-top-k", type=int, default=10)
    parser.add_argument("--vector-warmup", type=int, default=5)
    parser.add_argument("--blast-query-limit", type=int, default=20, help="Maximum benchmark queries per modality")
    parser.add_argument("--blast-max-targets", type=int, default=10)
    parser.add_argument("--graphs", default=DEFAULT_GRAPHS)
    parser.add_argument("--graph-samples", type=int, default=100)
    parser.add_argument("--graph-expand-limit", type=int, default=12)
    parser.add_argument("--output", default="reports/instant_verified_latency_benchmark.json")
    parser.add_argument("--skip-vector", action="store_true")
    parser.add_argument("--skip-blast", action="store_true")
    parser.add_argument("--skip-graph", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

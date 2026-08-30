#!/usr/bin/env python3
"""Evaluate multi-scale DNA vector retrieval and parent-level RRF fusion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dnarag.retrieval.vector import make_embedder
from eval_dna_embedding_matrix import embed_dna_batches, load_fasta_records, make_windows


def main() -> None:
    args = parse_args()
    records = load_fasta_records(Path(args.index_fasta))
    queries = [json.loads(line) for line in Path(args.benchmark).read_text(encoding="utf-8").splitlines() if line.strip()]
    embedder = make_embedder(args.backend, model_name=args.model, pooling=args.pooling, dtype=args.dtype)
    query_sequences = [clean_dna(row.get("query", "")) for row in queries]
    query_vectors = embed_dna_batches(embedder, query_sequences, batch_size=args.batch_size, orientation="none")
    scale_results: dict[str, list[dict[str, float]]] = {}
    scale_rankings: dict[str, list[list[str]]] = {}
    for scale in args.scales:
        size, stride = (int(value) for value in scale.split(":", 1))
        accessions, sequences = make_windows(records, size=size, stride=stride, min_size=args.min_window_size)
        if args.index_window_limit:
            accessions, sequences = accessions[: args.index_window_limit], sequences[: args.index_window_limit]
        vectors = embed_dna_batches(embedder, sequences, batch_size=args.batch_size, orientation="none")
        rankings: list[list[str]] = []
        rows: list[dict[str, float]] = []
        for row, query_vector in zip(queries, query_vectors):
            scores: dict[str, float] = {}
            for accession, score in zip(accessions, vectors @ query_vector):
                scores[accession] = max(scores.get(accession, -1.0), float(score))
            ranked = [key for key, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
            rankings.append(ranked)
            rows.append(metric_row(row, ranked[: args.top_k], records))
        scale_rankings[scale] = rankings
        scale_results[scale] = rows

    fused_rows: list[dict[str, float]] = []
    for index, row in enumerate(queries):
        rrf: dict[str, float] = {}
        for rankings in scale_rankings.values():
            for rank, accession in enumerate(rankings[index][: args.rrf_depth], start=1):
                rrf[accession] = rrf.get(accession, 0.0) + 1.0 / (args.rrf_k + rank)
        ranked = [key for key, _ in sorted(rrf.items(), key=lambda item: (-item[1], item[0]))]
        fused_rows.append(metric_row(row, ranked[: args.top_k], records))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "model": args.model,
        "backend": args.backend,
        "pooling": args.pooling,
        "benchmark": args.benchmark,
        "index_fasta": args.index_fasta,
        "index_window_limit": args.index_window_limit,
        "scales": args.scales,
        "query_count": len(queries),
        "top_k": args.top_k,
        "rrf": {"k": args.rrf_k, "depth": args.rrf_depth},
        "summary": {"scale_" + scale: summarize(rows) for scale, rows in scale_results.items()},
        "summary_fused_rrf": summarize(fused_rows),
    }
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def metric_row(row: dict, ranked: list[str], records: dict) -> dict[str, float]:
    expected = row.get("expected") or {}
    genes = {str(value).strip().upper() for value in ((expected.get("biological") or {}).get("gene_symbols") or []) if value}
    bio_rank = next((index for index, accession in enumerate(ranked, 1) if genes.intersection(records[accession].genes)), None)
    return {
        "bio_hit_at_1": float(bio_rank == 1),
        "bio_hit_at_5": float(bio_rank is not None and bio_rank <= 5),
        "bio_hit_at_10": float(bio_rank is not None and bio_rank <= 10),
        "bio_mrr": 1.0 / bio_rank if bio_rank else 0.0,
    }


def summarize(rows: list[dict[str, float]]) -> dict[str, float]:
    return {key: float(np.mean([row[key] for row in rows])) for key in rows[0]} if rows else {}


def clean_dna(value: str) -> str:
    return "".join(char for char in str(value).upper() if char in "ACGTN")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="dnabert2")
    parser.add_argument("--model", required=True)
    parser.add_argument("--pooling", default="mean")
    parser.add_argument("--dtype", default="fp32")
    parser.add_argument("--benchmark", default="benchmarks/dna_parent_frag_100.jsonl")
    parser.add_argument("--index-fasta", default="data/heldout/dna_parent_frag_100_controlled20k_index.fasta")
    parser.add_argument("--index-window-limit", type=int, default=20000)
    parser.add_argument("--scales", nargs="+", default=["128:64", "256:128", "512:256"])
    parser.add_argument("--min-window-size", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--rrf-depth", type=int, default=200)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()

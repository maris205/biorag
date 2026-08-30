#!/usr/bin/env python3
"""Evaluate one GPU embedding model on SeqLit-DAG sequence-to-paper paths."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.retrieval.vector import make_embedder
from dnarag.seq_lit_dag.evaluate import load_papers_by_accession, read_jsonl


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    vector_dir = Path(args.vector_dir)
    vector_dir.mkdir(parents=True, exist_ok=True)

    proteins = load_proteins(Path(args.documents))
    queries = read_jsonl(Path(args.queries), limit=args.limit)
    papers_by_accession = load_papers_by_accession(Path(args.graph_db))
    window_accessions, sequences = make_windows(proteins, size=args.window_size, stride=args.window_stride)

    import torch

    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    embedder = make_embedder(
        args.backend,
        model_name=args.model,
        pooling=args.pooling,
        dtype=args.dtype,
    )
    model_load_s = time.perf_counter() - load_started

    index_name = args.index_name or args.name
    index_path = vector_dir / f"{index_name}_protein_window_vectors.npz"
    if args.reuse_index and index_path.exists():
        protein_vectors = np.load(index_path)["vectors"]
        index_embedding_s = 0.0
        index_reused = True
    else:
        started = time.perf_counter()
        protein_vectors = embed_batches(embedder, sequences, args.batch_size)
        index_embedding_s = time.perf_counter() - started
        np.savez_compressed(index_path, vectors=protein_vectors)
        index_reused = False

    query_texts = [str(row["query"]) for row in queries]
    started = time.perf_counter()
    query_vectors = embed_batches(embedder, query_texts, args.batch_size)
    query_embedding_s = time.perf_counter() - started

    details: list[dict[str, Any]] = []
    lookup_times: list[float] = []
    for row, query_vector in zip(queries, query_vectors):
        lookup_started = time.perf_counter()
        scores = protein_vectors @ query_vector
        parent_scores: dict[str, float] = {}
        for index, score in enumerate(scores):
            accession = window_accessions[index]
            parent_scores[accession] = max(parent_scores.get(accession, -1.0), float(score))
        ranked_accessions = [
            accession
            for accession, _score in sorted(parent_scores.items(), key=lambda item: (-item[1], item[0]))[: args.protein_k]
        ]
        lookup_times.append((time.perf_counter() - lookup_started) * 1000.0)
        ranked_pmids = rank_pmids(ranked_accessions, papers_by_accession, args.paper_k)
        expected_accessions = {
            str(item)
            for item in (row.get("relevant_index_accessions") or row.get("expected_accessions") or [])
        }
        expected_pmids = {str(item) for item in row.get("expected_pmids", [])}
        accession_rank = first_rank(ranked_accessions, expected_accessions)
        paper_matches = expected_pmids.intersection(ranked_pmids)
        details.append(
            {
                "query_id": row.get("id"),
                "accession_rank": accession_rank,
                "protein_hit_at_1": bool(accession_rank == 1),
                "protein_hit_at_5": bool(accession_rank and accession_rank <= 5),
                "protein_hit_at_10": bool(accession_rank and accession_rank <= 10),
                "protein_mrr": 1.0 / accession_rank if accession_rank else 0.0,
                "paper_hit": bool(paper_matches),
                "paper_recall": len(paper_matches) / len(expected_pmids) if expected_pmids else 0.0,
                "path_complete": bool(accession_rank and paper_matches),
                "top_accessions": ranked_accessions,
                "top_pmids": ranked_pmids,
            }
        )

    result = {
        "dataset": embedding_dataset_name(queries),
        "claim_scope": embedding_claim_scope(queries),
        "name": args.name,
        "backend": args.backend,
        "model": args.model,
        "pooling": args.pooling,
        "dtype": args.dtype,
        "protein_count": len(proteins),
        "protein_window_count": len(sequences),
        "window_size": args.window_size,
        "window_stride": args.window_stride,
        "query_count": len(queries),
        "protein_k": args.protein_k,
        "paper_k": args.paper_k,
        "summary": summarize(details),
        "timing": {
            "model_load_s": model_load_s,
            "index_embedding_s": index_embedding_s,
            "index_reused": index_reused,
            "query_embedding_total_ms": query_embedding_s * 1000.0,
            "query_embedding_ms_per_query": query_embedding_s * 1000.0 / len(queries) if queries else 0.0,
            "lookup_ms_per_query": float(np.mean(lookup_times)) if lookup_times else 0.0,
            "end_to_end_ms_per_query": (
                query_embedding_s * 1000.0 / len(queries) + float(np.mean(lookup_times)) if queries else 0.0
            ),
        },
        "gpu": {
            "name": torch.cuda.get_device_name(0),
            "peak_memory_gib": torch.cuda.max_memory_allocated() / (1024**3),
        },
        "details": details,
    }
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2, ensure_ascii=False))


def embed_batches(embedder: Any, texts: list[str], batch_size: int) -> np.ndarray:
    chunks: list[np.ndarray] = []
    progress_every = max((len(texts) // max(batch_size, 1)) // 20, 1)
    for start in range(0, len(texts), max(batch_size, 1)):
        end = min(start + max(batch_size, 1), len(texts))
        chunks.append(embedder.embed(texts[start:end]))
        batch_index = start // max(batch_size, 1)
        if batch_index % progress_every == 0 or end == len(texts):
            print(json.dumps({"embedded": end, "total": len(texts)}), flush=True)
    return np.concatenate(chunks, axis=0) if chunks else np.zeros((0, 0), dtype=np.float32)


def load_proteins(path: Path) -> dict[str, str]:
    proteins: dict[str, str] = {}
    for row in read_jsonl(path):
        if row.get("modality") != "protein_sequence":
            continue
        sequence = str(row.get("text") or "").partition("Sequence:\n")[2]
        if sequence:
            proteins[str(row["accession"])] = sequence
    return proteins


def make_windows(proteins: dict[str, str], *, size: int, stride: int) -> tuple[list[str], list[str]]:
    accessions: list[str] = []
    windows: list[str] = []
    for accession, sequence in proteins.items():
        starts = list(range(0, max(len(sequence) - size + 1, 1), max(stride, 1)))
        tail_start = max(len(sequence) - size, 0)
        if tail_start not in starts:
            starts.append(tail_start)
        for start in sorted(set(starts)):
            window = sequence[start : start + size]
            if len(window) >= min(24, size):
                accessions.append(accession)
                windows.append(window)
    return accessions, windows


def rank_pmids(accessions: list[str], mapping: dict[str, list[str]], limit: int) -> list[str]:
    ranked: list[str] = []
    seen: set[str] = set()
    for accession in accessions:
        for pmid in mapping.get(accession, []):
            if pmid not in seen:
                seen.add(pmid)
                ranked.append(pmid)
                if len(ranked) >= limit:
                    return ranked
    return ranked


def first_rank(items: list[str], expected: set[str]) -> int | None:
    return next((index for index, item in enumerate(items, start=1) if item in expected), None)


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = ["protein_hit_at_1", "protein_hit_at_5", "protein_hit_at_10", "protein_mrr", "paper_hit", "paper_recall", "path_complete"]
    return {key: sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0 for key in keys}


def embedding_dataset_name(queries: list[dict[str, Any]]) -> str:
    task = embedding_query_task(queries)
    if task.startswith("uniref50_cluster_heldout"):
        return "BioRAG-SeqLit-DAG UniRef50-cluster-held-out embedding path evaluation"
    if task.startswith("identity_cluster_heldout"):
        return "BioRAG-SeqLit-DAG identity-cluster-held-out embedding path stress test"
    if queries and queries[0].get("relevant_index_accessions"):
        return "BioRAG-SeqLit-DAG held-out embedding path evaluation"
    return "BioRAG-SeqLit-DAG in-index embedding path evaluation"


def embedding_claim_scope(queries: list[dict[str, Any]]) -> str:
    task = embedding_query_task(queries)
    if task.startswith("uniref50_cluster_heldout"):
        return (
            "The query protein and every protein assigned to the same observed UniRef50 cluster are absent "
            "from the index. Relevant candidates and papers are curated split labels, not model outputs; this "
            "small control is not a Pfam-clan, species, temporal, or remote-homology benchmark."
        )
    if task.startswith("identity_cluster_heldout"):
        return (
            "The query protein and its full BLASTP connected component at the configured identity and "
            "shorter-sequence coverage thresholds are absent from the index. Queries intentionally prioritize "
            "non-singleton components, making this a cluster-stratified stress test rather than a prevalence sample."
        )
    if queries and queries[0].get("relevant_index_accessions"):
        return (
            "Held-out parent accessions are absent from the index. Relevant candidates and papers come from "
            "curated split labels, not model outputs."
        )
    return (
        "Queries are windows from indexed parent proteins. This evaluates model integration and evidence-path "
        "behavior, not held-out homology competitiveness."
    )


def embedding_query_task(queries: list[dict[str, Any]]) -> str:
    return str(queries[0].get("task") or "") if queries else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a protein embedding model on SeqLit-DAG")
    root = "data/seq_lit_dag_swissprot_sample"
    parser.add_argument("--name", required=True)
    parser.add_argument("--index-name", default=None, help="Shared vector artifact name for multiple K budgets")
    parser.add_argument("--backend", required=True, choices=["prott5", "esm", "omnigene"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--pooling", default="mean", choices=["mean", "last"])
    parser.add_argument("--dtype", default="bf16", choices=["bf16", "fp16", "fp32", "auto"])
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--documents", default=f"{root}/documents.jsonl")
    parser.add_argument("--queries", default=f"{root}/sample_queries.jsonl")
    parser.add_argument("--graph-db", default=f"{root}/graph.sqlite")
    parser.add_argument("--vector-dir", default="indexes/seq_lit_dag_swissprot_sample/embedding_eval")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--protein-k", type=int, default=10)
    parser.add_argument("--paper-k", type=int, default=50)
    parser.add_argument("--window-size", type=int, default=128)
    parser.add_argument("--window-stride", type=int, default=64)
    parser.add_argument("--reuse-index", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()

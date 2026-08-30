#!/usr/bin/env python3
"""Evaluate CPU candidate routes on the held-out SeqLit-DAG split."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.seq_lit_dag.evaluate import (
    ProteinCandidate,
    batch_blast_candidates,
    kmer_candidates,
    load_papers_by_accession,
    load_protein_sequences,
    rank_papers,
    read_jsonl,
)


def main() -> None:
    args = parse_args()
    queries = read_jsonl(Path(args.queries))
    sequences = load_protein_sequences(Path(args.documents))
    papers_by_accession = load_papers_by_accession(Path(args.graph_db))
    blast_results: dict[str, list[ProteinCandidate]] = {}
    blast_ms = 0.0
    if args.blast_db:
        blast_results, elapsed = batch_blast_candidates(
            queries, blast_db=Path(args.blast_db), limit=args.protein_k
        )
        blast_ms = elapsed / len(queries) if queries else 0.0

    rng = random.Random(args.seed)
    accessions = sorted(sequences)
    rows: list[dict[str, Any]] = []
    for query in queries:
        query_id = str(query["id"])
        methods: dict[str, tuple[list[ProteinCandidate], float]] = {}
        shuffled = accessions[:]
        rng.shuffle(shuffled)
        methods["random"] = ([ProteinCandidate(item, 0.0) for item in shuffled[: args.protein_k]], 0.0)
        started = time.perf_counter()
        kmer = kmer_candidates(str(query["query"]), sequences, k=args.kmer_size, limit=args.protein_k)
        methods["kmer_jaccard"] = (kmer, (time.perf_counter() - started) * 1000.0)
        if blast_results:
            methods["blast"] = (blast_results.get(query_id, []), blast_ms)
        for method, (candidates, latency_ms) in methods.items():
            rows.append(
                evaluate_one(
                    query,
                    method=method,
                    candidates=candidates,
                    papers_by_accession=papers_by_accession,
                    paper_k=args.paper_k,
                    latency_ms=latency_ms,
                )
            )

    result = {
        "dataset": dataset_name(queries),
        "claim_scope": claim_scope(queries),
        "query_count": len(queries),
        "index_protein_count": len(sequences),
        "protein_k": args.protein_k,
        "paper_k": args.paper_k,
        "summary": {
            method: summarize([row for row in rows if row["method"] == method])
            for method in sorted({row["method"] for row in rows})
        },
        "details": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2))


def evaluate_one(
    query: dict[str, Any],
    *,
    method: str,
    candidates: list[ProteinCandidate],
    papers_by_accession: dict[str, list[str]],
    paper_k: int,
    latency_ms: float,
) -> dict[str, Any]:
    ranked_accessions = [candidate.accession for candidate in candidates]
    relevant_accessions = {str(item) for item in query.get("relevant_index_accessions", [])}
    expected_pmids = {str(item) for item in query.get("expected_pmids", [])}
    candidate_rank = first_rank(ranked_accessions, relevant_accessions)
    ranked_pmids = rank_papers(candidates, papers_by_accession, limit=paper_k)
    matched_pmids = expected_pmids.intersection(ranked_pmids)
    return {
        "query_id": query["id"],
        "method": method,
        "candidate_rank": candidate_rank,
        "candidate_hit_at_1": bool(candidate_rank == 1),
        "candidate_hit_at_5": bool(candidate_rank and candidate_rank <= 5),
        "candidate_hit_at_10": bool(candidate_rank and candidate_rank <= 10),
        "candidate_mrr": 1.0 / candidate_rank if candidate_rank else 0.0,
        "paper_hit": bool(matched_pmids),
        "paper_recall": len(matched_pmids) / len(expected_pmids) if expected_pmids else 0.0,
        "path_complete": bool(candidate_rank and matched_pmids),
        "candidate_ms": latency_ms,
        "top_accessions": ranked_accessions,
        "top_pmids": ranked_pmids,
    }


def first_rank(items: list[str], expected: set[str]) -> int | None:
    return next((index for index, item in enumerate(items, start=1) if item in expected), None)


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = [
        "candidate_hit_at_1",
        "candidate_hit_at_5",
        "candidate_hit_at_10",
        "candidate_mrr",
        "paper_hit",
        "paper_recall",
        "path_complete",
        "candidate_ms",
    ]
    return {key: sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0 for key in keys}


def dataset_name(queries: list[dict[str, Any]]) -> str:
    task = query_task(queries)
    if task.startswith("uniref50_cluster_heldout"):
        return "BioRAG-SeqLit-DAG UniRef50-cluster-held-out path evaluation"
    if task.startswith("identity_cluster_heldout"):
        return "BioRAG-SeqLit-DAG identity-cluster-held-out path stress test"
    if queries and queries[0].get("expected_go_ids"):
        return "BioRAG-SeqLit-DAG held-out sequence-to-function-to-paper pilot"
    return "BioRAG-SeqLit-DAG held-out parent direct-paper pilot"


def claim_scope(queries: list[dict[str, Any]]) -> str:
    task = query_task(queries)
    if task.startswith("uniref50_cluster_heldout"):
        return (
            "The query protein and every protein assigned to the same observed UniRef50 cluster are absent "
            "from the index. Relevance is low-frequency shared GO plus index-side GOA paper evidence. This "
            "small control does not establish Pfam-clan, species, temporal, or remote-homology generalization."
        )
    if task.startswith("identity_cluster_heldout"):
        return (
            "The query protein and its full BLASTP connected component at the configured identity and "
            "shorter-sequence coverage thresholds are absent from the index. Queries intentionally prioritize "
            "non-singleton components, so this is a cluster-stratified stress test rather than a prevalence sample."
        )
    if queries and queries[0].get("expected_go_ids"):
        return (
            "Held-out parent accessions are absent from the index. Relevance is low-frequency shared GO plus "
            "index-side GOA paper evidence; retrieval models do not generate labels."
        )
    return (
        "Held-out parent accessions are absent from the index. Relevance is curated shared-PMID connectivity, "
        "not general paper topical relevance or held-out family homology."
    )


def query_task(queries: list[dict[str, Any]]) -> str:
    return str(queries[0].get("task") or "") if queries else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate held-out SeqLit-DAG CPU baselines")
    root = "data/seq_lit_dag_heldout"
    parser.add_argument("--queries", default=f"{root}/queries.jsonl")
    parser.add_argument("--documents", default=f"{root}/index_documents.jsonl")
    parser.add_argument("--graph-db", default="data/seq_lit_dag_swissprot_sample/graph.sqlite")
    parser.add_argument("--blast-db", default=f"{root}/blast/index")
    parser.add_argument("--output", default="reports/results/seq_lit_dag_heldout_cpu.json")
    parser.add_argument("--protein-k", type=int, default=10)
    parser.add_argument("--paper-k", type=int, default=50)
    parser.add_argument("--kmer-size", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260720)
    return parser.parse_args()


if __name__ == "__main__":
    main()

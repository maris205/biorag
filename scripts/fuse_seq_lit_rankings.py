#!/usr/bin/env python3
"""Fuse saved SeqLit-DAG candidate rankings without rerunning retrieval models."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.seq_lit_dag.evaluate import ProteinCandidate, load_papers_by_accession, rank_papers


def main() -> None:
    args = parse_args()
    left = load_by_query(Path(args.left), method=args.left_method)
    right = load_by_query(Path(args.right), method=args.right_method)
    queries = load_queries(Path(args.queries))
    papers = load_papers_by_accession(Path(args.graph_db))
    rows: list[dict[str, Any]] = []
    for query_id in sorted(set(left) & set(right) & set(queries)):
        ranking = reciprocal_rank_fusion(
            [left[query_id]["top_accessions"], right[query_id]["top_accessions"]],
            limit=args.protein_k,
            rrf_k=args.rrf_k,
        )
        query = queries[query_id]
        expected_accessions = {str(item) for item in query["relevant_index_accessions"]}
        expected_pmids = {str(item) for item in query["expected_pmids"]}
        rank = first_rank(ranking, expected_accessions)
        candidates = [ProteinCandidate(accession, 1.0 / index) for index, accession in enumerate(ranking, start=1)]
        ranked_pmids = rank_papers(candidates, papers, limit=args.paper_k)
        matched_pmids = expected_pmids.intersection(ranked_pmids)
        rows.append(
            {
                "query_id": query_id,
                "method": args.name,
                "candidate_rank": rank,
                "candidate_hit_at_1": bool(rank == 1),
                "candidate_hit_at_5": bool(rank and rank <= 5),
                "candidate_hit_at_10": bool(rank and rank <= 10),
                "candidate_mrr": 1.0 / rank if rank else 0.0,
                "paper_hit": bool(matched_pmids),
                "paper_recall": len(matched_pmids) / len(expected_pmids) if expected_pmids else 0.0,
                "path_complete": bool(rank and matched_pmids),
                "top_accessions": ranking,
                "top_pmids": ranked_pmids,
            }
        )
    result = {
        "dataset": "BioRAG-SeqLit-DAG saved-ranking fusion ablation",
        "claim_scope": "Heuristic reciprocal-rank fusion ablation over independently saved candidate rankings.",
        "name": args.name,
        "query_count": len(rows),
        "protein_k": args.protein_k,
        "paper_k": args.paper_k,
        "rrf_k": args.rrf_k,
        "summary": summarize(rows),
        "details": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2))


def reciprocal_rank_fusion(rankings: list[list[str]], *, limit: int, rrf_k: int) -> list[str]:
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        for rank, accession in enumerate(ranking, start=1):
            scores[accession] = scores.get(accession, 0.0) + 1.0 / (rrf_k + rank)
            best_rank[accession] = min(best_rank.get(accession, rank), rank)
    return [
        accession
        for accession in sorted(scores, key=lambda item: (-scores[item], best_rank[item], item))[:limit]
    ]


def load_by_query(path: Path, *, method: str | None = None) -> dict[str, dict[str, Any]]:
    result = json.loads(path.read_text(encoding="utf-8"))
    rows = result["details"]
    if method is not None:
        rows = [row for row in rows if str(row.get("method")) == method]
    return {str(row["query_id"]): row for row in rows}


def load_queries(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def first_rank(items: list[str], expected: set[str]) -> int | None:
    return next((rank for rank, item in enumerate(items, start=1) if item in expected), None)


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = ("candidate_hit_at_1", "candidate_hit_at_5", "candidate_hit_at_10", "candidate_mrr", "paper_hit", "paper_recall", "path_complete")
    return {key: sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0 for key in keys}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fuse two saved SeqLit-DAG rankings")
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--left-method", default=None)
    parser.add_argument("--right-method", default=None)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--graph-db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--name", default="prott5_blast_rrf")
    parser.add_argument("--protein-k", type=int, default=50)
    parser.add_argument("--paper-k", type=int, default=200)
    parser.add_argument("--rrf-k", type=int, default=60)
    return parser.parse_args()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sweep vector candidate budgets for candidate-subset BLAST reranking.

This is a diagnostic experiment for the Plan 1 bottleneck identified in
``evaluate_vector_blast_rerank.py``: candidate-subset BLAST can only verify
what vector retrieval placed in the candidate pool.

By default the script performs a prefix sweep from one max-budget vector search
per query. This isolates the effect of candidate budget and candidate-subset
BLAST size. It is not a lookup-latency benchmark for each budget; use the
single-budget evaluator for exact per-budget latency.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.evaluation import first_biological_match_rank, first_match_rank, has_biological_expected, load_benchmark
from dnarag.retrieval.hybrid import HybridBioSearch
from dnarag.retrieval.sequence import detect_sequence
from scripts.evaluate_vector_blast_rerank import (
    parent_candidates,
    rerank_candidates,
    run_candidate_blast,
    summarize_rows,
)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    budgets = sorted({int(item) for item in args.budgets.split(",") if item.strip()})
    if not budgets:
        raise SystemExit("--budgets must contain at least one integer")
    max_budget = max(budgets)
    tasks = load_benchmark(args.benchmark)
    if args.limit:
        tasks = tasks[: max(int(args.limit), 0)]
    if args.categories:
        wanted = {item.strip() for item in args.categories.split(",") if item.strip()}
        tasks = [task for task in tasks if task.category in wanted]

    searcher = HybridBioSearch(config)
    started = time.perf_counter()
    details: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        if args.progress:
            print(f"[candidate-sweep] vector {index}/{len(tasks)} {task.task_id}", flush=True)
        task_result = vector_candidates_for_task(searcher, task, max_budget=max_budget)
        vector_rows.append(task_result["vector_row"])
        for budget in budgets:
            if args.progress:
                print(f"[candidate-sweep] blast {task.task_id} budget={budget}", flush=True)
            row = evaluate_budget(
                task_result,
                task=task,
                budget=budget,
                protein_db=config.blast_db,
                nucleotide_db=config.blastn_db,
                final_limit=args.final_limit,
                append_unaligned=args.append_unaligned,
                blast_max_targets=max(args.blast_top_k, budget, args.final_limit),
            )
            details.append(row)

    result = {
        "dataset": "dnarag_vector_candidate_budget_sweep",
        "config": args.config,
        "benchmark": args.benchmark,
        "mode": "prefix_from_max_budget_vector_search",
        "mode_note": (
            "Each query is vector-searched once at the max budget. Smaller budgets use prefixes "
            "of that candidate list, so this isolates candidate-pool and candidate-BLAST effects; "
            "it is not a fair per-budget vector lookup latency benchmark."
        ),
        "task_count": len(tasks),
        "budgets": budgets,
        "max_budget": max_budget,
        "final_limit": args.final_limit,
        "blast_top_k": args.blast_top_k,
        "append_unaligned": args.append_unaligned,
        "summary_by_budget": summarize_by_budget(details),
        "category_summary_by_budget": summarize_category_by_budget(details),
        "query_type_summary_by_budget": summarize_query_type_by_budget(details),
        "vector_search_summary": summarize_vector_rows(vector_rows),
        "details": details,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2, ensure_ascii=False))


def vector_candidates_for_task(searcher: HybridBioSearch, task: Any, *, max_budget: int) -> dict[str, Any]:
    started = time.perf_counter()
    seq = detect_sequence(task.query)
    if seq is None or seq.alphabet not in {"dna", "protein"}:
        return {
            "task_id": task.task_id,
            "sequence": None,
            "alphabet": None,
            "candidates": [],
            "vector_row": {
                "task_id": task.task_id,
                "category": task.category,
                "query_type": task.query_type,
                "status": "not_sequence",
                "candidate_count": 0,
                "vector_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        }
    result = searcher.search(
        task.query,
        modes=["vector"],
        limit=max_budget,
        vector_target=task.vector_target,
    )
    vector_latency_ms = (time.perf_counter() - started) * 1000
    candidates = parent_candidates(list(result.get("evidence") or []), sequence_alphabet=seq.alphabet)
    return {
        "task_id": task.task_id,
        "sequence": seq.sequence,
        "alphabet": seq.alphabet,
        "candidates": candidates,
        "vector_trace": result.get("retrieval_trace") or [],
        "vector_row": {
            "task_id": task.task_id,
            "category": task.category,
            "query_type": task.query_type,
            "status": "ok",
            "candidate_count": len(candidates),
            "vector_latency_ms": round(vector_latency_ms, 3),
        },
    }


def evaluate_budget(
    task_result: dict[str, Any],
    *,
    task: Any,
    budget: int,
    protein_db: Path,
    nucleotide_db: Path,
    final_limit: int,
    append_unaligned: bool,
    blast_max_targets: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    candidates = list(task_result.get("candidates") or [])[:budget]
    if not candidates or not task_result.get("sequence") or not task_result.get("alphabet"):
        return empty_row(task, budget=budget, status="no_candidates")
    blast_started = time.perf_counter()
    blast_result = run_candidate_blast(
        query_sequence=str(task_result["sequence"]),
        sequence_alphabet=str(task_result["alphabet"]),
        candidates=candidates,
        protein_db=protein_db,
        nucleotide_db=nucleotide_db,
        max_targets=blast_max_targets,
    )
    blast_latency_ms = (time.perf_counter() - blast_started) * 1000
    reranked = rerank_candidates(
        candidates,
        list(blast_result.get("hits") or []),
        sequence_alphabet=str(task_result["alphabet"]),
        final_limit=final_limit,
        append_unaligned=append_unaligned,
    )
    rank = first_match_rank(reranked, task.expected)
    bio_evaluable = has_biological_expected(task.expected)
    bio_rank = first_biological_match_rank(reranked, task.expected) if bio_evaluable else None
    candidate_rank = first_match_rank([candidate["evidence"] for candidate in candidates], task.expected)
    candidate_bio_rank = (
        first_biological_match_rank([candidate["evidence"] for candidate in candidates], task.expected)
        if bio_evaluable
        else None
    )
    return {
        "task_id": task.task_id,
        "category": task.category,
        "query_type": task.query_type,
        "budget": int(budget),
        "status": "ok" if blast_result.get("status") == "ok" else str(blast_result.get("status") or "unknown"),
        "candidate_count": len(candidates),
        "candidate_rank": candidate_rank,
        "candidate_hit_at_10": bool(candidate_rank is not None and candidate_rank <= 10),
        "candidate_hit_at_n": bool(candidate_rank is not None),
        "candidate_bio_rank": candidate_bio_rank,
        "candidate_bio_hit_at_10": bool(candidate_bio_rank is not None and candidate_bio_rank <= 10),
        "candidate_bio_hit_at_n": bool(candidate_bio_rank is not None),
        "blast_hit_count": len(blast_result.get("hits") or []),
        "rank": rank,
        "hit_at_1": bool(rank is not None and rank <= 1),
        "hit_at_5": bool(rank is not None and rank <= 5),
        "hit_at_10": bool(rank is not None and rank <= 10),
        "mrr": round(1.0 / rank, 6) if rank else 0.0,
        "bio_evaluable": bio_evaluable,
        "bio_rank": bio_rank,
        "bio_hit_at_1": bool(bio_rank is not None and bio_rank <= 1),
        "bio_hit_at_5": bool(bio_rank is not None and bio_rank <= 5),
        "bio_hit_at_10": bool(bio_rank is not None and bio_rank <= 10),
        "bio_mrr": round(1.0 / bio_rank, 6) if bio_rank else 0.0,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "candidate_blast_latency_ms": round(blast_latency_ms, 3),
        "vector_latency_ms": float(task_result.get("vector_row", {}).get("vector_latency_ms") or 0.0),
        "blast_status": blast_result.get("status"),
        "top_accessions": [candidate["accession"] for candidate in candidates[:10]],
        "top_evidence": [
            {
                "entity_id": item.get("entity_id"),
                "source_id": item.get("source_id"),
                "score": item.get("score"),
                "candidate_blast_status": (item.get("metadata") or {}).get("candidate_blast_status"),
            }
            for item in reranked[:10]
        ],
    }


def empty_row(task: Any, *, budget: int, status: str) -> dict[str, Any]:
    bio_evaluable = has_biological_expected(task.expected)
    return {
        "task_id": task.task_id,
        "category": task.category,
        "query_type": task.query_type,
        "budget": int(budget),
        "status": status,
        "candidate_count": 0,
        "candidate_rank": None,
        "candidate_hit_at_10": False,
        "candidate_hit_at_n": False,
        "candidate_bio_rank": None,
        "candidate_bio_hit_at_10": False,
        "candidate_bio_hit_at_n": False,
        "blast_hit_count": 0,
        "rank": None,
        "hit_at_1": False,
        "hit_at_5": False,
        "hit_at_10": False,
        "mrr": 0.0,
        "bio_evaluable": bio_evaluable,
        "bio_rank": None,
        "bio_hit_at_1": False,
        "bio_hit_at_5": False,
        "bio_hit_at_10": False,
        "bio_mrr": 0.0,
        "latency_ms": 0.0,
        "candidate_blast_latency_ms": 0.0,
        "vector_latency_ms": 0.0,
    }


def summarize_by_budget(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["budget"])].append(row)
    return {str(budget): summarize_rows(grouped[budget]) for budget in sorted(grouped)}


def summarize_category_by_budget(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[str(row.get("category") or "unknown")][int(row["budget"])].append(row)
    return {
        category: {str(budget): summarize_rows(values[budget]) for budget in sorted(values)}
        for category, values in sorted(grouped.items())
    }


def summarize_query_type_by_budget(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[str(row.get("query_type") or "unknown")][int(row["budget"])].append(row)
    return {
        query_type: {str(budget): summarize_rows(values[budget]) for budget in sorted(values)}
        for query_type, values in sorted(grouped.items())
    }


def summarize_vector_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"tasks": 0}
    return {
        "tasks": len(rows),
        "ok_tasks": sum(1 for row in rows if row.get("status") == "ok"),
        "avg_candidate_count": round(sum(float(row.get("candidate_count") or 0.0) for row in rows) / len(rows), 4),
        "avg_vector_latency_ms": round(sum(float(row.get("vector_latency_ms") or 0.0) for row in rows) / len(rows), 3),
        "min_candidate_count": min(int(row.get("candidate_count") or 0) for row in rows),
        "max_candidate_count": max(int(row.get("candidate_count") or 0) for row in rows),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Vector Candidate Budget Sweep",
        "",
        result["mode_note"],
        "",
        "## Overall",
        "",
        "| Budget | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Candidate BLAST ms |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for budget, row in sorted(result["summary_by_budget"].items(), key=lambda item: int(item[0])):
        lines.append(
            f"| {budget} | {row.get('hit_at_10', 0):.4f} | {row.get('mrr', 0):.4f} | "
            f"{row.get('bio_hit_at_10', 0):.4f} | {row.get('bio_mrr', 0):.4f} | "
            f"{row.get('candidate_bio_hit_at_n', 0):.4f} | {row.get('avg_candidate_blast_latency_ms', 0):.3f} |"
        )
    lines.extend(["", "## By Modality", ""])
    for category, budgets in result["category_summary_by_budget"].items():
        lines.extend(
            [
                f"### {category}",
                "",
                "| Budget | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Candidate BLAST ms |",
                "|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for budget, row in sorted(budgets.items(), key=lambda item: int(item[0])):
            lines.append(
                f"| {budget} | {row.get('hit_at_10', 0):.4f} | {row.get('mrr', 0):.4f} | "
                f"{row.get('bio_hit_at_10', 0):.4f} | {row.get('bio_mrr', 0):.4f} | "
                f"{row.get('candidate_bio_hit_at_n', 0):.4f} | {row.get('avg_candidate_blast_latency_ms', 0):.3f} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "- Candidate Bio Recall@N shows whether expanding vector candidates increases the chance that BLAST can verify a biologically equivalent sequence.",
            "- Because this is a prefix sweep from one max-budget vector search, vector lookup latency should be interpreted from `vector_search_summary`, not from each budget row.",
            "- If recall plateaus, the next fix should be graph-expanded candidates or better vector ranking rather than simply increasing BLAST candidate count.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep vector candidate budgets for candidate-subset BLAST reranking")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--benchmark", default="benchmarks/sequence_search_100_seed20260516_bio.jsonl")
    parser.add_argument("--output", default="reports/vector_candidate_budget_sweep_eval.json")
    parser.add_argument("--markdown", default="reports/vector_candidate_budget_sweep_summary.md")
    parser.add_argument("--budgets", default="10,25,50,100,200")
    parser.add_argument("--categories", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--final-limit", type=int, default=10)
    parser.add_argument("--blast-top-k", type=int, default=10)
    parser.add_argument("--append-unaligned", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

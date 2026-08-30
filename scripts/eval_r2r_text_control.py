#!/usr/bin/env python3
"""Evaluate a live R2R collection as the generic text-RAG sequence control."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.integrations.r2r import build_r2r_text_control_pack, search_r2r_text_control


def main() -> None:
    args = parse_args()
    try:
        from r2r import R2RClient
    except ImportError as exc:
        raise SystemExit("Install the optional R2R SDK with `pip install 'r2r>=3.6,<4'`.") from exc
    client = R2RClient(base_url=args.base_url)
    queries = read_jsonl(Path(args.queries))
    if args.test_ids:
        test_ids = {
            line.strip()
            for line in Path(args.test_ids).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        queries = [query for query in queries if str(query["id"]) in test_ids]
    if args.query_limit:
        queries = queries[: args.query_limit]
    details = []
    packs = []
    latencies = []
    for index, query in enumerate(queries, start=1):
        started = time.perf_counter()
        chunks = search_r2r_text_control(
            client,
            str(query["query"]),
            collection_id=args.collection_id,
            limit=args.top_k,
        )
        latency_ms = 1000.0 * (time.perf_counter() - started)
        latencies.append(latency_ms)
        route = build_r2r_text_control_pack(query, chunks)
        route["retrieval"]["api_latency_ms"] = latency_ms
        packs.append(route)
        accessions = [str(item["accession"]) for item in route["pack"]["candidates"]]
        pmids = [str(item) for item in route["pack"]["papers"]]
        details.append(
            {
                "query_id": str(query["id"]),
                "method": "r2r_text_only",
                "top_accessions": accessions,
                "top_pmids": pmids,
                "latency_ms": latency_ms,
                "chunks": chunks if args.keep_chunks else [],
            }
        )
        print(json.dumps({"query": index, "total": len(queries), "latency_ms": round(latency_ms, 3)}), flush=True)
    result = {
        "dataset": "BioRAG SeqLit held-out R2R text-only control",
        "claim_scope": (
            "This is the generic R2R semantic text route over an explicitly frozen collection. "
            "It is a deployment control, not a biological sequence embedding baseline."
        ),
        "r2r_base_url": args.base_url,
        "collection_id": args.collection_id,
        "embedding_label": args.embedding_label,
        "test_ids": args.test_ids,
        "query_count": len(details),
        "top_k": args.top_k,
        "latency": {
            "mean_ms": statistics.mean(latencies) if latencies else 0.0,
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
        },
        "retrieval_summary": summarize_retrieval(packs),
        "agent_packs": str(args.packs_output),
        "details": details,
    }
    packs_output = Path(args.packs_output)
    packs_output.parent.mkdir(parents=True, exist_ok=True)
    packs_output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in packs),
        encoding="utf-8",
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "latency": result["latency"]}, indent=2))


def summarize_retrieval(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = (
        "candidate_hit",
        "candidate_recall",
        "function_prompt_gold_recall",
        "literature_prompt_gold_recall",
    )
    return {
        key: statistics.mean(float(row["retrieval"][key]) for row in rows) if rows else 0.0
        for key in keys
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the live R2R text-only application control")
    parser.add_argument("--base-url", default="http://localhost:7272")
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--embedding-label", required=True)
    parser.add_argument("--queries", default="data/seq_lit_dag_function_heldout_2k/queries.jsonl")
    parser.add_argument(
        "--test-ids",
        default="reports/results/agent_graph_selector_fused_full_p20_test_ids.txt",
    )
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--query-limit", type=int, default=0)
    parser.add_argument("--keep-chunks", action="store_true")
    parser.add_argument("--output", default="reports/results/r2r_text_control.json")
    parser.add_argument(
        "--packs-output",
        default="reports/results/agent_application_ablation/r2r_text_only.jsonl",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()

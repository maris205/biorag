#!/usr/bin/env python3
"""Freeze the outcome-independent sample and metadata request for expert review."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.agent_review import evidence_pmids, query_stratum, select_review_queries


ROUTE_FILES = {
    "no_retrieval": "no_retrieval.jsonl",
    "r2r_text_only": "r2r_text_only.jsonl",
    "sequence_vector": "sequence_vector.jsonl",
    "combined_blast_vector": "combined_blast_vector.jsonl",
    "combined_blast_vector_dag": "combined_blast_vector_dag.jsonl",
}


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    eligible_ids = [line.strip() for line in Path(args.test_ids).read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = select_review_queries(
        queries,
        eligible_ids,
        per_stratum=args.per_stratum,
        seed=args.seed,
    )
    selected_ids = {row["query_id"] for row in selected}
    selected_path = output / "selected_query_ids.txt"
    selected_path.write_text("\n".join(row["query_id"] for row in selected) + "\n", encoding="utf-8")

    route_root = Path(args.route_root)
    route_counts: dict[str, int] = {}
    pmids = {
        str(pmid)
        for row in selected
        for pmid in queries[row["query_id"]].get("expected_pmids", [])
    }
    for route, filename in ROUTE_FILES.items():
        rows = [row for row in read_jsonl(route_root / filename) if str(row["pack"]["query_id"]) in selected_ids]
        route_counts[route] = len(rows)
        mode = "graph_idf" if route.endswith("_dag") else "raw"
        for row in rows:
            pmids.update(evidence_pmids(row["pack"], evidence_mode=mode))
    expected_count = len(selected)
    incomplete = {route: count for route, count in route_counts.items() if count != expected_count}
    if incomplete:
        raise ValueError(f"Incomplete route packs: {incomplete}; expected {expected_count}")

    metadata_request = output / "metadata_pmids.jsonl"
    metadata_request.write_text(
        json.dumps({"id": "agent-expert-review", "labels": {"pmids": sorted(pmids, key=int)}}) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "dataset": "BioRAG SeqLit free-form expert review pilot",
        "status": "protocol_frozen_before_freeform_generation",
        "seed": args.seed,
        "selection_rule": (
            "Deterministic random sample from the frozen 66-query test split, with equal allocation to "
            "single-GO sparse-literature, single-GO dense-literature, and multi-GO strata. Retrieval outcomes "
            "and generated answers are not used for selection."
        ),
        "per_stratum": args.per_stratum,
        "query_count": len(selected),
        "strata": {
            stratum: sum(1 for row in selected if row["stratum"] == stratum)
            for stratum in sorted({row["stratum"] for row in selected})
        },
        "eligible_query_count": len(eligible_ids),
        "eligible_strata": {
            stratum: sum(1 for query_id in eligible_ids if query_stratum(queries[query_id]) == stratum)
            for stratum in sorted({query_stratum(queries[query_id]) for query_id in eligible_ids})
        },
        "routes": route_counts,
        "selected_queries": selected,
        "metadata_pmid_count": len(pmids),
        "claim_boundary": (
            "This package enables a blinded human evaluation. It is not an expert-evaluation result until "
            "independent domain reviewers complete the frozen form and the route key is decoded."
        ),
    }
    manifest_path = output / "selection_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "queries": len(selected), "pmids": len(pmids)}, indent=2))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the SeqLit free-form expert review sample")
    parser.add_argument("--queries", default="data/seq_lit_dag_function_heldout_2k/queries.jsonl")
    parser.add_argument("--test-ids", default="reports/results/agent_graph_selector_fused_full_p20_test_ids.txt")
    parser.add_argument("--route-root", default="reports/results/agent_application_ablation")
    parser.add_argument("--output", default="reports/results/agent_expert_review")
    parser.add_argument("--per-stratum", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260831)
    return parser.parse_args()


if __name__ == "__main__":
    main()

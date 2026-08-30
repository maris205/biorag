#!/usr/bin/env python3
"""Freeze evidence packs for the downstream SeqLit Agent route ablation."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    test_ids = load_ids(Path(args.test_ids))
    dag_rows = read_jsonl(Path(args.dag_packs))
    selector_config = next(
        (
            dict(row["pack"]["selector_config"])
            for row in dag_rows
            if row.get("pack", {}).get("selector_config")
        ),
        {},
    )
    routes = [
        export_route(
            name="no_retrieval",
            source=Path(args.dag_packs),
            output=output / "no_retrieval.jsonl",
            test_ids=test_ids,
            evidence_mode="raw",
            clear_evidence=True,
            selector_config=selector_config,
        ),
        export_route(
            name="sequence_vector",
            source=Path(args.vector_packs),
            output=output / "sequence_vector.jsonl",
            test_ids=test_ids,
            evidence_mode="raw",
            selector_config=selector_config,
        ),
        export_route(
            name="combined_blast_vector",
            source=Path(args.combined_packs),
            output=output / "combined_blast_vector.jsonl",
            test_ids=test_ids,
            evidence_mode="raw",
            selector_config=selector_config,
        ),
        export_route(
            name="combined_blast_vector_dag",
            source=Path(args.dag_packs),
            output=output / "combined_blast_vector_dag.jsonl",
            test_ids=test_ids,
            evidence_mode="graph_idf",
        ),
    ]
    manifest = {
        "dataset": "BioRAG SeqLit downstream Agent application ablation",
        "split": "frozen 66-query test partition",
        "test_ids": str(args.test_ids),
        "generator_control": "Use one fixed instruction model and decoding configuration for every route.",
        "routes": routes,
        "pending_external_route": {
            "name": "r2r_text_only",
            "status": "requires live R2R endpoint and frozen collection snapshot",
            "claim_boundary": "Do not substitute a local proxy result and label it as R2R.",
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "routes": routes}, indent=2))


def export_route(
    *,
    name: str,
    source: Path,
    output: Path,
    test_ids: set[str],
    evidence_mode: str,
    clear_evidence: bool = False,
    selector_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = []
    for row in read_jsonl(source):
        pack = dict(row["pack"])
        query_id = str(pack["query_id"])
        if query_id not in test_ids:
            continue
        if selector_config:
            pack["selector_config"] = copy.deepcopy(selector_config)
        if clear_evidence:
            pack.update(
                {
                    "candidates": [],
                    "papers": [],
                    "go_claims": [],
                    "paper_claims": [],
                    "graph_paths": [],
                }
            )
        selected.append({**row, "pack": pack, "application_route": name})
    selected.sort(key=lambda row: str(row["pack"]["query_id"]))
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    return {
        "name": name,
        "packs": str(output),
        "source": str(source),
        "query_count": len(selected),
        "evidence_mode": evidence_mode,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_ids(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def parse_args() -> argparse.Namespace:
    root = "reports/results"
    parser = argparse.ArgumentParser(description="Freeze Agent evidence-route ablation packs")
    parser.add_argument("--vector-packs", default=f"{root}/agent_qa_prott5_full_p20_packs.jsonl")
    parser.add_argument("--combined-packs", default=f"{root}/agent_qa_fused_full_p20_packs.jsonl")
    parser.add_argument("--dag-packs", default=f"{root}/agent_graph_selector_fused_full_p20_packs.jsonl")
    parser.add_argument("--test-ids", default=f"{root}/agent_graph_selector_fused_full_p20_test_ids.txt")
    parser.add_argument("--output", default=f"{root}/agent_application_ablation")
    return parser.parse_args()


if __name__ == "__main__":
    main()

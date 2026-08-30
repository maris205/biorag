#!/usr/bin/env python3
"""Summarize SeqLit-DAG embedding-model path results into a paper-ready table."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    args = parse_args()
    rows = [load_result(Path(path)) for path in args.inputs]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(rows), encoding="utf-8")
    print(json.dumps({"models": len(rows), "output": str(output)}, indent=2))


def load_result(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    summary = result["summary"]
    timing = result["timing"]
    gpu = result["gpu"]
    return {
        "name": result["name"],
        "protein_hit_at_1": summary["protein_hit_at_1"],
        "protein_hit_at_10": summary["protein_hit_at_10"],
        "protein_mrr": summary["protein_mrr"],
        "paper_recall": summary["paper_recall"],
        "path_complete": summary["path_complete"],
        "embedding_ms": timing["query_embedding_ms_per_query"],
        "lookup_ms": timing["lookup_ms_per_query"],
        "end_to_end_ms": timing["end_to_end_ms_per_query"],
        "peak_gib": gpu["peak_memory_gib"],
    }


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# SeqLit-DAG Protein Embedding Comparison",
        "",
        "The 50 queries are sequence windows from indexed parent proteins. This table evaluates model integration and evidence-path behavior, not held-out homology competitiveness.",
        "",
        "| Model | Protein Hit@1 | Protein Hit@10 | Protein MRR | Paper Recall@50 | Complete path | Embed ms/query | Lookup ms/query | E2E ms/query | Peak GiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {"prott5_mean": "ProtT5-XL mean", "esm2_mean": "ESM-2 650M mean", "omnigene_mean": "OmniGene-4-CPT BF16 mean"}
    for row in sorted(rows, key=lambda item: -item["protein_mrr"]):
        lines.append(
            f"| {labels.get(row['name'], row['name'])} | {row['protein_hit_at_1']:.3f} | "
            f"{row['protein_hit_at_10']:.3f} | {row['protein_mrr']:.3f} | {row['paper_recall']:.3f} | "
            f"{row['path_complete']:.3f} | {row['embedding_ms']:.2f} | {row['lookup_ms']:.3f} | "
            f"{row['end_to_end_ms']:.2f} | {row['peak_gib']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "1. Window indexing with parent collapse is necessary: a full-protein mean-pooling sanity condition was weak, whereas 128-aa windows with stride 64 recover the parent reliably.",
            "2. ProtT5 is the strongest protein-only entry model in this sample, reaching perfect parent rank and paper-path recovery while using less than 3 GiB peak allocated memory.",
            "3. ESM-2 is nearly as strong and slightly faster end to end. It provides a practical public baseline and deployment option.",
            "4. OmniGene remains viable as the unified biological-language backbone, but it is slower and less accurate than specialized protein encoders on this protein-only route.",
            "5. Paper recall can exceed exact parent recovery because several candidate proteins share curated GOA-supported PMIDs. This is a graph property to analyze, not an excuse to relax protein retrieval metrics.",
            "",
            "## Next Experiments",
            "",
            "- Build a held-out parent/family split where query proteins are absent from the index and paper relevance is derived independently from the retrieval model.",
            "- Report paper Recall@10/20/50, nDCG, and parent-collapsed controls against random, k-mer-NN, and BLAST candidate graphs.",
            "- Scale ProtT5 and ESM-2 indexes to the curated Swiss-Prot literature subset, then full Swiss-Prot, while retaining the same PMID ground truth.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize SeqLit-DAG embedding results")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", default="reports/seq_lit_embedding_comparison.md")
    return parser.parse_args()


if __name__ == "__main__":
    main()

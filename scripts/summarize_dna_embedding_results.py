#!/usr/bin/env python3
"""Summarize comparable DNA embedding matrix JSON files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    args = parse_args()
    rows = [load_row(Path(path)) for path in args.inputs]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(rows), encoding="utf-8")
    print(json.dumps({"results": len(rows), "output": str(output)}, indent=2))


def load_row(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    summary = dict(result.get("summary") or {})
    timing = dict(result.get("timing") or {})
    gpu = dict(result.get("gpu") or {})
    details = list(result.get("details") or [])
    return {
        "name": result.get("name") or path.stem,
        "backend": result.get("backend", "unknown"),
        "model": display_model(result.get("model", "unknown")),
        "pooling": result.get("pooling", "unknown"),
        "orientation": result.get("orientation", "none"),
        "window": f"{result.get('window_size', '?')}/{result.get('window_stride', '?')}",
        "queries": result.get("query_count", 0),
        "bio_hit_at_1": float(summary.get("bio_hit_at_1", 0.0)),
        "bio_hit_at_5": float(summary.get("bio_hit_at_5", 0.0)),
        "bio_hit_at_10": float(summary.get("bio_hit_at_10", 0.0)),
        "bio_mrr": float(summary.get("bio_mrr", 0.0)),
        "exact_hit_at_10": float(summary.get("exact_hit_at_10", 0.0)),
        "query_embedding_ms": float(timing.get("query_embedding_ms_per_query", 0.0)),
        "lookup_ms": float(timing.get("lookup_ms_per_query", 0.0)),
        "e2e_ms": float(timing.get("end_to_end_ms_per_query", 0.0)),
        "peak_gib": float(gpu.get("peak_memory_gib", 0.0)),
        "by_query_type": query_type_summary(details),
    }


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# DNA Embedding Matrix",
        "",
        "All rows use the same held-out-parent DNA/cDNA benchmark and controlled20k index. Biological metrics use shared gene labels; BLASTN remains the alignment reference.",
        "",
        "| Model | Pooling | Strand | Window | N | Bio Hit@1 | Bio Hit@5 | Bio Hit@10 | Bio MRR | Exact Hit@10 | Embed ms/q | Lookup ms/q | E2E ms/q | Peak GiB |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda item: (-item["bio_mrr"], item["model"], item["pooling"])):
        model = str(row["model"]).replace("|", "/")
        lines.append(
            f"| {model} | {row['pooling']} | {row['orientation']} | {row['window']} | {row['queries']} | "
            f"{row['bio_hit_at_1']:.4f} | {row['bio_hit_at_5']:.4f} | {row['bio_hit_at_10']:.4f} | "
            f"{row['bio_mrr']:.4f} | {row['exact_hit_at_10']:.4f} | {row['query_embedding_ms']:.1f} | "
            f"{row['lookup_ms']:.2f} | {row['e2e_ms']:.1f} | {row['peak_gib']:.2f} |"
        )
    query_types = sorted({query_type for row in rows for query_type in row["by_query_type"]})
    if query_types:
        lines.extend(
            [
                "",
                "## Biological Hit@10 by Query Type",
                "",
                "| Model / setting | " + " | ".join(query_types) + " |",
                "|---|" + "---:|" * len(query_types),
            ]
        )
        for row in sorted(rows, key=lambda item: (-item["bio_mrr"], item["model"], item["pooling"])):
            label = f"{row['model']} / {row['pooling']} / {row['orientation']} / {row['window']}"
            values = [f"{row['by_query_type'].get(query_type, {}).get('bio_hit_at_10', 0.0):.4f}" for query_type in query_types]
            lines.append("| " + label.replace("|", "/") + " | " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "## Reading the Matrix",
            "",
            "- Select the primary DNA encoder by held-out biological MRR/Hit@10, then check stability by query type in the source JSON details.",
            "- Treat reverse-complement averaging as a strand-invariance engineering ablation, not as a new biological learning method.",
            "- Do not compare lookup-only latency with end-to-end latency; the latter includes query embedding.",
            "- Only scale a condition to 100k/full indexes after it improves or clarifies the controlled20k result.",
            "",
        ]
    )
    return "\n".join(lines)


def display_model(model: Any) -> str:
    """Use stable paper-facing labels instead of machine-local checkpoint paths."""
    value = str(model or "unknown")
    lowered = value.lower()
    if "dnabert-2" in lowered or "dnabert_hyphen_2" in lowered:
        return "DNABERT-2 117M"
    if "dnabert-s" in lowered or "dnabert_s" in lowered:
        return "DNABERT-S"
    if "omnigene-4-cpt" in lowered:
        return "OmniGene-4-CPT 4-bit"
    if "nucleotide-transformer" in lowered:
        return "Nucleotide Transformer v2 500M"
    if "caduceus-ps" in lowered:
        return "Caduceus-PS"
    if "caduceus-ph" in lowered:
        return "Caduceus-Ph"
    if "hyenadna" in lowered:
        return "HyenaDNA-small"
    if "moderngena" in lowered:
        return "modernGENA-base"
    if "gena-lm" in lowered or "gena_lm" in lowered:
        return "GENA-LM-base"
    return value.rsplit("/", 1)[-1]


def query_type_summary(details: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for detail in details:
        grouped.setdefault(str(detail.get("query_type") or "unknown"), []).append(detail)
    return {
        query_type: {
            "count": float(len(items)),
            "bio_hit_at_10": sum(bool(item.get("bio_hit_at_10")) for item in items) / len(items),
            "bio_mrr": sum(float(item.get("bio_mrr") or 0.0) for item in items) / len(items),
        }
        for query_type, items in sorted(grouped.items())
        if items
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize DNA embedding matrix results")
    parser.add_argument("inputs", nargs="+", help="DNA embedding result JSON files")
    parser.add_argument("--output", default="reports/dna_embedding_matrix.md")
    return parser.parse_args()


if __name__ == "__main__":
    main()

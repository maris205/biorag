#!/usr/bin/env python3
"""Summarize held-out embedding baseline evaluation JSON files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize embedding baseline eval results")
    parser.add_argument("results", nargs="+", help="Evaluation JSON files")
    parser.add_argument("--output", default="reports/embedding_baseline_comparison.md")
    args = parser.parse_args()

    rows = [_row(Path(path)) for path in args.results]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown(rows), encoding="utf-8")
    print(output)


def _row(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    details = list(data.get("details") or [])
    condition = _condition_key(data, path)
    condition_rows = [row for row in details if row.get("condition") == condition]
    summary = dict((data.get("summary") or {}).get(condition) or {})
    ranks = [int(row["bio_rank"]) for row in condition_rows if row.get("bio_rank")]
    manifest = _manifest_from_eval(data, path)
    manifest = {**_manifest_from_filename(path), **manifest}
    return {
        "file": path,
        "model": _display_model(manifest.get("model") or path.stem),
        "backend": manifest.get("backend") or "unknown",
        "pooling": manifest.get("pooling") or "unknown",
        "tasks": int(summary.get("tasks") or len(condition_rows)),
        "bio_hit_at_10": float(summary.get("bio_hit_at_10") or 0.0),
        "bio_mrr": float(summary.get("bio_mrr") or 0.0),
        "recall_at_50": _recall_at(ranks, 50, len(condition_rows)),
        "recall_at_100": _recall_at(ranks, 100, len(condition_rows)),
        "recall_at_200": _recall_at(ranks, 200, len(condition_rows)),
        "avg_latency_ms": float(summary.get("avg_latency_ms") or 0.0),
    }


def _condition_key(data: dict[str, Any], path: Path) -> str:
    summary = data.get("summary") or {}
    if "vector" in summary:
        return "vector"
    if "blast" in summary:
        return "blast"
    conditions = data.get("conditions") or {}
    for key in ("vector", "blast"):
        if key in conditions:
            return key
    if "blast" in path.stem:
        return "blast"
    return "vector"


def _manifest_from_eval(data: dict[str, Any], path: Path) -> dict[str, Any]:
    for row in data.get("details") or []:
        for evidence in row.get("top_evidence") or []:
            if evidence.get("route") == "vector":
                break
        for trace in row.get("retrieval_trace") or []:
            if trace.get("route") == "vector":
                return dict(trace.get("metadata") or {})
    manifest_path = path.parent / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}


def _manifest_from_filename(path: Path) -> dict[str, str]:
    stem = path.stem.lower()
    if "blast" in stem:
        return {"model": "BLAST local alignment", "backend": "blast", "pooling": "alignment"}
    if "prott5" in stem:
        return {
            "model": "ProtT5-XL-UniRef50",
            "backend": "prott5",
            "pooling": "last" if "_last_" in stem else "mean",
        }
    if "esm2" in stem:
        return {
            "model": "ESM-2 650M",
            "backend": "esm",
            "pooling": "last" if "_last_" in stem else "mean",
        }
    if "omnigene" in stem:
        return {
            "model": "OmniGene-4-CPT BF16",
            "backend": "omnigene",
            "pooling": "last" if "_last_" in stem else "mean",
        }
    return {}


def _display_model(model: Any) -> str:
    raw = str(model or "")
    lowered = raw.lower()
    if "prot_t5_xl_uniref50" in lowered or "prott5-xl" in lowered:
        return "ProtT5-XL-UniRef50"
    if "esm2_t33_650m" in lowered or "esm-2 650m" in lowered:
        return "ESM-2 650M"
    if "omnigene-4-cpt" in lowered:
        return "OmniGene-4-CPT BF16"
    return raw


def _recall_at(ranks: list[int], k: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(sum(1 for rank in ranks if rank <= k) / total, 4)


def _markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Protein Embedding Baseline Comparison",
        "",
        "Held-out parent-fragment retrieval on the controlled20k protein index. BLAST is the alignment reference; vector rows use sequence-window Chroma retrieval with top-200 candidate pools. The exact held-out parent accessions are excluded from the index, so the main metric is biological match based on shared gene/family labels rather than exact parent ID.",
        "",
        "| Method | Backend | Pooling | Tasks | Bio Hit@10 | Bio MRR | Recall@50 | Recall@100 | Recall@200 | Avg latency ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        model = str(row["model"]).replace("|", "/")
        lines.append(
            f"| {model} | {row['backend']} | {row['pooling']} | {row['tasks']} | "
            f"{row['bio_hit_at_10']:.4f} | {row['bio_mrr']:.4f} | "
            f"{row['recall_at_50']:.4f} | {row['recall_at_100']:.4f} | {row['recall_at_200']:.4f} | "
            f"{row['avg_latency_ms']:.1f} |"
        )
    lines.extend(
        [
            "",
            "Current interpretation:",
            "- ProtT5 mean pooling is the strongest completed dense protein baseline and narrows the gap to BLAST, but BLAST remains stronger for alignment-grounded verification.",
            "- Mean pooling is consistently stronger than last-token pooling for OmniGene, ESM-2, and ProtT5 on this fragment task.",
            "- OmniGene-4-CPT is useful as a unified sequence/text representation layer for BioRAG agents, but current protein-only retrieval results do not support treating it as the strongest protein embedding model.",
            "- This supports a model-agnostic BioRAG framing: use specialized encoders for sequence partitions when they are stronger, and use OmniGene as an integrated biological-language backbone where unified agent behavior matters.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()

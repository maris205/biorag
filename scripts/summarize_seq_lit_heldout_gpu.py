#!/usr/bin/env python3
"""Create a bootstrap comparison of held-out sequence-to-paper methods."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


METRICS = ("candidate_hit_at_10", "candidate_mrr", "paper_hit", "paper_recall", "path_complete")


def main() -> None:
    args = parse_args()
    methods = {
        "BLAST": load_cpu(Path(args.cpu), "blast"),
        "k-mer": load_cpu(Path(args.cpu), "kmer_jaccard"),
        "Random": load_cpu(Path(args.cpu), "random"),
        "ProtT5": load_vector(Path(args.prott5)),
        "ESM-2": load_vector(Path(args.esm2)),
        "ProtT5+BLAST RRF": load_fusion(Path(args.fusion)),
    }
    analysis = {
        "query_count": len(next(iter(methods.values()))),
        "protein_k": args.protein_k,
        "paper_k": args.paper_k,
        "bootstrap_samples": args.bootstrap_samples,
        "methods": {
            name: bootstrap(rows, samples=args.bootstrap_samples, seed=args.seed)
            for name, rows in methods.items()
        },
        "paired_deltas": {
            "ProtT5_minus_BLAST": paired(methods["ProtT5"], methods["BLAST"], args.bootstrap_samples, args.seed),
            "ProtT5_minus_ESM2": paired(methods["ProtT5"], methods["ESM-2"], args.bootstrap_samples, args.seed),
            "ProtT5_minus_kmer": paired(methods["ProtT5"], methods["k-mer"], args.bootstrap_samples, args.seed),
            "RRF_minus_ProtT5": paired(methods["ProtT5+BLAST RRF"], methods["ProtT5"], args.bootstrap_samples, args.seed),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(render(analysis), encoding="utf-8")
    print(json.dumps({"output": str(output), "query_count": analysis["query_count"]}, indent=2))


def load_cpu(path: Path, method: str) -> list[dict[str, Any]]:
    result = json.loads(path.read_text(encoding="utf-8"))
    return normalize([row for row in result["details"] if row["method"] == method], vector=False)


def load_vector(path: Path) -> list[dict[str, Any]]:
    return normalize(json.loads(path.read_text(encoding="utf-8"))["details"], vector=True)


def load_fusion(path: Path) -> list[dict[str, Any]]:
    return normalize(json.loads(path.read_text(encoding="utf-8"))["details"], vector=False)


def normalize(rows: list[dict[str, Any]], *, vector: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "query_id": str(row["query_id"]),
                "candidate_hit_at_10": float(row["protein_hit_at_10"] if vector else row["candidate_hit_at_10"]),
                "candidate_mrr": float(row["protein_mrr"] if vector else row["candidate_mrr"]),
                "paper_hit": float(row["paper_hit"]),
                "paper_recall": float(row["paper_recall"]),
                "path_complete": float(row["path_complete"]),
            }
        )
    return sorted(result, key=lambda row: row["query_id"])


def bootstrap(rows: list[dict[str, Any]], *, samples: int, seed: int) -> dict[str, Any]:
    matrix = np.asarray([[row[key] for key in METRICS] for row in rows])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(rows), size=(samples, len(rows)))
    means = matrix[draws].mean(axis=1)
    return {key: interval(float(matrix[:, index].mean()), means[:, index]) for index, key in enumerate(METRICS)}


def paired(left: list[dict[str, Any]], right: list[dict[str, Any]], samples: int, seed: int) -> dict[str, Any]:
    left_map = {row["query_id"]: row for row in left}
    right_map = {row["query_id"]: row for row in right}
    query_ids = sorted(set(left_map) & set(right_map))
    differences = np.asarray(
        [[left_map[q][key] - right_map[q][key] for key in METRICS] for q in query_ids]
    )
    rng = np.random.default_rng(seed + 1)
    draws = rng.integers(0, len(query_ids), size=(samples, len(query_ids)))
    means = differences[draws].mean(axis=1)
    return {
        key: {**interval(float(differences[:, index].mean()), means[:, index]), "probability_gt_zero": float(np.mean(means[:, index] > 0))}
        for index, key in enumerate(METRICS)
    }


def interval(point: float, values: np.ndarray) -> dict[str, float]:
    return {"mean": point, "ci95_low": float(np.quantile(values, 0.025)), "ci95_high": float(np.quantile(values, 0.975))}


def render(analysis: dict[str, Any]) -> str:
    lines = [
        "# Held-Out SeqLit-DAG GPU Comparison",
        "",
        "Held-out parent proteins are absent from the index. Relevance uses low-frequency shared GO terms and index-side GOA paper evidence.",
        "",
        f"Queries: `{analysis['query_count']}`; protein K: `{analysis['protein_k']}`; paper K: `{analysis['paper_k']}`.",
        "",
        "| Method | Candidate Hit@10 | Candidate MRR | Paper Hit | Paper Recall | Complete Path |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in ("ProtT5", "ESM-2", "BLAST", "k-mer", "Random", "ProtT5+BLAST RRF"):
        row = analysis["methods"][method]
        lines.append(f"| {method} | " + " | ".join(fmt(row[key]) for key in METRICS) + " |")
    lines.extend(["", "## Paired Deltas", "", "| Contrast | Candidate MRR | Paper Hit | Paper Recall |", "|---|---:|---:|---:|"])
    for key, label in (
        ("ProtT5_minus_BLAST", "ProtT5 - BLAST"),
        ("ProtT5_minus_ESM2", "ProtT5 - ESM-2"),
        ("ProtT5_minus_kmer", "ProtT5 - k-mer"),
        ("RRF_minus_ProtT5", "RRF - ProtT5"),
    ):
        row = analysis["paired_deltas"][key]
        lines.append(f"| {label} | {fmt(row['candidate_mrr'])} | {fmt(row['paper_hit'])} | {fmt(row['paper_recall'])} |")
    lines.extend(
        [
            "",
            "Intervals are query-level paired bootstrap 95% intervals. RRF is a heuristic engineering ablation, not a proposed methodological contribution.",
            "",
        ]
    )
    return "\n".join(lines)


def fmt(row: dict[str, float]) -> str:
    return f"{row['mean']:.3f} [{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize held-out SeqLit-DAG GPU results")
    parser.add_argument("--cpu", required=True)
    parser.add_argument("--prott5", required=True)
    parser.add_argument("--esm2", required=True)
    parser.add_argument("--fusion", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--protein-k", type=int, required=True)
    parser.add_argument("--paper-k", type=int, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260720)
    return parser.parse_args()


if __name__ == "__main__":
    main()

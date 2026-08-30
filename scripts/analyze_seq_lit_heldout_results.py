#!/usr/bin/env python3
"""Analyze held-out SeqLit-DAG CPU baselines with paired bootstrap intervals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


METRICS = ("candidate_hit_at_10", "candidate_mrr", "paper_hit", "paper_recall", "path_complete")


def main() -> None:
    args = parse_args()
    result = json.loads(Path(args.input).read_text(encoding="utf-8"))
    by_method = group_rows(result["details"])
    analysis = {
        "source": args.input,
        "query_count": result["query_count"],
        "bootstrap_samples": args.bootstrap_samples,
        "seed": args.seed,
        "methods": {
            method: bootstrap_metrics(rows, samples=args.bootstrap_samples, seed=args.seed)
            for method, rows in by_method.items()
        },
        "paired_deltas": {
            "blast_minus_kmer": paired_bootstrap(
                by_method["blast"], by_method["kmer_jaccard"], samples=args.bootstrap_samples, seed=args.seed
            ),
            "kmer_minus_random": paired_bootstrap(
                by_method["kmer_jaccard"], by_method["random"], samples=args.bootstrap_samples, seed=args.seed
            ),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    markdown = output.with_suffix(".md")
    markdown.write_text(render_markdown(result, analysis), encoding="utf-8")
    print(json.dumps({"output": str(output), "markdown": str(markdown), "query_count": result["query_count"]}, indent=2))


def group_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["method"]), []).append(row)
    for method in grouped:
        grouped[method].sort(key=lambda row: str(row["query_id"]))
    return grouped


def bootstrap_metrics(rows: list[dict[str, Any]], *, samples: int, seed: int) -> dict[str, Any]:
    matrix = np.asarray([[float(row[key]) for key in METRICS] for row in rows], dtype=np.float64)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(rows), size=(samples, len(rows)))
    means = matrix[draws].mean(axis=1)
    return {
        key: interval(float(matrix[:, index].mean()), means[:, index])
        for index, key in enumerate(METRICS)
    }


def paired_bootstrap(
    left: list[dict[str, Any]], right: list[dict[str, Any]], *, samples: int, seed: int
) -> dict[str, Any]:
    left_map = {str(row["query_id"]): row for row in left}
    right_map = {str(row["query_id"]): row for row in right}
    query_ids = sorted(set(left_map) & set(right_map))
    differences = np.asarray(
        [[float(left_map[q][key]) - float(right_map[q][key]) for key in METRICS] for q in query_ids],
        dtype=np.float64,
    )
    rng = np.random.default_rng(seed + 1)
    draws = rng.integers(0, len(query_ids), size=(samples, len(query_ids)))
    means = differences[draws].mean(axis=1)
    return {
        key: {
            **interval(float(differences[:, index].mean()), means[:, index]),
            "probability_gt_zero": float(np.mean(means[:, index] > 0)),
        }
        for index, key in enumerate(METRICS)
    }


def interval(point: float, bootstrap: np.ndarray) -> dict[str, float]:
    return {
        "mean": point,
        "ci95_low": float(np.quantile(bootstrap, 0.025)),
        "ci95_high": float(np.quantile(bootstrap, 0.975)),
    }


def render_markdown(result: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = [
        "# Held-Out Sequence-to-Function-to-Paper CPU Pilot",
        "",
        result["claim_scope"],
        "",
        f"Queries: `{result['query_count']}`; index proteins: `{result['index_protein_count']}`; protein K: `{result['protein_k']}`; paper K: `{result['paper_k']}`.",
        "",
        "| Method | Candidate Hit@10 | Candidate MRR | Paper Hit | Paper Recall | Complete Path |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {"blast": "BLAST", "kmer_jaccard": "k-mer Jaccard", "random": "Random"}
    for method in ("blast", "kmer_jaccard", "random"):
        metrics = analysis["methods"][method]
        values = [format_interval(metrics[key]) for key in METRICS]
        lines.append(f"| {labels[method]} | " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "## Paired Differences",
            "",
            "| Contrast | Candidate Hit@10 delta | Candidate MRR delta | Paper Hit delta | Paper Recall delta |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for key, label in (("blast_minus_kmer", "BLAST - k-mer"), ("kmer_minus_random", "k-mer - random")):
        delta = analysis["paired_deltas"][key]
        lines.append(
            f"| {label} | {format_interval(delta['candidate_hit_at_10'])} | "
            f"{format_interval(delta['candidate_mrr'])} | {format_interval(delta['paper_hit'])} | "
            f"{format_interval(delta['paper_recall'])} |"
        )
    lines.extend(
        [
            "",
            "Intervals are query-level nonparametric paired bootstrap 95% intervals. The pilot is not a family-cluster-held-out benchmark; GOA labels are curated but the 2k corpus is sampled from human GOA order.",
            "",
        ]
    )
    return "\n".join(lines)


def format_interval(row: dict[str, float]) -> str:
    return f"{row['mean']:.3f} [{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap held-out SeqLit-DAG results")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260720)
    return parser.parse_args()


if __name__ == "__main__":
    main()

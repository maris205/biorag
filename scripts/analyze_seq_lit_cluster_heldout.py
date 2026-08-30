#!/usr/bin/env python3
"""Combine cluster-held-out SeqLit retrieval routes with paired intervals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


METRICS = ("hit_at_10", "mrr", "paper_hit", "paper_recall", "path_complete")


def main() -> None:
    args = parse_args()
    cpu = json.loads(Path(args.cpu).read_text(encoding="utf-8"))
    vector = json.loads(Path(args.vector).read_text(encoding="utf-8"))
    fusion = json.loads(Path(args.fusion).read_text(encoding="utf-8"))
    methods = {
        "random": normalize_cpu(cpu["details"], "random"),
        "kmer_jaccard": normalize_cpu(cpu["details"], "kmer_jaccard"),
        "blast": normalize_cpu(cpu["details"], "blast"),
        "prott5": normalize_rows(vector["details"]),
        "prott5_blast_rrf": normalize_rows(fusion["details"]),
    }
    validate_query_sets(methods)
    analysis = {
        "dataset": args.label,
        "claim_scope": args.claim_scope,
        "query_count": len(next(iter(methods.values()))),
        "bootstrap_samples": args.bootstrap_samples,
        "seed": args.seed,
        "methods": {
            name: bootstrap_metrics(rows, samples=args.bootstrap_samples, seed=args.seed)
            for name, rows in methods.items()
        },
        "paired_deltas": {
            "prott5_minus_blast": paired_bootstrap(
                methods["prott5"], methods["blast"], samples=args.bootstrap_samples, seed=args.seed
            ),
            "fusion_minus_prott5": paired_bootstrap(
                methods["prott5_blast_rrf"], methods["prott5"], samples=args.bootstrap_samples, seed=args.seed + 1
            ),
            "blast_minus_random": paired_bootstrap(
                methods["blast"], methods["random"], samples=args.bootstrap_samples, seed=args.seed + 2
            ),
        },
        "source_results": {
            "cpu": args.cpu,
            "vector": args.vector,
            "fusion": args.fusion,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    markdown = output.with_suffix(".md")
    markdown.write_text(render_markdown(analysis), encoding="utf-8")
    print(json.dumps({"output": str(output), "markdown": str(markdown)}, indent=2))


def normalize_cpu(rows: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    return normalize_rows([row for row in rows if row.get("method") == method])


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "query_id": str(row["query_id"]),
                "hit_at_10": float(row.get("candidate_hit_at_10", row.get("protein_hit_at_10", False))),
                "mrr": float(row.get("candidate_mrr", row.get("protein_mrr", 0.0))),
                "paper_hit": float(row["paper_hit"]),
                "paper_recall": float(row["paper_recall"]),
                "path_complete": float(row["path_complete"]),
            }
        )
    return sorted(normalized, key=lambda row: row["query_id"])


def validate_query_sets(methods: dict[str, list[dict[str, Any]]]) -> None:
    expected: set[str] | None = None
    for name, rows in methods.items():
        query_ids = {str(row["query_id"]) for row in rows}
        if len(query_ids) != len(rows):
            raise ValueError(f"Duplicate query IDs in {name}")
        if expected is None:
            expected = query_ids
        elif query_ids != expected:
            raise ValueError(f"Query set mismatch in {name}: {len(query_ids)} != {len(expected)}")


def bootstrap_metrics(rows: list[dict[str, Any]], *, samples: int, seed: int) -> dict[str, Any]:
    matrix = np.asarray([[row[key] for key in METRICS] for row in rows], dtype=np.float64)
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
    query_ids = sorted(left_map)
    differences = np.asarray(
        [[left_map[q][key] - right_map[q][key] for key in METRICS] for q in query_ids],
        dtype=np.float64,
    )
    rng = np.random.default_rng(seed)
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


def render_markdown(analysis: dict[str, Any]) -> str:
    labels = {
        "random": "Random",
        "kmer_jaccard": "3-mer Jaccard",
        "blast": "BLASTP",
        "prott5": "ProtT5 mean",
        "prott5_blast_rrf": "ProtT5+BLAST RRF",
    }
    lines = [
        f"# {analysis['dataset']}",
        "",
        analysis["claim_scope"],
        "",
        f"Queries: `{analysis['query_count']}`; paired bootstrap samples: `{analysis['bootstrap_samples']}`.",
        "",
        "| Method | Candidate Hit@10 | Candidate MRR | Paper Hit | Paper Recall | Complete Path |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in labels:
        metrics = analysis["methods"][method]
        values = [format_interval(metrics[key]) for key in METRICS]
        lines.append(f"| {labels[method]} | " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "## Paired Differences",
            "",
            "| Contrast | Hit@10 delta | MRR delta | Paper Hit delta | Paper Recall delta | Complete Path delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    contrasts = {
        "prott5_minus_blast": "ProtT5 - BLASTP",
        "fusion_minus_prott5": "RRF - ProtT5",
        "blast_minus_random": "BLASTP - random",
    }
    for key, label in contrasts.items():
        delta = analysis["paired_deltas"][key]
        values = [format_interval(delta[metric]) for metric in METRICS]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "Intervals are query-level nonparametric paired bootstrap 95% intervals. Paper relevance follows "
            "the split's low-frequency shared-GO and index-side GOA evidence definition; it is not generic "
            "topical relevance or direct experimental support for the held-out protein.",
            "",
        ]
    )
    return "\n".join(lines)


def format_interval(row: dict[str, float]) -> str:
    return f"{row['mean']:.3f} [{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze cluster-held-out SeqLit-DAG retrieval")
    parser.add_argument("--label", required=True)
    parser.add_argument("--claim-scope", required=True)
    parser.add_argument("--cpu", required=True)
    parser.add_argument("--vector", required=True)
    parser.add_argument("--fusion", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260831)
    return parser.parse_args()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Summarize fixed-generator Agent results across BioRAG evidence routes."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


ROUTES = (
    ("no_retrieval", "No retrieval"),
    ("r2r_text_only", "Ordinary text RAG (R2R)"),
    ("sequence_vector", "Sequence vector"),
    ("combined_blast_vector", "Combined BLAST+vector"),
    ("combined_blast_vector_dag", "Combined BLAST+vector+DAG"),
)


def main() -> None:
    args = parse_args()
    root = Path(args.results_dir)
    rows = []
    missing = []
    scores_by_route = {}
    for route, label in ROUTES:
        generated_path = root / f"{args.prefix}_{route}_test66.json"
        score_path = root / f"{args.prefix}_{route}_test66_score.json"
        if not generated_path.exists() or not score_path.exists():
            missing.append(route)
            continue
        generated = json.loads(generated_path.read_text(encoding="utf-8"))
        score = json.loads(score_path.read_text(encoding="utf-8"))
        rows.append(to_row(route, label, generated, score))
        scores_by_route[route] = score
    result = {
        "dataset": "BioRAG downstream Agent evidence-route ablation",
        "claim_scope": (
            "The generator, decoding, query split, and answer contract are fixed across routes. "
            "The experiment measures the effect of available evidence, not free-form expert reasoning."
        ),
        "prefix": args.prefix,
        "routes": rows,
        "paired_comparisons": build_paired_comparisons(scores_by_route),
        "generator_robustness": load_generator_robustness(root, args.prefix),
        "missing_routes": missing,
        "r2r_text_control": load_r2r_control(Path(args.r2r_result)),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"output": str(output), "markdown": str(markdown), "missing": missing}, indent=2))


def to_row(route: str, label: str, generated: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    function = score["summary"]["function"]
    literature = score["summary"]["literature"]
    mechanism = score["summary"]["mechanism"]
    return {
        "route": route,
        "label": label,
        "query_count": score["query_count"],
        "function_f1": function["answer_f1"],
        "literature_f1": literature["answer_f1"],
        "function_prompt_gold_recall": function["prompt_gold_recall"],
        "literature_prompt_gold_recall": literature["prompt_gold_recall"],
        "function_selection_f1": function["evidence_selection_f1"],
        "literature_selection_f1": literature["evidence_selection_f1"],
        "mean_citation_entailment": (function["citation_entailment"] + literature["citation_entailment"]) / 2,
        "mean_pack_hallucination": (function["pack_hallucination_rate"] + literature["pack_hallucination_rate"]) / 2,
        "mechanism_abstention": mechanism["abstention_correct"],
        "peak_gpu_memory_gib": generated["peak_gpu_memory_gib"],
        "mean_generation_ms": generated["mean_generation_ms"],
        "p95_generation_ms": generated["p95_generation_ms"],
    }


def build_paired_comparisons(scores: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons = []
    specifications = (
        (
            "r2r_text_only",
            "sequence_vector",
            (
                ("function", "answer_f1"),
                ("literature", "answer_f1"),
                ("function", "prompt_gold_recall"),
                ("literature", "prompt_gold_recall"),
            ),
        ),
        (
            "sequence_vector",
            "combined_blast_vector",
            (
                ("function", "answer_f1"),
                ("literature", "answer_f1"),
                ("function", "prompt_gold_recall"),
                ("literature", "prompt_gold_recall"),
            ),
        ),
        (
            "combined_blast_vector",
            "combined_blast_vector_dag",
            (
                ("function", "answer_f1"),
                ("literature", "answer_f1"),
                ("function", "evidence_selection_f1"),
                ("literature", "evidence_selection_f1"),
            ),
        ),
    )
    for source, target, metrics in specifications:
        if source not in scores or target not in scores:
            continue
        for qa_type, metric in metrics:
            delta, low, high, query_count = paired_bootstrap_delta(
                scores[source],
                scores[target],
                qa_type=qa_type,
                metric=metric,
            )
            comparisons.append(
                {
                    "source": source,
                    "target": target,
                    "qa_type": qa_type,
                    "metric": metric,
                    "delta": delta,
                    "ci_low": low,
                    "ci_high": high,
                    "query_count": query_count,
                    "statistically_directional": low > 0.0 or high < 0.0,
                }
            )
    return comparisons


def paired_bootstrap_delta(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    qa_type: str,
    metric: str,
    seed: int = 20260830,
    replicates: int = 10000,
) -> tuple[float, float, float, int]:
    source_rows = {
        str(row["query_id"]): float(row[metric])
        for row in source["details"]
        if row["qa_type"] == qa_type
    }
    target_rows = {
        str(row["query_id"]): float(row[metric])
        for row in target["details"]
        if row["qa_type"] == qa_type
    }
    query_ids = sorted(source_rows.keys() & target_rows.keys())
    if not query_ids:
        return 0.0, 0.0, 0.0, 0
    deltas = [target_rows[query_id] - source_rows[query_id] for query_id in query_ids]
    rng = random.Random(seed)
    bootstrap = sorted(
        sum(deltas[rng.randrange(len(deltas))] for _ in deltas) / len(deltas)
        for _ in range(replicates)
    )
    return (
        sum(deltas) / len(deltas),
        bootstrap[int(0.025 * replicates)],
        bootstrap[min(int(0.975 * replicates), replicates - 1)],
        len(deltas),
    )


def load_generator_robustness(root: Path, main_prefix: str) -> list[dict[str, Any]]:
    rows = []
    for prefix, label in ((main_prefix, "Qwen3.5-9B"), ("qwen25", "Qwen2.5-7B-Instruct")):
        generated_path = root / f"{prefix}_combined_blast_vector_dag_test66.json"
        score_path = root / f"{prefix}_combined_blast_vector_dag_test66_score.json"
        if not generated_path.exists() or not score_path.exists():
            continue
        generated = json.loads(generated_path.read_text(encoding="utf-8"))
        score = json.loads(score_path.read_text(encoding="utf-8"))
        function = score["summary"]["function"]
        literature = score["summary"]["literature"]
        rows.append(
            {
                "generator": label,
                "function_f1": function["answer_f1"],
                "literature_f1": literature["answer_f1"],
                "function_selection_f1": function["evidence_selection_f1"],
                "literature_selection_f1": literature["evidence_selection_f1"],
                "mean_citation_entailment": (
                    function["citation_entailment"] + literature["citation_entailment"]
                )
                / 2,
                "mean_pack_hallucination": (
                    function["pack_hallucination_rate"] + literature["pack_hallucination_rate"]
                )
                / 2,
                "mechanism_abstention": score["summary"]["mechanism"]["abstention_correct"],
                "mean_generation_ms": generated["mean_generation_ms"],
                "peak_gpu_memory_gib": generated["peak_gpu_memory_gib"],
            }
        )
    return rows


def load_r2r_control(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "pending", "result_path": str(path)}
    result = json.loads(path.read_text(encoding="utf-8"))
    runtime = dict(result.get("runtime") or {})
    return {
        "status": "completed",
        "result_path": str(path),
        "collection_id": result.get("collection_id"),
        "embedding_label": result.get("embedding_label"),
        "r2r_sdk_version": runtime.get("r2r_sdk_version"),
        "document_count": dict(runtime.get("collection") or {}).get("document_count"),
        "retrieval_latency": result.get("latency"),
        "retrieval_summary": result.get("retrieval_summary"),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Application Route Ablation",
        "",
        result["claim_scope"],
        "",
        "| Route | Function F1 | Literature F1 | GO prompt recall | PMID prompt recall | GO/PMID selection F1 | Citation entailment | Pack hallucination | Mechanism abstention | Mean/P95 generation ms | Peak GPU GiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["routes"]:
        selection = (
            "--"
            if row["route"] == "no_retrieval"
            else f"{row['function_selection_f1']:.3f}/{row['literature_selection_f1']:.3f}"
        )
        entailment = "--" if row["route"] == "no_retrieval" else f"{row['mean_citation_entailment']:.3f}"
        lines.append(
            f"| {row['label']} | {row['function_f1']:.3f} | {row['literature_f1']:.3f} | "
            f"{row['function_prompt_gold_recall']:.3f} | {row['literature_prompt_gold_recall']:.3f} | "
            f"{selection} | {entailment} | {row['mean_pack_hallucination']:.3f} | "
            f"{row['mechanism_abstention']:.3f} | {row['mean_generation_ms']:.1f}/{row['p95_generation_ms']:.1f} | "
            f"{row['peak_gpu_memory_gib']:.3f} |"
        )
    lines.append("")
    r2r_control = result["r2r_text_control"]
    if r2r_control["status"] == "completed":
        latency = dict(r2r_control.get("retrieval_latency") or {})
        lines.extend(
            [
                f"The ordinary text-RAG control is a live R2R {r2r_control.get('r2r_sdk_version')} collection "
                f"(`{r2r_control.get('collection_id')}`) with {r2r_control.get('document_count')} documents and "
                f"{r2r_control.get('embedding_label')}. Graph search is disabled. Its server-side query embedding "
                f"plus lookup latency is {latency.get('mean_ms', 0.0):.1f} ms mean and "
                f"{latency.get('p95_ms', 0.0):.1f} ms P95.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The R2R text-only row is pending until a live collection ID, R2R version, and embedding configuration are frozen. No proxy result is labeled as R2R.",
                "",
            ]
        )
    lines.extend(
        [
            "The no-retrieval condition applies the system's no-evidence abstention policy; citation entailment and evidence selection are therefore not applicable rather than positive results.",
            "",
        ]
    )
    if result["paired_comparisons"]:
        lines.extend(
            [
                "## Paired Query Bootstrap",
                "",
                "| Comparison | QA type | Metric | Delta | 95% CI |",
                "|---|---|---|---:|---:|",
            ]
        )
        for row in result["paired_comparisons"]:
            comparison = f"{row['source']} -> {row['target']}"
            lines.append(
                f"| {comparison} | {row['qa_type']} | {row['metric']} | "
                f"{row['delta']:+.3f} | [{row['ci_low']:+.3f}, {row['ci_high']:+.3f}] |"
            )
        lines.extend(
            [
                "",
                "Intervals are paired over the same 66 query IDs with 10,000 bootstrap replicates. A confidence interval crossing zero is treated as directional engineering evidence, not a statistically resolved gain.",
                "",
            ]
        )
    if result["generator_robustness"]:
        lines.extend(
            [
                "## Generator Robustness",
                "",
                "Both generators execute the identical combined BLAST+vector+DAG pack; this is a robustness check, not a generator contribution.",
                "",
                "| Generator | Function F1 | Literature F1 | GO/PMID selection F1 | Citation entailment | Pack hallucination | Mechanism abstention | Mean generation ms | Peak GPU GiB |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in result["generator_robustness"]:
            lines.append(
                f"| {row['generator']} | {row['function_f1']:.3f} | {row['literature_f1']:.3f} | "
                f"{row['function_selection_f1']:.3f}/{row['literature_selection_f1']:.3f} | "
                f"{row['mean_citation_entailment']:.3f} | {row['mean_pack_hallucination']:.3f} | "
                f"{row['mechanism_abstention']:.3f} | {row['mean_generation_ms']:.1f} | "
                f"{row['peak_gpu_memory_gib']:.3f} |"
            )
        lines.append("")
    if result["missing_routes"]:
        lines.extend([f"Missing local routes: `{', '.join(result['missing_routes'])}`.", ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize generated Agent application route results")
    parser.add_argument("--results-dir", default="reports/results/agent_application_ablation")
    parser.add_argument("--prefix", default="qwen35")
    parser.add_argument("--output", default="reports/results/agent_application_ablation_qwen35.json")
    parser.add_argument("--markdown", default="reports/agent_application_ablation_qwen35.md")
    parser.add_argument("--r2r-result", default="reports/results/r2r_text_control_qwen3_06b.json")
    return parser.parse_args()


if __name__ == "__main__":
    main()

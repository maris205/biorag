#!/usr/bin/env python3
"""Decode completed blinded forms and summarize the SeqLit expert review."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.agent_review import REVIEW_ROUTES


ORDINAL_FIELDS = (
    "functional_correctness_0_4",
    "citation_support_0_4",
    "literature_relevance_0_4",
    "calibration_0_4",
    "actionability_0_4",
)
RANK_FIELD = "within_case_rank_1_5"
OVERCLAIM_FIELD = "overclaim_0_1"
COMPARISONS = (
    ("no_retrieval", "r2r_text_only"),
    ("r2r_text_only", "sequence_vector"),
    ("sequence_vector", "combined_blast_vector"),
    ("combined_blast_vector", "combined_blast_vector_dag"),
    ("no_retrieval", "combined_blast_vector_dag"),
)


def main() -> None:
    args = parse_args()
    key = json.loads(Path(args.answer_key).read_text(encoding="utf-8"))
    route_key, expected_items = load_route_key(key)
    ratings = load_ratings([Path(item) for item in args.ratings], expected_items=expected_items)
    result = summarize_ratings(
        ratings,
        route_key=route_key,
        expected_items=expected_items,
        seed=args.seed,
        bootstrap_replicates=args.bootstrap_replicates,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"output": str(output), "markdown": str(markdown), "reviewers": result["reviewers"]}, indent=2))


def load_route_key(key: dict[str, Any]) -> tuple[dict[tuple[str, str], str], set[tuple[str, str]]]:
    route_key: dict[tuple[str, str], str] = {}
    for case in key["cases"]:
        case_id = str(case["case_id"])
        for variant_id, item in case["variant_key"].items():
            route_key[(case_id, str(variant_id))] = str(item["route"])
    return route_key, set(route_key)


def load_ratings(paths: list[Path], *, expected_items: set[tuple[str, str]]) -> list[dict[str, Any]]:
    ratings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    reviewer_items: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for path in paths:
        with path.open("rt", encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                if not any(str(value or "").strip() for value in raw.values()):
                    continue
                reviewer = str(raw.get("reviewer_id") or "").strip()
                case_id = str(raw.get("case_id") or "").strip()
                variant_id = str(raw.get("variant_id") or "").strip()
                if not reviewer:
                    raise ValueError(f"Missing reviewer_id in {path}: {case_id}/{variant_id}")
                item = (case_id, variant_id)
                if item not in expected_items:
                    raise ValueError(f"Unknown review item in {path}: {item}")
                unique = (reviewer, case_id, variant_id)
                if unique in seen:
                    raise ValueError(f"Duplicate rating: {unique}")
                seen.add(unique)
                reviewer_items[reviewer].add(item)
                row: dict[str, Any] = {
                    "reviewer_id": reviewer,
                    "case_id": case_id,
                    "variant_id": variant_id,
                    "notes": str(raw.get("notes") or ""),
                }
                for field in ORDINAL_FIELDS:
                    row[field] = parse_score(raw, field, minimum=0, maximum=4, path=path)
                row[OVERCLAIM_FIELD] = parse_score(raw, OVERCLAIM_FIELD, minimum=0, maximum=1, path=path)
                row[RANK_FIELD] = parse_score(raw, RANK_FIELD, minimum=1, maximum=5, path=path)
                ratings.append(row)
    if not ratings:
        raise ValueError("No completed ratings were found")
    for reviewer, items in reviewer_items.items():
        missing = expected_items - items
        extra = items - expected_items
        if missing or extra:
            raise ValueError(f"Reviewer {reviewer} has missing={len(missing)} extra={len(extra)} items")
    validate_ranks(ratings)
    return ratings


def summarize_ratings(
    ratings: list[dict[str, Any]],
    *,
    route_key: dict[tuple[str, str], str],
    expected_items: set[tuple[str, str]],
    seed: int = 20260831,
    bootstrap_replicates: int = 10000,
) -> dict[str, Any]:
    del expected_items
    reviewers = sorted({str(row["reviewer_id"]) for row in ratings})
    decoded = []
    for row in ratings:
        item = (str(row["case_id"]), str(row["variant_id"]))
        primary = mean(float(row[field]) for field in (
            "functional_correctness_0_4",
            "citation_support_0_4",
            "calibration_0_4",
        ))
        decoded.append({**row, "route": route_key[item], "primary_utility": primary})

    case_route: dict[tuple[str, str], dict[str, float]] = {}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in decoded:
        grouped[(str(row["case_id"]), str(row["route"]))].append(row)
    metric_fields = (*ORDINAL_FIELDS, OVERCLAIM_FIELD, RANK_FIELD, "primary_utility")
    for item, rows in grouped.items():
        case_route[item] = {field: mean(float(row[field]) for row in rows) for field in metric_fields}

    present_routes = {route for _case, route in case_route}
    routes = [route for route in REVIEW_ROUTES if route in present_routes]
    route_rows = []
    for route in routes:
        rows = [values for (_case, row_route), values in case_route.items() if row_route == route]
        route_rows.append(
            {
                "route": route,
                "case_count": len(rows),
                **{field: mean(row[field] for row in rows) for field in metric_fields},
            }
        )

    comparisons = []
    for source, target in COMPARISONS:
        for field in ("primary_utility", *ORDINAL_FIELDS, OVERCLAIM_FIELD, RANK_FIELD):
            delta, low, high, count = paired_case_bootstrap(
                case_route,
                source=source,
                target=target,
                field=field,
                seed=seed,
                replicates=bootstrap_replicates,
            )
            comparisons.append(
                {
                    "source": source,
                    "target": target,
                    "metric": field,
                    "delta_target_minus_source": delta,
                    "ci_low": low,
                    "ci_high": high,
                    "case_count": count,
                }
            )
    return {
        "dataset": "BioRAG SeqLit assessor-blinded free-form Agent evaluation",
        "reviewers": reviewers,
        "reviewer_count": len(reviewers),
        "case_count": len({case for case, _route in case_route}),
        "rating_count": len(ratings),
        "analysis_unit": "Reviewer scores are averaged within case/route; paired bootstrap resamples cases.",
        "primary_endpoint": "mean(functional correctness, citation support, calibration)",
        "routes": route_rows,
        "paired_comparisons": comparisons,
        "inter_rater_agreement": agreement_summary(decoded, reviewers),
    }


def paired_case_bootstrap(
    rows: dict[tuple[str, str], dict[str, float]],
    *,
    source: str,
    target: str,
    field: str,
    seed: int,
    replicates: int,
) -> tuple[float, float, float, int]:
    cases = sorted(
        case
        for case, route in rows
        if route == source and (case, target) in rows
    )
    if not cases:
        return 0.0, 0.0, 0.0, 0
    deltas = [rows[(case, target)][field] - rows[(case, source)][field] for case in cases]
    rng = random.Random(f"{seed}:{source}:{target}:{field}")
    samples = sorted(
        mean(deltas[rng.randrange(len(deltas))] for _ in deltas)
        for _ in range(replicates)
    )
    return (
        mean(deltas),
        samples[int(0.025 * replicates)],
        samples[min(int(0.975 * replicates), replicates - 1)],
        len(cases),
    )


def agreement_summary(rows: list[dict[str, Any]], reviewers: list[str]) -> dict[str, Any]:
    if len(reviewers) != 2:
        return {"status": "requires exactly two complete reviewers", "reviewer_count": len(reviewers)}
    by_reviewer = {
        reviewer: {
            (str(row["case_id"]), str(row["variant_id"])): row
            for row in rows
            if row["reviewer_id"] == reviewer
        }
        for reviewer in reviewers
    }
    items = sorted(set(by_reviewer[reviewers[0]]) & set(by_reviewer[reviewers[1]]))
    agreement: dict[str, Any] = {"status": "completed", "item_count": len(items)}
    for field in (*ORDINAL_FIELDS, RANK_FIELD):
        first = [int(by_reviewer[reviewers[0]][item][field]) for item in items]
        second = [int(by_reviewer[reviewers[1]][item][field]) for item in items]
        minimum, maximum = (1, 5) if field == RANK_FIELD else (0, 4)
        agreement[field] = quadratic_weighted_kappa(first, second, minimum=minimum, maximum=maximum)
    first_flags = [int(by_reviewer[reviewers[0]][item][OVERCLAIM_FIELD]) for item in items]
    second_flags = [int(by_reviewer[reviewers[1]][item][OVERCLAIM_FIELD]) for item in items]
    agreement["overclaim_raw_agreement"] = mean(a == b for a, b in zip(first_flags, second_flags))
    return agreement


def quadratic_weighted_kappa(first: list[int], second: list[int], *, minimum: int, maximum: int) -> float:
    if len(first) != len(second) or not first:
        return 0.0
    categories = list(range(minimum, maximum + 1))
    index = {value: offset for offset, value in enumerate(categories)}
    size = len(categories)
    observed = [[0.0 for _ in categories] for _ in categories]
    first_counts = [0.0 for _ in categories]
    second_counts = [0.0 for _ in categories]
    for left, right in zip(first, second):
        observed[index[left]][index[right]] += 1.0
        first_counts[index[left]] += 1.0
        second_counts[index[right]] += 1.0
    total = float(len(first))
    denominator = float((size - 1) ** 2) or 1.0
    observed_disagreement = 0.0
    expected_disagreement = 0.0
    for i, j in itertools.product(range(size), repeat=2):
        weight = ((i - j) ** 2) / denominator
        observed_disagreement += weight * observed[i][j] / total
        expected_disagreement += weight * (first_counts[i] * second_counts[j]) / (total * total)
    if expected_disagreement == 0.0:
        return 1.0 if observed_disagreement == 0.0 else 0.0
    return 1.0 - observed_disagreement / expected_disagreement


def validate_ranks(ratings: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in ratings:
        grouped[(str(row["reviewer_id"]), str(row["case_id"]))].append(int(row[RANK_FIELD]))
    for key, ranks in grouped.items():
        if sorted(ranks) != [1, 2, 3, 4, 5]:
            raise ValueError(f"Ranks for reviewer/case {key} must be a permutation of 1..5: {ranks}")


def parse_score(raw: dict[str, str], field: str, *, minimum: int, maximum: int, path: Path) -> int:
    value = str(raw.get(field) or "").strip()
    try:
        score = int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}={value!r} in {path}") from exc
    if not minimum <= score <= maximum:
        raise ValueError(f"Out-of-range {field}={score} in {path}")
    return score


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Assessor-Blinded Free-form Agent Evaluation",
        "",
        f"Reviewers: {result['reviewer_count']}; cases: {result['case_count']}; ratings: {result['rating_count']}.",
        "",
        f"Primary endpoint: {result['primary_endpoint']}.",
        "",
        "| Route | Primary utility | Function | Citation support | Literature relevance | Calibration | Actionability | Overclaim | Mean rank |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["routes"]:
        lines.append(
            f"| {row['route']} | {row['primary_utility']:.3f} | "
            f"{row['functional_correctness_0_4']:.3f} | {row['citation_support_0_4']:.3f} | "
            f"{row['literature_relevance_0_4']:.3f} | {row['calibration_0_4']:.3f} | "
            f"{row['actionability_0_4']:.3f} | {row['overclaim_0_1']:.3f} | "
            f"{row['within_case_rank_1_5']:.3f} |"
        )
    lines.extend(["", "## Preregistered Paired Contrasts", "", "| Comparison | Metric | Delta | 95% CI |", "|---|---|---:|---:|"])
    for row in result["paired_comparisons"]:
        if row["metric"] not in {"primary_utility", "functional_correctness_0_4", "overclaim_0_1"}:
            continue
        lines.append(
            f"| {row['source']} -> {row['target']} | {row['metric']} | "
            f"{row['delta_target_minus_source']:+.3f} | [{row['ci_low']:+.3f}, {row['ci_high']:+.3f}] |"
        )
    lines.extend(["", "Intervals resample paired cases after averaging reviewers within case/route.", ""])
    return "\n".join(lines)


def mean(values: Any) -> float:
    rows = [float(value) for value in values]
    return sum(rows) / len(rows) if rows else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize completed SeqLit expert-review forms")
    parser.add_argument("ratings", nargs="+", help="One or more completed review CSV files")
    parser.add_argument("--answer-key", default="reports/agent_expert_review_package/organizer/answer_key.json")
    parser.add_argument("--output", default="reports/results/agent_expert_review_scored.json")
    parser.add_argument("--markdown", default="reports/agent_expert_review_scored.md")
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--bootstrap-replicates", type=int, default=10000)
    return parser.parse_args()


if __name__ == "__main__":
    main()

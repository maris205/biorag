#!/usr/bin/env python3
"""Blind generated Agent notes and create an expert-scoring package."""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.agent_review import REVIEW_ROUTES, audit_freeform_answer, identifier_scores, stable_digest
from dnarag.seq_lit_dag.build import parse_go_obo


def main() -> None:
    args = parse_args()
    root = Path(args.input)
    output = Path(args.output)
    evaluator_output = output / "evaluator"
    organizer_output = output / "organizer"
    evaluator_output.mkdir(parents=True, exist_ok=True)
    organizer_output.mkdir(parents=True, exist_ok=True)
    selection = json.loads((root / "selection_manifest.json").read_text(encoding="utf-8"))
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    go_terms = parse_go_obo(Path(args.go_obo))
    generated = {
        route: json.loads((root / f"freeform_{route}.json").read_text(encoding="utf-8"))
        for route in REVIEW_ROUTES
    }
    selected = list(selection["selected_queries"])
    generated_by_route = {
        route: {str(row["query_id"]): row for row in result["outputs"]}
        for route, result in generated.items()
    }
    expected_ids = {str(row["query_id"]) for row in selected}
    for route, rows in generated_by_route.items():
        if set(rows) != expected_ids:
            raise ValueError(f"Route {route} query mismatch: {len(rows)} rows")

    case_order = sorted(expected_ids, key=lambda query_id: stable_digest(f"{args.seed}:case:{query_id}"))
    case_ids = {query_id: f"BRX-{index:03d}" for index, query_id in enumerate(case_order, start=1)}
    selection_by_id = {str(row["query_id"]): row for row in selected}
    cases = []
    answer_key = []
    auto_rows: dict[str, list[dict[str, Any]]] = {route: [] for route in REVIEW_ROUTES}
    latin_base = list(REVIEW_ROUTES)
    random.Random(args.seed).shuffle(latin_base)
    variant_position_counts = {
        route: {letter: 0 for letter in "ABCDE"}
        for route in REVIEW_ROUTES
    }
    heldout_exposure_count = 0
    route_label_exposure_count = 0
    for case_index, query_id in enumerate(case_order):
        query = queries[query_id]
        case_id = case_ids[query_id]
        shift = case_index % len(latin_base)
        route_order = latin_base[shift:] + latin_base[:shift]
        variants = []
        variant_key = {}
        for variant_index, route in enumerate(route_order):
            variant_id = chr(ord("A") + variant_index)
            row = generated_by_route[route][query_id]
            audit = audit_freeform_answer(row["answer"], row)
            variant_position_counts[route][variant_id] += 1
            variants.append(
                {
                    "variant_id": variant_id,
                    "evidence": row["evidence_lines"],
                    "answer": row["answer"],
                }
            )
            variant_key[variant_id] = {
                "route": route,
                "automatic_audit": audit,
                "identifier_scores": identifier_scores(row["answer"], query),
            }
            auto_rows[route].append(
                {
                    **audit,
                    **identifier_scores(row["answer"], query),
                    "query_id": query_id,
                }
            )
        cases.append(
            {
                "case_id": case_id,
                "sequence": query["query"],
                "instruction": (
                    "Score each independently. Retrieved candidates are indirect evidence; a useful answer must "
                    "not present transferred function as direct validation of the held-out sequence."
                ),
                "variants": variants,
            }
        )
        public_case_text = json.dumps(cases[-1], ensure_ascii=False)
        if str(query.get("heldout_accession") or "") in public_case_text:
            heldout_exposure_count += 1
        if any(route in public_case_text for route in REVIEW_ROUTES):
            route_label_exposure_count += 1
        answer_key.append(
            {
                "case_id": case_id,
                "query_id": query_id,
                "stratum": selection_by_id[query_id]["stratum"],
                "heldout_accession": query.get("heldout_accession"),
                "expected_go_ids": query.get("expected_go_ids", []),
                "expected_go_names": [
                    go_terms[go_id].name if go_id in go_terms else "name unavailable"
                    for go_id in query.get("expected_go_ids", [])
                ],
                "expected_pmids": query.get("expected_pmids", []),
                "variant_key": variant_key,
            }
        )

    cases_path = evaluator_output / "review_cases.jsonl"
    cases_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in cases), encoding="utf-8")
    (organizer_output / "answer_key.json").write_text(
        json.dumps({"seed": args.seed, "cases": answer_key}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (evaluator_output / "review_form.csv").write_text(render_review_form(cases), encoding="utf-8")
    (evaluator_output / "REVIEW_PROTOCOL.md").write_text(render_protocol(len(cases)), encoding="utf-8")
    (evaluator_output / "review_booklet.md").write_text(render_booklet(cases), encoding="utf-8")

    automatic = {
        "dataset": "BioRAG SeqLit free-form automatic identifier audit",
        "claim_boundary": (
            "These are format, citation-ID, and exact GO/PMID overlap checks. They are not substitutes for "
            "the blinded domain-expert assessment of biological correctness and usefulness."
        ),
        "query_count": len(cases),
        "blinding_audit": {
            "heldout_accession_exposure_count": heldout_exposure_count,
            "route_label_exposure_count": route_label_exposure_count,
            "variant_position_counts": variant_position_counts,
            "latin_square_balanced": all(
                set(counts.values()) == {len(cases) // len(REVIEW_ROUTES)}
                for counts in variant_position_counts.values()
            ),
        },
        "routes": [summarize_route(route, rows, generated[route]) for route, rows in auto_rows.items()],
    }
    (organizer_output / "automatic_audit.json").write_text(json.dumps(automatic, indent=2) + "\n", encoding="utf-8")
    (organizer_output / "AUTOMATIC_AUDIT.md").write_text(render_automatic(automatic), encoding="utf-8")
    (output / "README.md").write_text(render_package_readme(), encoding="utf-8")
    remove_legacy_root_files(output)
    print(
        json.dumps(
            {
                "output": str(output),
                "evaluator_package": str(evaluator_output),
                "organizer_key": str(organizer_output / "answer_key.json"),
                "cases": len(cases),
                "variants": len(cases) * len(REVIEW_ROUTES),
            },
            indent=2,
        )
    )


def summarize_route(route: str, rows: list[dict[str, Any]], generated: dict[str, Any]) -> dict[str, Any]:
    numeric = (
        "citation_validity",
        "go_citation_entailment",
        "pmid_citation_entailment",
        "go_precision",
        "go_recall",
        "go_f1",
        "pmid_precision",
        "pmid_recall",
        "pmid_f1",
    )
    summary = {key: mean(float(row[key]) for row in rows) for key in numeric}
    summary.update(
        {
            "route": route,
            "query_count": len(rows),
            "format_compliance": mean(bool(row["format_compliance"]) for row in rows),
            "citation_syntax_compliance": mean(bool(row["citation_syntax_compliance"]) for row in rows),
            "calibration_language": mean(bool(row["calibration_language"]) for row in rows),
            "overclaim_rate": mean(bool(row["overclaim_flag"]) for row in rows),
            "out_of_pack_identifier_rate": mean(
                bool(row["out_of_pack_go_ids"] or row["out_of_pack_pmids"]) for row in rows
            ),
            "abstention_rate": mean(bool(row["abstention"]) for row in rows),
            "mean_generation_ms": generated.get("mean_generation_ms", 0.0),
            "p95_generation_ms": generated.get("p95_generation_ms", 0.0),
            "peak_gpu_memory_gib": generated.get("peak_gpu_memory_gib", 0.0),
        }
    )
    return summary


def render_review_form(cases: list[dict[str, Any]]) -> str:
    handle = io.StringIO()
    fields = [
        "reviewer_id",
        "case_id",
        "variant_id",
        "functional_correctness_0_4",
        "citation_support_0_4",
        "literature_relevance_0_4",
        "calibration_0_4",
        "actionability_0_4",
        "overclaim_0_1",
        "within_case_rank_1_5",
        "notes",
    ]
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for case in cases:
        for variant in case["variants"]:
            writer.writerow({"case_id": case["case_id"], "variant_id": variant["variant_id"]})
    return handle.getvalue()


def render_protocol(case_count: int) -> str:
    return f"""# Blinded SeqLit Agent Expert Review Protocol

## Status and claim boundary

This is a frozen evaluation package, not a completed expert-study result. The
route key in `answer_key.json` must remain hidden until every reviewer has
submitted a complete form.

## Design

- {case_count} held-out protein-sequence cases from the frozen 66-query test set.
- Equal allocation to single-GO/sparse-literature, single-GO/dense-literature,
  and multi-GO strata.
- Five within-case evidence routes; route labels are masked and presentation
  order follows a seed-randomized, balanced Latin square.
- One fixed Qwen3.5-9B BF16 generator and deterministic decoding for all routes.
- Two independent reviewers with biological sequence-analysis or protein-
  annotation experience; disagreements are adjudicated only after initial
  forms are locked.

## Rating rubric

Score every variant independently from 0 (unacceptable) to 4 (strong):

1. `functional_correctness_0_4`: function hypotheses agree with the held-out
   reference annotation and do not over-transfer neighbor annotations.
2. `citation_support_0_4`: cited evidence actually supports the adjacent claim.
3. `literature_relevance_0_4`: selected papers are useful for investigating the
   proposed function of the held-out sequence.
4. `calibration_0_4`: the answer distinguishes indirect retrieval evidence from
   direct validation and states important uncertainty.
5. `actionability_0_4`: the note gives a scientist a defensible next step.

Set `overclaim_0_1=1` if the answer asserts a mechanism, disease relation, or
validated query function beyond the supplied evidence. Rank variants 1 (best)
through 5 (worst) within a case; ties are not allowed. Add short notes for any
score of 0 or overclaim flag.

## Frozen analysis

- Primary endpoint: mean of functional correctness, citation support, and
  calibration.
- Secondary endpoints: literature relevance, actionability, overclaim rate,
  and within-case rank.
- Average reviewers within case/route, then use paired case bootstrap intervals
  for route contrasts. The case, not the answer, is the resampling unit.
- Report quadratic-weighted agreement for ordinal scores and raw agreement for
  overclaim flags.
- Automatic GO/PMID overlap is a diagnostic only and must not replace expert
  scoring.
"""


def render_package_readme() -> str:
    return """# SeqLit Agent Expert Review Package

Share only the `evaluator/` directory with blinded reviewers. It contains the
case booklet, machine-readable cases, protocol, and blank scoring form.

The `organizer/` directory contains the route key, held-out reference labels,
and automatic diagnostics. Do not open or distribute it until all reviewer
forms are complete and locked.
"""


def remove_legacy_root_files(output: Path) -> None:
    for name in (
        "review_cases.jsonl",
        "review_form.csv",
        "REVIEW_PROTOCOL.md",
        "review_booklet.md",
        "answer_key.json",
        "automatic_audit.json",
        "AUTOMATIC_AUDIT.md",
    ):
        path = output / name
        if path.exists():
            path.unlink()


def render_booklet(cases: list[dict[str, Any]]) -> str:
    lines = ["# Blinded SeqLit Agent Review Booklet", "", "Use `review_form.csv` for scores.", ""]
    for case in cases:
        lines.extend([f"## {case['case_id']}", "", f"Sequence: `{case['sequence']}`", "", case["instruction"], ""])
        for variant in case["variants"]:
            lines.extend([f"### Variant {variant['variant_id']}", "", "Evidence:", ""])
            lines.extend(f"- `{line}`" for line in variant["evidence"])
            lines.extend(["", "Answer:", "", variant["answer"], ""])
    return "\n".join(lines) + "\n"


def render_automatic(result: dict[str, Any]) -> str:
    lines = [
        "# Free-form Agent Automatic Audit",
        "",
        result["claim_boundary"],
        "",
        "| Route | GO F1 | PMID F1 | Citation ID validity | GO/PMID citation entailment | Citation syntax | Out-of-pack IDs | Format | Calibration | Overclaim | Abstention | Mean/P95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["routes"]:
        lines.append(
            f"| {row['route']} | {row['go_f1']:.3f} | {row['pmid_f1']:.3f} | "
            f"{row['citation_validity']:.3f} | {row['go_citation_entailment']:.3f}/{row['pmid_citation_entailment']:.3f} | "
            f"{row['citation_syntax_compliance']:.3f} | {row['out_of_pack_identifier_rate']:.3f} | "
            f"{row['format_compliance']:.3f} | {row['calibration_language']:.3f} | "
            f"{row['overclaim_rate']:.3f} | {row['abstention_rate']:.3f} | "
            f"{row['mean_generation_ms']:.1f}/{row['p95_generation_ms']:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def mean(values: Any) -> float:
    rows = [float(value) for value in values]
    return sum(rows) / len(rows) if rows else 0.0


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a blinded SeqLit expert-review package")
    parser.add_argument("--input", default="reports/results/agent_expert_review")
    parser.add_argument("--output", default="reports/agent_expert_review_package")
    parser.add_argument("--queries", default="data/seq_lit_dag_function_heldout_2k/queries.jsonl")
    parser.add_argument("--go-obo", default="/autodl-fs/data/open-rosalind-kb/standard/raw/go/go-basic.obo")
    parser.add_argument("--seed", type=int, default=20260831)
    return parser.parse_args()


if __name__ == "__main__":
    main()

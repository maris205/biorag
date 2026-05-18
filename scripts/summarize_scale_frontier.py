#!/usr/bin/env python3
"""Build a scale-frontier report from completed BLAST/vector/candidate-BLAST runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROWS = [
    {
        "label": "controlled20k",
        "records": 20000,
        "blast": "reports/protein_parent_frag_500_controlled20k_blast_eval.json",
        "vector": "reports/protein_parent_frag_500_controlled20k_prott5_mean_window_vector_top200_eval.json",
        "candidate": None,
        "notes": "completed controlled same-gene subset",
    },
    {
        "label": "controlled100k",
        "records": 100000,
        "blast": "reports/protein_parent_frag_500_controlled100k_blast_eval.json",
        "vector": "reports/protein_parent_frag_500_controlled100k_prott5_mean_v2_window_vector_top200_eval.json",
        "candidate": "reports/protein_parent_frag_500_controlled100k_prott5_mean_v2_candidate_blast_n200_parseids_eval.json",
        "notes": "completed controlled same-gene subset; 100k parents expand to 589,210 indexed windows",
    },
    {
        "label": "controlled300k",
        "records": 300000,
        "blast": "reports/protein_parent_frag_500_controlled300k_blast_eval.json",
        "vector": "reports/protein_parent_frag_500_controlled300k_prott5_mean_window_vector_top200_eval.json",
        "candidate": "reports/protein_parent_frag_500_controlled300k_prott5_mean_candidate_blast_n200_parseids_eval.json",
        "notes": "completed controlled same-gene subset; 300k parents expand to 1,789,478 indexed windows",
    },
    {
        "label": "full held-out Swiss-Prot",
        "records": 483581,
        "blast": "reports/protein_parent_frag_500_blast_eval.json",
        "vector": None,
        "candidate": None,
        "notes": "full BLAST reference completed; full vector index pending",
    },
]


def main() -> None:
    args = parse_args()
    rows = [build_row(row) for row in ROWS]
    payload = {
        "benchmark": "benchmarks/protein_parent_frag_500.jsonl",
        "interpretation": (
            "This is a scale-frontier tracking table. Completed BLAST rows show "
            "alignment-reference latency as the indexed protein corpus grows. "
            "Vector and candidate-BLAST rows are reported only where a matching "
            "vector index exists; larger vector indexes remain pending background jobs. "
            "Candidate-BLAST is treated as an ablation unless it improves both "
            "biological retrieval quality and verified-route latency at matched scale."
        ),
        "rows": rows,
        "pending_jobs": [
            "Build ProtT5 or ESM-2 mean protein_sequence_window vector indexes for full held-out Swiss-Prot.",
            "Run vector top-200 and vector->candidate-BLAST budget sweeps at full scale.",
            "Only claim candidate-BLAST speed advantage if matched-accuracy latency crosses full BLAST at larger scale or after optimized vector serving; the completed 100k and 300k Chroma points do not cross it.",
        ],
    }
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"output_json": str(output_json), "output_md": str(output_md), "rows": len(rows)}, indent=2))


def build_row(spec: dict[str, Any]) -> dict[str, Any]:
    row = {
        "label": spec["label"],
        "records": spec["records"],
        "blast": load_eval_summary(spec.get("blast"), condition="blast"),
        "vector": load_eval_summary(spec.get("vector"), condition="vector"),
        "candidate_blast": load_candidate_summary(spec.get("candidate")),
        "notes": spec["notes"],
    }
    row["status"] = status_for(row)
    return row


def load_eval_summary(path_value: str | None, *, condition: str) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return {"status": "pending", "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = dict((data.get("summary") or {}).get(condition) or {})
    if not summary:
        return {"status": "missing_summary", "path": str(path)}
    return {
        "status": "completed",
        "path": str(path),
        "tasks": int(summary.get("tasks") or 0),
        "bio_hit_at_10": float(summary.get("bio_hit_at_10") or 0.0),
        "bio_mrr": float(summary.get("bio_mrr") or 0.0),
        "bio_recall_at_200": bio_recall_at_k(data.get("details") or [], 200),
        "avg_latency_ms": float(summary.get("avg_latency_ms") or 0.0),
        "elapsed_s": float(summary.get("elapsed_s") or 0.0),
    }


def load_candidate_summary(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return {"status": "pending", "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = (data.get("summary_by_budget") or {}).get("200") or data.get("summary") or {}
    return {
        "status": "completed",
        "path": str(path),
        "tasks": int(summary.get("tasks") or 0),
        "ok_tasks": int(summary.get("ok_tasks") or summary.get("tasks") or 0),
        "bio_hit_at_10": float(summary.get("bio_hit_at_10") or 0.0),
        "bio_mrr": float(summary.get("bio_mrr") or 0.0),
        "candidate_bio_recall": float(summary.get("candidate_bio_hit_at_n") or 0.0),
        "avg_latency_ms": float(summary.get("avg_latency_ms") or 0.0),
        "vector_latency_ms": float(summary.get("avg_vector_latency_ms") or 0.0),
        "candidate_blast_latency_ms": float(summary.get("avg_candidate_blast_latency_ms") or 0.0),
        "avg_blast_hit_count": float(summary.get("avg_blast_hit_count") or 0.0),
    }


def bio_recall_at_k(rows: list[dict[str, Any]], k: int) -> float:
    evaluable = [row for row in rows if row.get("bio_evaluable")]
    if not evaluable:
        return 0.0
    hits = 0
    for row in evaluable:
        rank = row.get("bio_rank")
        if rank is not None and int(rank) <= k:
            hits += 1
    return hits / len(evaluable)


def status_for(row: dict[str, Any]) -> str:
    vector = row.get("vector")
    candidate = row.get("candidate_blast")
    if vector and vector.get("status") == "completed" and candidate and candidate.get("status") == "completed":
        return "complete"
    if vector and vector.get("status") == "completed":
        return "vector_complete_candidate_pending"
    if row.get("blast") and row["blast"].get("status") == "completed":
        return "blast_complete_vector_pending"
    return "pending"


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Swiss-Prot Scale Frontier",
        "",
        payload["interpretation"],
        "",
        "## Completed and Pending Scale Points",
        "",
        "| Scale | Records | BLAST Bio@10 | BLAST MRR | BLAST ms | Vector Bio@10 | Vector MRR | Vector Recall@200 | Vector ms | Candidate-BLAST Bio@10 | Candidate MRR | Candidate Recall@200 | Candidate total ms | Candidate BLAST-only ms | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["rows"]:
        blast = row.get("blast") or {}
        vector = row.get("vector") or {}
        candidate = row.get("candidate_blast") or {}
        lines.append(
            f"| {row['label']} | {row['records']} | "
            f"{fmt_metric(blast.get('bio_hit_at_10'))} | {fmt_metric(blast.get('bio_mrr'))} | {fmt_ms(blast.get('avg_latency_ms'))} | "
            f"{fmt_metric(vector.get('bio_hit_at_10'))} | {fmt_metric(vector.get('bio_mrr'))} | {fmt_metric(vector.get('bio_recall_at_200'))} | {fmt_ms(vector.get('avg_latency_ms'))} | "
            f"{fmt_metric(candidate.get('bio_hit_at_10'))} | {fmt_metric(candidate.get('bio_mrr'))} | {fmt_metric(candidate.get('candidate_bio_recall'))} | {fmt_ms(candidate.get('avg_latency_ms'))} | {fmt_ms(candidate.get('candidate_blast_latency_ms'))} | "
            f"{row['status']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Full-database BLAST remains the alignment-grounded reference and must stay in the verified route.",
            "- ProtT5 mean pooling provides a nontrivial dense candidate layer, but the completed 20k/100k/300k vector points remain below BLAST on biological Hit@10 and MRR.",
            "- At controlled100k, candidate-BLAST improves dense retrieval MRR over vector-only (0.7245 vs. 0.6268) and verifies candidates, but its total measured latency (839.7 ms) is slower than full BLAST at the same scale (329.2 ms).",
            "- At controlled300k, vector Recall@200 remains 0.7740 while BLAST latency rises to 796.5 ms. Candidate-BLAST improves dense retrieval MRR over vector-only (0.6835 vs. 0.5788), but its measured total latency is 1020.6 ms.",
            "- The 100k and 300k results therefore support candidate-BLAST as an evidence-quality ablation, not yet as a speed advantage in the current Chroma implementation. The candidate-BLAST-only portions are much smaller (189.2/209.6 ms), so the systems question shifts to optimized vector serving.",
            "- The stop/go rule is simple: keep candidate-BLAST as an ablation unless top-200 candidate recall remains high and verified-route latency improves at larger scale.",
            "",
            "## Pending Jobs",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["pending_jobs"])
    lines.append("")
    return "\n".join(lines)


def fmt_metric(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.4f}"


def fmt_ms(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.1f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default="reports/swissprot_scale_frontier.json")
    parser.add_argument("--output-md", default="reports/swissprot_scale_frontier.md")
    return parser.parse_args()


if __name__ == "__main__":
    main()

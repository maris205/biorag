#!/usr/bin/env python3
"""Summarize DRAG trace JSON files into an agent evidence case-study report."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_CASES = [
    {
        "case_id": "dna_igkv2_40",
        "title": "DNA/cDNA immunoglobulin module",
        "label": "IGKV2-40",
        "modality": "DNA/cDNA",
        "question": (
            "Given a local IGKV2-40 cDNA fragment, retrieve nearby sequence "
            "evidence and distinguish alignment-supported neighbors from "
            "representation-neighbor context."
        ),
        "vector": "reports/traces/dna_igkv2_40_vector_trace.json",
        "blast": "reports/traces/dna_igkv2_40_blast_trace.json",
        "hybrid": "reports/traces/dna_igkv2_40_hybrid_trace.json",
    },
    {
        "case_id": "protein_pgl",
        "title": "Protein pgl module",
        "label": "pgl",
        "modality": "Protein",
        "question": (
            "Given a protein sequence neighborhood labeled pgl, collect local "
            "module evidence and expose which links are vector-derived versus "
            "alignment-derived."
        ),
        "vector": "reports/traces/protein_pgl_vector_trace.json",
        "blast": "reports/traces/protein_pgl_blast_trace.json",
        "hybrid": "reports/traces/protein_pgl_hybrid_trace.json",
    },
    {
        "case_id": "protein_yfbr",
        "title": "Protein yfbR module",
        "label": "yfbR",
        "modality": "Protein",
        "question": (
            "Given a yfbR-like protein sequence, return a compact evidence pack "
            "that preserves both broad neighborhood context and BLAST-supported "
            "verification edges."
        ),
        "vector": "reports/traces/protein_yfbr_vector_trace.json",
        "blast": "reports/traces/protein_yfbr_blast_trace.json",
        "hybrid": "reports/traces/protein_yfbr_hybrid_trace.json",
    },
]


def main() -> None:
    args = parse_args()
    cases = [summarize_case(case, root=Path(args.root)) for case in DEFAULT_CASES]
    payload = {
        "purpose": "agent-facing evidence packaging case study",
        "llm_called": False,
        "cases": cases,
    }
    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "output_md": str(md_path), "output_json": str(json_path)}, indent=2))


def summarize_case(case: dict[str, str], *, root: Path) -> dict[str, Any]:
    routes = {}
    for route in ("vector", "blast", "hybrid"):
        routes[route] = summarize_trace_file(root / case[route])
    hybrid = routes["hybrid"]
    top_edges = representative_edges(hybrid["raw"])
    return {
        "case_id": case["case_id"],
        "title": case["title"],
        "label": case["label"],
        "modality": case["modality"],
        "question": case["question"],
        "routes": {name: strip_raw(value) for name, value in routes.items()},
        "agent_evidence_contract": {
            "instant_context": "vector_neighbor edges supply provisional neighborhood context",
            "verified_context": "blast_neighbor edges supply alignment-labeled verification evidence",
            "answer_boundary": (
                "The downstream agent may describe retrieved neighborhoods and "
                "route support, but should not infer function, mechanism, or "
                "clinical meaning unless annotation/literature evidence is present."
            ),
        },
        "hybrid_representative_edges": top_edges,
        "answer_skeleton": answer_skeleton(case, hybrid, top_edges),
    }


def summarize_trace_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary") or {}
    return {
        "path": str(path),
        "recipe": data.get("recipe"),
        "target": data.get("target"),
        "seed_count": int(data.get("seed_count") or 0),
        "avg_context_nodes": float(summary.get("avg_context_nodes") or 0.0),
        "avg_context_edges": float(summary.get("avg_context_edges") or 0.0),
        "avg_same_label_hits": float(summary.get("avg_focus_label_neighbor_hits") or 0.0),
        "relation_counts": dict(summary.get("relation_counts") or {}),
        "raw": data,
    }


def strip_raw(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "raw"}


def representative_edges(trace_summary: dict[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
    traces = trace_summary.get("traces") or []
    if not traces:
        return []
    edges = list(traces[0].get("edges") or [])
    blast_edges = [edge for edge in edges if edge.get("relation_type") == "blast_neighbor"]
    vector_edges = [edge for edge in edges if edge.get("relation_type") == "vector_neighbor"]
    selected = blast_edges[:3] + vector_edges[:3]
    return [compact_edge(edge) for edge in selected[:limit]]


def compact_edge(edge: dict[str, Any]) -> dict[str, Any]:
    labels = edge.get("target_labels") or {}
    label_text = []
    for key in ("gene_symbols", "protein_gene_names", "gene_families", "gene_biotypes"):
        if labels.get(key):
            label_text.extend(str(item) for item in labels[key][:2])
    return {
        "source": edge.get("source_name") or edge.get("source"),
        "target": edge.get("target_name") or edge.get("target"),
        "relation_type": edge.get("relation_type"),
        "confidence": edge.get("confidence"),
        "pident": edge.get("pident"),
        "bitscore": edge.get("bitscore"),
        "rank": edge.get("rank"),
        "target_labels": sorted(set(label_text)),
    }


def answer_skeleton(case: dict[str, str], hybrid: dict[str, Any], edges: list[dict[str, Any]]) -> list[str]:
    relation_counts = Counter(hybrid.get("relation_counts") or {})
    same_label = hybrid.get("avg_same_label_hits", 0.0)
    nodes = hybrid.get("avg_context_nodes", 0.0)
    edge_count = hybrid.get("avg_context_edges", 0.0)
    blast_count = relation_counts.get("blast_neighbor", 0)
    vector_count = relation_counts.get("vector_neighbor", 0)
    examples = ", ".join(
        f"{edge['target']} via {edge['relation_type']}" for edge in edges[:3] if edge.get("target")
    )
    return [
        (
            f"BioRAG-DRAG retrieved a {case['modality']} neighborhood for "
            f"{case['label']} with {nodes:.1f} average context nodes and "
            f"{edge_count:.1f} average typed edges."
        ),
        (
            f"The hybrid trace includes {blast_count} BLAST-labeled edges and "
            f"{vector_count} vector-neighbor edges across the sampled seeds."
        ),
        (
            f"Average same-label neighbor recovery is {same_label:.1f}; example "
            f"neighbors include {examples}."
        ),
        (
            "This supports an evidence-pack answer, not a mechanistic claim: "
            "the agent should cite BLAST edges for local alignment support and "
            "vector edges for broader candidate context."
        ),
    ]


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Agent Evidence Case Study",
        "",
        "This report summarizes existing DRAG trace JSON files into agent-facing evidence packs. No LLM is called; the goal is to show what a downstream biomedical agent can consume after BioRAG retrieval.",
        "",
        "## Summary Table",
        "",
        "| Case | Modality | Route | Avg nodes | Avg edges | Avg same-label hits | Relation evidence |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for case in payload["cases"]:
        for route_name in ("vector", "blast", "hybrid"):
            route = case["routes"][route_name]
            relations = "; ".join(f"{key} {value}" for key, value in route["relation_counts"].items()) or "-"
            lines.append(
                f"| `{case['label']}` | {case['modality']} | {route_name} | "
                f"{route['avg_context_nodes']:.4f} | {route['avg_context_edges']:.4f} | "
                f"{route['avg_same_label_hits']:.4f} | {relations} |"
            )
    lines.extend(["", "## Case Details", ""])
    for case in payload["cases"]:
        lines.extend(render_case(case))
    lines.extend(
        [
            "## Paper Interpretation",
            "",
            "- Vector traces provide instant neighborhood context but do not by themselves prove alignment or function.",
            "- BLAST traces provide compact alignment-labeled evidence.",
            "- Hybrid DRAG gives an agent a single evidence pack that keeps both route labels visible.",
            "- The answer boundary is explicit: without annotation, GO/pathway, domain, or literature evidence, the agent should describe retrieved sequence neighborhoods rather than infer mechanism.",
            "",
        ]
    )
    return "\n".join(lines)


def render_case(case: dict[str, Any]) -> list[str]:
    lines = [
        f"### {case['title']}",
        "",
        f"- Focus label: `{case['label']}`",
        f"- Agent-style query: {case['question']}",
        "- Evidence contract:",
        f"  - Instant context: {case['agent_evidence_contract']['instant_context']}.",
        f"  - Verified context: {case['agent_evidence_contract']['verified_context']}.",
        f"  - Boundary: {case['agent_evidence_contract']['answer_boundary']}",
        "",
        "Representative hybrid edges:",
        "",
        "| Source | Target | Relation | Confidence | pident | bitscore | Target labels |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for edge in case["hybrid_representative_edges"]:
        labels = ", ".join(edge.get("target_labels") or []) or "-"
        lines.append(
            f"| `{edge.get('source')}` | `{edge.get('target')}` | `{edge.get('relation_type')}` | "
            f"{format_number(edge.get('confidence'))} | {format_number(edge.get('pident'))} | "
            f"{format_number(edge.get('bitscore'))} | {labels} |"
        )
    lines.extend(["", "Answer skeleton:", ""])
    for item in case["answer_skeleton"]:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def format_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}".rstrip("0").rstrip(".")
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-md", default="reports/agent_evidence_case_study.md")
    parser.add_argument("--output-json", default="reports/agent_evidence_case_study.json")
    return parser.parse_args()


if __name__ == "__main__":
    main()

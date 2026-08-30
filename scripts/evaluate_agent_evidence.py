#!/usr/bin/env python3
"""Evaluate deterministic agent evidence packs on the held-out SeqLit split.

This is a retrieval/evidence-contract evaluation, not an LLM answer-quality
benchmark. It checks whether ranked protein candidates can be expanded into
typed sequence -> GO -> paper evidence and whether cited papers are relevant
under the split labels.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def main() -> None:
    args = parse_args()
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    documents = load_documents(Path(args.documents))
    go_df = compute_go_document_frequency(documents)
    methods = parse_method_files(args.methods)
    all_rows: list[dict[str, Any]] = []
    representative: dict[str, dict[str, Any]] = {}

    for method, (path, source_method) in methods.items():
        result = json.loads(path.read_text(encoding="utf-8"))
        rows = result.get("details") or []
        if source_method:
            rows = [row for row in rows if str(row.get("method")) == source_method]
        evaluated: list[dict[str, Any]] = []
        for row in rows:
            query_id = str(row.get("query_id") or row.get("id"))
            query = queries.get(query_id)
            if query is None:
                continue
            pack = build_pack(
                query,
                row,
                documents,
                candidate_k=args.candidate_k,
                paper_k=args.paper_k,
                go_df=go_df,
            )
            evaluated.append(score_pack(pack, query))
            all_rows.append({"method": method, **evaluated[-1]})
            if method not in representative and evaluated[-1]["path_complete"]:
                representative[method] = pack
        if evaluated and method not in representative:
            representative[method] = build_pack(
                queries[evaluated[0]["query_id"]],
                rows[0],
                documents,
                candidate_k=args.candidate_k,
                paper_k=args.paper_k,
                go_df=go_df,
            )

    summary = summarize_by_method(all_rows)
    output = {
        "dataset": "BioRAG-SeqLit-DAG deterministic agent evidence evaluation",
        "claim_scope": (
            "This evaluates evidence-pack construction and label-based citation support without an LLM. "
            "It is not a human or model answer-quality benchmark. Relevance follows the held-out split labels."
        ),
        "queries": len(queries),
        "methods": {name: str(path) for name, (path, _source_method) in methods.items()},
        "candidate_k": args.candidate_k,
        "paper_k": args.paper_k,
        "summary": summary,
        "representative_packs": representative,
        "details": all_rows,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path = Path(args.markdown)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(output), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "markdown": str(markdown_path), "summary": summary}, indent=2))


def build_pack(
    query: dict[str, Any],
    row: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    *,
    candidate_k: int,
    paper_k: int,
    go_df: dict[str, int] | None = None,
) -> dict[str, Any]:
    accessions = [str(item) for item in (row.get("top_accessions") or [])[: max(candidate_k, 1)]]
    papers = [str(item) for item in (row.get("top_pmids") or [])[: max(paper_k, 1)]]
    expected_accessions = {
        str(item) for item in (query.get("relevant_index_accessions") or query.get("expected_accessions") or [])
    }
    expected_go = {str(item) for item in query.get("expected_go_ids", [])}
    expected_papers = {str(item) for item in query.get("expected_pmids", [])}
    selected_papers = set(papers)
    candidates = []
    for rank, accession in enumerate(accessions, start=1):
        document = documents.get(accession, {})
        labels = dict(document.get("labels") or {})
        go_ids = {str(item) for item in labels.get("go_ids", [])}
        paper_ids = {str(item) for item in labels.get("pmids", [])} & selected_papers
        go_pmid_edges = [
            {
                "go_id": str(edge["go_id"]),
                "pmid": str(edge["pmid"]),
                "evidence_codes": sorted(str(item) for item in edge.get("evidence_codes", [])),
            }
            for edge in document.get("go_pmid_edges", [])
            if edge.get("go_id") and str(edge.get("pmid")) in selected_papers
        ]
        candidates.append(
            {
                "rank": rank,
                "accession": accession,
                "symbol": document.get("symbol"),
                "go_ids": sorted(go_ids),
                "paper_ids": sorted(paper_ids),
                "go_pmid_edges": go_pmid_edges,
                "sequence_evidence": bool(document),
                "go_bridge": sorted(go_ids & expected_go),
                "paper_bridge": sorted(paper_ids & expected_papers),
            }
        )
    graph_paths = [
        {
            "source": item["accession"],
            "relation": "annotated_with_go",
            "target": go_id,
        }
        for item in candidates
        for go_id in item["go_ids"]
    ]
    graph_paths.extend(
        {
            "source": item["accession"],
            "relation": "supported_by_paper",
            "target": pmid,
        }
        for item in candidates
        for pmid in item["paper_ids"]
    )
    graph_paths.extend(
        {
            "source": edge["go_id"],
            "relation": "supported_by_paper",
            "target": edge["pmid"],
            "via_accession": item["accession"],
            "evidence_codes": edge["evidence_codes"],
        }
        for item in candidates
        for edge in item["go_pmid_edges"]
    )
    go_claims, paper_claims = rank_graph_claims(
        candidates,
        papers,
        go_df=go_df or compute_go_document_frequency(documents),
        document_count=len(documents),
    )
    return {
        "query_id": str(query["id"]),
        "query_type": query.get("query_type"),
        "task": query.get("task"),
        "candidates": candidates,
        "papers": papers,
        "go_claims": go_claims,
        "paper_claims": paper_claims,
        "graph_paths": graph_paths,
    }


def compute_go_document_frequency(documents: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for document in documents.values():
        counts.update({str(item) for item in (document.get("labels") or {}).get("go_ids", [])})
    return dict(counts)


def rank_graph_claims(
    candidates: list[dict[str, Any]],
    papers: list[str],
    *,
    go_df: dict[str, int],
    document_count: int,
    rank_offset: float = 10.0,
    idf_power: float = 1.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank typed GO and paper claims without using query gold labels."""
    go_scores: dict[str, float] = Counter()
    go_support: dict[str, list[dict[str, Any]]] = {}
    paper_scores: dict[str, float] = Counter()
    paper_support: dict[str, list[dict[str, Any]]] = {}
    paper_rank = {str(pmid): rank for rank, pmid in enumerate(papers, start=1)}
    for item in candidates:
        rank_weight = 1.0 / (rank_offset + float(item["rank"]))
        for go_id in item["go_ids"]:
            idf = math.log((document_count + 1.0) / (go_df.get(go_id, 0) + 1.0)) + 1.0
            contribution = rank_weight * (idf**idf_power)
            go_scores[go_id] += contribution
            go_support.setdefault(go_id, []).append(
                {
                    "evidence_id": f"E{item['rank']}",
                    "accession": item["accession"],
                    "rank": item["rank"],
                    "contribution": contribution,
                }
            )
        for edge in item["go_pmid_edges"]:
            pmid = str(edge["pmid"])
            if pmid not in paper_rank:
                continue
            go_id = str(edge["go_id"])
            idf = math.log((document_count + 1.0) / (go_df.get(go_id, 0) + 1.0)) + 1.0
            contribution = rank_weight * (idf**idf_power)
            paper_scores[pmid] += contribution
            paper_support.setdefault(pmid, []).append(
                {
                    "evidence_id": f"E{item['rank']}",
                    "accession": item["accession"],
                    "go_id": go_id,
                    "evidence_codes": edge["evidence_codes"],
                    "contribution": contribution,
                }
            )
    go_claims = []
    for go_id, score in go_scores.items():
        support = sorted(go_support[go_id], key=lambda row: (-row["contribution"], row["rank"], row["accession"]))
        go_claims.append(
            {
                "go_id": go_id,
                "score": score,
                "document_frequency": go_df.get(go_id, 0),
                "evidence_ids": [row["evidence_id"] for row in support],
                "accessions": [row["accession"] for row in support],
            }
        )
    go_claims.sort(key=lambda row: (-row["score"], row["document_frequency"], row["go_id"]))
    paper_claims = []
    for pmid, score in paper_scores.items():
        support = sorted(
            paper_support[pmid],
            key=lambda row: (-row["contribution"], row["evidence_id"], row["go_id"]),
        )
        paper_claims.append(
            {
                "pmid": pmid,
                "score": score,
                "paper_rank": paper_rank[pmid],
                "go_ids": sorted({row["go_id"] for row in support}),
                "evidence_ids": [row["evidence_id"] for row in support],
                "accessions": [row["accession"] for row in support],
            }
        )
    paper_claims.sort(key=lambda row: (-row["score"], row["paper_rank"], row["pmid"]))
    return go_claims, paper_claims


def score_pack(pack: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
    accessions = [item["accession"] for item in pack["candidates"]]
    papers = pack["papers"]
    expected_accessions = {
        str(item) for item in (query.get("relevant_index_accessions") or query.get("expected_accessions") or [])
    }
    expected_go = {str(item) for item in query.get("expected_go_ids", [])}
    expected_papers = {str(item) for item in query.get("expected_pmids", [])}
    retrieved_accessions = set(accessions)
    retrieved_papers = set(papers)
    go_bridged = {go for item in pack["candidates"] for go in item["go_bridge"]}
    paper_bridged = {pmid for item in pack["candidates"] for pmid in item["paper_bridge"]}
    strict_edges = {
        (edge["go_id"], edge["pmid"])
        for item in pack["candidates"]
        for edge in item.get("go_pmid_edges", [])
    }
    strict_expected_edges = {
        (go_id, pmid)
        for go_id in expected_go
        for pmid in expected_papers
    }
    typed_candidates = sum(bool(item["go_ids"] or item["paper_ids"]) for item in pack["candidates"])
    first_relevant = next((i for i, item in enumerate(accessions, start=1) if item in expected_accessions), None)
    citation_precision = len(retrieved_papers & expected_papers) / len(retrieved_papers) if retrieved_papers else 0.0
    citation_recall = len(retrieved_papers & expected_papers) / len(expected_papers) if expected_papers else 0.0
    return {
        "query_id": pack["query_id"],
        "candidate_count": len(accessions),
        "paper_count": len(papers),
        "graph_path_count": len(pack["graph_paths"]),
        "typed_candidate_rate": typed_candidates / len(accessions) if accessions else 0.0,
        "candidate_recall": len(retrieved_accessions & expected_accessions) / len(expected_accessions) if expected_accessions else 0.0,
        "candidate_hit": bool(retrieved_accessions & expected_accessions),
        "first_relevant_rank": first_relevant,
        "go_bridge_recall": len(go_bridged & expected_go) / len(expected_go) if expected_go else 0.0,
        "go_bridge_hit": bool(go_bridged & expected_go),
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "citation_hit": bool(retrieved_papers & expected_papers),
        "paper_path_support": len(paper_bridged & expected_papers) / len(expected_papers) if expected_papers else 0.0,
        "path_complete": bool(retrieved_accessions & expected_accessions and retrieved_papers & expected_papers),
        "strict_typed_path": bool(strict_edges & strict_expected_edges),
        "pack_chars": len(json.dumps(pack, ensure_ascii=False, separators=(",", ":"))),
    }


def summarize_by_method(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    metrics = (
        "typed_candidate_rate",
        "candidate_recall",
        "candidate_hit",
        "go_bridge_recall",
        "go_bridge_hit",
        "citation_precision",
        "citation_recall",
        "citation_hit",
        "paper_path_support",
        "path_complete",
        "strict_typed_path",
        "pack_chars",
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["method"]), []).append(row)
    return {
        method: {
            metric: sum(float(row[metric]) for row in method_rows) / len(method_rows)
            for metric in metrics
        }
        for method, method_rows in sorted(grouped.items())
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Evidence Evaluation",
        "",
        result["claim_scope"],
        "",
        f"Queries: `{result['queries']}`; candidate K: `{result['candidate_k']}`; paper K: `{result['paper_k']}`.",
        "",
        "| Method | Typed candidate rate | Candidate hit | GO bridge hit | Citation precision | Citation recall | Complete path | Strict typed path | Pack chars |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, values in result["summary"].items():
        lines.append(
            f"| {method} | {values['typed_candidate_rate']:.3f} | {values['candidate_hit']:.3f} | "
            f"{values['go_bridge_hit']:.3f} | {values['citation_precision']:.3f} | "
            f"{values['citation_recall']:.3f} | {values['path_complete']:.3f} | "
            f"{values['strict_typed_path']:.3f} | {values['pack_chars']:.0f} |"
        )
    lines.extend(
        [
            "",
            "## Metric Definitions",
            "",
            "- `Typed candidate rate`: fraction of ranked candidates with local GO or paper metadata.",
            "- `GO bridge hit`: at least one retrieved candidate carries a gold held-out GO term.",
            "- `Citation precision/recall`: retrieved PMID support against the query's held-out expected PMIDs.",
            "- `Complete path`: a ranked candidate and a ranked expected paper are both present.",
            "- `Strict typed path`: a visible candidate contains an expected GO-to-PMID evidence edge under the paper budget.",
            "- `Pack chars`: compact serialized pack size, a proxy for context budget rather than answer quality.",
            "",
            "The evaluation measures auditable evidence construction. It does not claim that a downstream agent's generated answer is correct without a separate human or model-judged QA evaluation.",
            "",
        ]
    )
    return "\n".join(lines)


def load_documents(path: Path) -> dict[str, dict[str, Any]]:
    """Merge protein and evidence-path rows into one typed record per accession."""
    documents: dict[str, dict[str, Any]] = {}
    seen_edges: dict[str, set[tuple[str, str, tuple[str, ...]]]] = {}
    for row in read_jsonl(path):
        accession = row.get("accession")
        if not accession:
            continue
        accession = str(accession)
        document = documents.setdefault(
            accession,
            {
                "accession": accession,
                "symbol": None,
                "name": None,
                "organism": None,
                "labels": {"go_ids": [], "pmids": []},
                "go_pmid_edges": [],
            },
        )
        for key in ("symbol", "name", "organism"):
            if row.get(key) and (document.get(key) is None or row.get("modality") == "protein_sequence"):
                document[key] = row[key]
        labels = dict(row.get("labels") or {})
        document["labels"]["go_ids"] = sorted(
            set(document["labels"]["go_ids"]) | {str(item) for item in labels.get("go_ids", [])}
        )
        document["labels"]["pmids"] = sorted(
            set(document["labels"]["pmids"]) | {str(item) for item in labels.get("pmids", [])}
        )
        if row.get("partition") != "seq_lit_dag/evidence_path":
            continue
        evidence_codes = tuple(sorted(str(item) for item in labels.get("evidence_codes", [])))
        edge_keys = seen_edges.setdefault(accession, set())
        for go_id in labels.get("go_ids", []):
            for pmid in labels.get("pmids", []):
                edge_key = (str(go_id), str(pmid), evidence_codes)
                if edge_key in edge_keys:
                    continue
                edge_keys.add(edge_key)
                document["go_pmid_edges"].append(
                    {"go_id": str(go_id), "pmid": str(pmid), "evidence_codes": list(evidence_codes)}
                )
    return documents


def parse_method_files(values: list[str]) -> dict[str, tuple[Path, str | None]]:
    methods: dict[str, tuple[Path, str | None]] = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            raise SystemExit(f"Method must use NAME=PATH, got: {value}")
        path_value, method_separator, source_method = path.rpartition("#")
        if method_separator and path_value and source_method:
            methods[name] = (Path(path_value), source_method)
        else:
            methods[name] = (Path(path), None)
    return methods


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deterministic SeqLit agent evidence packs")
    root = "data/seq_lit_dag_function_heldout_2k"
    parser.add_argument("--queries", default=f"{root}/queries.jsonl")
    parser.add_argument("--documents", default=f"{root}/index_documents.jsonl")
    parser.add_argument("--methods", nargs="+", required=True, help="NAME=JSON result file")
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--paper-k", type=int, default=50)
    parser.add_argument("--output", default="reports/results/agent_evidence_eval.json")
    parser.add_argument("--markdown", default="reports/agent_evidence_eval.md")
    return parser.parse_args()


if __name__ == "__main__":
    main()

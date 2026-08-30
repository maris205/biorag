#!/usr/bin/env python3
"""Run an evidence-constrained agent QA baseline on SeqLit-DAG packs.

The baseline is intentionally extractive: it can only state GO IDs and PMIDs
that occur in the retrieved evidence pack, and it abstains on unsupported
mechanistic questions. This gives a reproducible lower-level agent measure
before introducing a generative model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_agent_evidence import (
    build_pack,
    compute_go_document_frequency,
    load_documents,
    read_jsonl,
    score_pack,
)


def main() -> None:
    args = parse_args()
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    documents = load_documents(Path(args.documents))
    go_df = compute_go_document_frequency(documents)
    result = json.loads(Path(args.input).read_text(encoding="utf-8"))
    method_rows = [
        row for row in result.get("details", [])
        if args.method == "all" or str(row.get("method")) == args.method
    ]
    if args.limit:
        method_rows = method_rows[: args.limit]

    rows: list[dict[str, Any]] = []
    dumped_packs: list[dict[str, Any]] = []
    for method_row in method_rows:
        query = queries.get(str(method_row.get("query_id")))
        if query is None:
            continue
        pack = build_pack(
            query,
            method_row,
            documents,
            candidate_k=args.candidate_k,
            paper_k=args.paper_k,
            go_df=go_df,
        )
        retrieval_score = score_pack(pack, query)
        for qa_type in ("function", "literature", "mechanism"):
            answer = answer_question(pack, qa_type=qa_type, selector=args.selector)
            rows.append(score_answer(query, pack, qa_type=qa_type, answer=answer))
        if args.dump_packs:
            dumped_packs.append({"retrieval": retrieval_score, "pack": pack})

    if args.dump_packs:
        dump_path = Path(args.dump_packs)
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in dumped_packs),
            encoding="utf-8",
        )

    output = {
        "dataset": "BioRAG-SeqLit-DAG held-out agent QA benchmark",
        "claim_scope": (
            "This is an extractive evidence-constrained baseline. It measures answer coverage and citation support, "
            "not open-ended LLM generation quality. Mechanism questions are designed to test evidence-aware abstention."
        ),
        "source_result": str(args.input),
        "method": args.method,
        "query_count": len({row["query_id"] for row in rows}),
        "qa_count": len(rows),
        "candidate_k": args.candidate_k,
        "paper_k": args.paper_k,
        "selector": args.selector,
        "summary": summarize(rows),
        "details": rows,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path = Path(args.markdown)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(output), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "markdown": str(markdown_path), "summary": output["summary"]}, indent=2))


def answer_question(pack: dict[str, Any], *, qa_type: str, selector: str = "rank_first") -> dict[str, Any]:
    candidates = pack["candidates"]
    if qa_type == "mechanism":
        return {
            "text": "The retrieved sequence evidence is insufficient to infer a molecular mechanism. Additional curated functional or experimental evidence is required.",
            "go_ids": [],
            "pmids": [],
            "citations": [],
            "abstained": True,
        }
    if qa_type == "function":
        if selector == "graph_idf":
            claims = pack.get("go_claims", [])[:5]
            go_ids = [str(item["go_id"]) for item in claims]
            citations = [
                {
                    "type": "candidate",
                    "id": item["evidence_ids"][0],
                    "accession": item["accessions"][0],
                    "go_id": item["go_id"],
                }
                for item in claims
                if item.get("evidence_ids") and item.get("accessions")
            ]
            text = (
                "Graph-ranked candidate annotations include " + ", ".join(go_ids) + "."
                if go_ids
                else "No GO annotation was retrieved for the top candidates."
            )
            return {"text": text, "go_ids": go_ids, "pmids": [], "citations": citations, "abstained": not bool(go_ids)}
        go_ids: list[str] = []
        citations: list[dict[str, Any]] = []
        for item in candidates[:10]:
            for go_id in item["go_ids"]:
                if go_id in go_ids:
                    continue
                go_ids.append(go_id)
                citations.append({"type": "candidate", "id": f"E{item['rank']}", "accession": item["accession"], "go_id": go_id})
                if len(go_ids) >= 5:
                    break
            if len(go_ids) >= 5:
                break
        text = (
            "Retrieved candidate annotations include " + ", ".join(go_ids) + "."
            if go_ids
            else "No GO annotation was retrieved for the top candidates."
        )
        return {"text": text, "go_ids": go_ids, "pmids": [], "citations": citations, "abstained": not bool(go_ids)}
    if selector == "graph_idf":
        claims = pack.get("paper_claims", [])[:10]
        pmids = [str(item["pmid"]) for item in claims]
        citations = []
        for item in claims:
            p_id = f"P{item['paper_rank']}"
            support_accession = item["accessions"][0] if item.get("accessions") else None
            citations.append({"type": "paper", "id": p_id, "pmid": item["pmid"], "accession": support_accession})
        text = "Graph-ranked literature evidence includes PMIDs " + ", ".join(pmids) + "." if pmids else "No supported paper was retrieved."
        return {"text": text, "go_ids": [], "pmids": pmids, "citations": citations, "abstained": not bool(pmids)}
    pmids: list[str] = []
    citations = []
    for pmid in pack["papers"]:
        pmid = str(pmid)
        if pmid in pmids:
            continue
        support = next((item for item in candidates if pmid in item["paper_ids"]), None)
        if support is None:
            continue
        pmids.append(pmid)
        citations.append({"type": "paper", "id": f"P{len(pmids)}", "pmid": pmid, "accession": support["accession"]})
        if len(pmids) >= 10:
            break
    text = "Retrieved literature evidence includes PMIDs " + ", ".join(pmids) + "." if pmids else "No supported paper was retrieved."
    return {"text": text, "go_ids": [], "pmids": pmids, "citations": citations, "abstained": not bool(pmids)}


def score_answer(query: dict[str, Any], pack: dict[str, Any], *, qa_type: str, answer: dict[str, Any]) -> dict[str, Any]:
    expected_go = {str(item) for item in query.get("expected_go_ids", [])}
    expected_pmids = {str(item) for item in query.get("expected_pmids", [])}
    predicted_go = set(answer["go_ids"])
    predicted_pmids = set(answer["pmids"])
    if qa_type == "function":
        precision, recall, f1 = set_f1(predicted_go, expected_go)
    elif qa_type == "literature":
        precision, recall, f1 = set_f1(predicted_pmids, expected_pmids)
    else:
        precision = recall = f1 = 0.0
    supported = 0
    for citation in answer["citations"]:
        if citation["type"] == "candidate":
            candidate = next((item for item in pack["candidates"] if item["accession"] == citation["accession"]), None)
            supported += int(candidate is not None and citation["go_id"] in candidate["go_ids"])
        else:
            candidate = next((item for item in pack["candidates"] if item["accession"] == citation["accession"]), None)
            supported += int(candidate is not None and citation["pmid"] in candidate["paper_ids"])
    citation_count = len(answer["citations"])
    return {
        "query_id": str(query["id"]),
        "qa_type": qa_type,
        "answer": answer["text"],
        "predicted_go_ids": sorted(predicted_go),
        "predicted_pmids": sorted(predicted_pmids),
        "citation_count": citation_count,
        "citation_support_rate": supported / citation_count if citation_count else 1.0 if qa_type == "mechanism" else 0.0,
        "answer_precision": precision,
        "answer_recall": recall,
        "answer_f1": f1,
        "abstained": bool(answer["abstained"]),
        "abstention_correct": bool(qa_type == "mechanism" and answer["abstained"]),
    }


def set_f1(predicted: set[str], expected: set[str]) -> tuple[float, float, float]:
    if not predicted:
        return 0.0, 0.0, 0.0
    precision = len(predicted & expected) / len(predicted)
    recall = len(predicted & expected) / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    metrics = ("answer_precision", "answer_recall", "answer_f1", "citation_support_rate", "abstention_correct")
    result = {}
    for qa_type in ("function", "literature", "mechanism"):
        selected = [row for row in rows if row["qa_type"] == qa_type]
        result[qa_type] = {
            metric: sum(float(row[metric]) for row in selected) / len(selected) if selected else 0.0
            for metric in metrics
        }
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Agent QA Evaluation",
        "",
        result["claim_scope"],
        "",
        f"Method: `{result['method']}`; selector: `{result['selector']}`; queries: `{result['query_count']}`; candidate K: `{result['candidate_k']}`; paper K: `{result['paper_k']}`.",
        "",
        "| QA type | Answer precision | Answer recall | Answer F1 | Citation support | Correct abstention |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for qa_type, values in result["summary"].items():
        lines.append(
            f"| {qa_type} | {values['answer_precision']:.3f} | {values['answer_recall']:.3f} | "
            f"{values['answer_f1']:.3f} | {values['citation_support_rate']:.3f} | {values['abstention_correct']:.3f} |"
        )
    lines.extend(
        [
            "",
            "The extractive baseline is deliberately conservative. It cannot hallucinate a GO term or PMID because every answer item is constructed from the retrieved pack and every citation is checked against a candidate-to-annotation or candidate-to-paper edge.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate an evidence-constrained SeqLit agent QA baseline")
    root = "data/seq_lit_dag_function_heldout_2k"
    parser.add_argument("--input", required=True, help="Result JSON containing details rows")
    parser.add_argument("--method", required=True, help="Method name in the result file")
    parser.add_argument("--queries", default=f"{root}/queries.jsonl")
    parser.add_argument("--documents", default=f"{root}/index_documents.jsonl")
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--paper-k", type=int, default=20)
    parser.add_argument("--selector", choices=("rank_first", "graph_idf"), default="rank_first")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="reports/results/agent_qa_prott5_blast.json")
    parser.add_argument("--markdown", default="reports/agent_qa_prott5_blast.md")
    parser.add_argument("--dump-packs", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()

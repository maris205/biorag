#!/usr/bin/env python3
"""Score generated SeqLit agent answers for correctness and grounding."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def main() -> None:
    args = parse_args()
    generated = json.loads(Path(args.input).read_text(encoding="utf-8"))
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    packs = {str(row["pack"]["query_id"]): row["pack"] for row in read_jsonl(Path(args.packs))}
    rows = []
    for output in generated.get("outputs", []):
        query_id = str(output["query_id"])
        if query_id not in queries or query_id not in packs:
            continue
        rows.append(score_output(output, queries[query_id], packs[query_id]))
    result = {
        "dataset": "BioRAG-SeqLit-DAG generated agent QA scoring",
        "claim_scope": (
            "String-level GO/PMID correctness and graph-edge citation entailment are measured automatically. "
            "This does not replace expert judgment of free-form biomedical statements."
        ),
        "source": args.input,
        "query_count": len({row["query_id"] for row in rows}),
        "answer_count": len(rows),
        "summary": summarize(rows),
        "details": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"output": str(output), "markdown": str(markdown), "summary": result["summary"]}, indent=2))


def score_output(output: dict[str, Any], query: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    qa_type = str(output["qa_type"])
    answer = str(output.get("answer") or "")
    predicted_go = set(re.findall(r"GO:\d{7}", answer))
    predicted_pmids = extract_pmids(answer)
    prompt = str(output.get("prompt") or "")
    prompt_evidence = prompt.partition("Query:")[0]
    ordered_prompt_go = ordered_unique(re.findall(r"GO:\d{7}", prompt_evidence))
    ordered_prompt_pmids = ordered_unique(re.findall(r"(?i)PMID\s*[:=]?\s*(\d{7,8})", prompt_evidence))
    prompt_go = set(ordered_prompt_go)
    prompt_pmids = set(ordered_prompt_pmids)
    output_k_match = re.search(r"(?:Return at most|Copy the first) (\d+)", prompt)
    output_k = int(output_k_match.group(1)) if output_k_match else 5
    citations = {
        f"[{kind}{rank}]"
        for kind, rank in re.findall(r"\[?([EPGL])(\d+)\]?", citation_region(answer))
    }
    expected_go = {str(item) for item in query.get("expected_go_ids", [])}
    expected_pmids = {str(item) for item in query.get("expected_pmids", [])}
    e_map = {
        f"[E{item['rank']}]": {"go_ids": set(item["go_ids"]), "pmids": set(item["paper_ids"])}
        for item in pack["candidates"]
    }
    p_map = {f"[P{rank}]": str(pmid) for rank, pmid in enumerate(pack["papers"], start=1)}
    g_map = {
        f"[G{rank}]": str(claim["go_id"])
        for rank, claim in enumerate(pack.get("go_claims", []), start=1)
    }
    l_map = {
        f"[L{rank}]": str(claim["pmid"])
        for rank, claim in enumerate(pack.get("paper_claims", []), start=1)
    }
    valid_ids = set(e_map) | set(p_map) | set(g_map) | set(l_map)
    cited_go = {go for citation in citations & set(e_map) for go in e_map[citation]["go_ids"]}
    cited_go.update(g_map[citation] for citation in citations & set(g_map))
    cited_pmids = {pmid for citation in citations & set(e_map) for pmid in e_map[citation]["pmids"]}
    cited_pmids.update(p_map[citation] for citation in citations & set(p_map))
    cited_pmids.update(l_map[citation] for citation in citations & set(l_map))
    pack_go = {go for item in pack["candidates"] for go in item["go_ids"]}
    pack_pmids = set(pack["papers"])
    pack_pmids.update(pmid for item in pack["candidates"] for pmid in item["paper_ids"])
    if qa_type == "function":
        precision, recall, f1 = set_f1(predicted_go, expected_go)
        retrievable_precision, retrievable_recall, retrievable_f1 = set_f1(predicted_go, expected_go & prompt_go)
        _, _, evidence_selection_f1 = set_f1(predicted_go, set(ordered_prompt_go[:output_k]))
        prompt_gold_recall = len(expected_go & prompt_go) / len(expected_go) if expected_go else 0.0
        claim_support = (
            1.0 if not predicted_go and is_abstention(answer) else fraction_supported(predicted_go, cited_go)
        )
        hallucination = fraction_outside(predicted_go, pack_go)
        evidence_aware_abstention = float(bool(not prompt_go and is_abstention(answer)))
    elif qa_type == "literature":
        precision, recall, f1 = set_f1(predicted_pmids, expected_pmids)
        retrievable_precision, retrievable_recall, retrievable_f1 = set_f1(
            predicted_pmids, expected_pmids & prompt_pmids
        )
        _, _, evidence_selection_f1 = set_f1(predicted_pmids, set(ordered_prompt_pmids[:output_k]))
        prompt_gold_recall = len(expected_pmids & prompt_pmids) / len(expected_pmids) if expected_pmids else 0.0
        claim_support = (
            1.0 if not predicted_pmids and is_abstention(answer) else fraction_supported(predicted_pmids, cited_pmids)
        )
        hallucination = fraction_outside(predicted_pmids, pack_pmids)
        evidence_aware_abstention = float(bool(not prompt_pmids and is_abstention(answer)))
    else:
        precision = recall = f1 = 0.0
        retrievable_precision = retrievable_recall = retrievable_f1 = 0.0
        evidence_selection_f1 = 0.0
        prompt_gold_recall = 0.0
        claim_support = 1.0 if is_abstention(answer) and not predicted_go and not predicted_pmids else 0.0
        hallucination = fraction_outside(predicted_go, pack_go) + fraction_outside(predicted_pmids, pack_pmids)
        hallucination = min(hallucination, 1.0)
        evidence_aware_abstention = float(bool(is_abstention(answer)))
    format_ok = bool(re.fullmatch(r"ANSWER:[^\n]*\nCITATIONS:[^\n]*\s*", answer))
    citation_text = citation_region(answer)
    bare_citations = re.findall(r"(?<!\[)\b[EPGL]\d+\b(?!\])", citation_text)
    citation_syntax_ok = bool(is_abstention(answer) or (citations and not bare_citations))
    return {
        "query_id": output["query_id"],
        "qa_type": qa_type,
        "answer": answer,
        "predicted_go_ids": sorted(predicted_go),
        "predicted_pmids": sorted(predicted_pmids),
        "citation_ids": sorted(citations),
        "answer_precision": precision,
        "answer_recall": recall,
        "answer_f1": f1,
        "retrievable_answer_precision": retrievable_precision,
        "retrievable_answer_recall": retrievable_recall,
        "retrievable_answer_f1": retrievable_f1,
        "prompt_gold_recall": prompt_gold_recall,
        "evidence_selection_f1": evidence_selection_f1,
        "citation_validity": len(citations & valid_ids) / len(citations) if citations else 1.0 if is_abstention(answer) else 0.0,
        "citation_entailment": claim_support,
        "pack_hallucination_rate": hallucination,
        "abstention_correct": bool(qa_type == "mechanism" and is_abstention(answer)),
        "evidence_aware_abstention": evidence_aware_abstention,
        "format_compliance": format_ok,
        "citation_syntax_compliance": citation_syntax_ok,
    }


def citation_region(answer: str) -> str:
    match = re.search(r"(?ms)^CITATIONS:\s*(.*)$", answer)
    return match.group(1) if match else answer


def is_abstention(answer: str) -> bool:
    lowered = answer.lower()
    return "insufficient_evidence" in lowered or "insufficient evidence" in lowered or "cannot establish" in lowered


def set_f1(predicted: set[str], expected: set[str]) -> tuple[float, float, float]:
    if not predicted:
        return 0.0, 0.0, 0.0
    precision = len(predicted & expected) / len(predicted)
    recall = len(predicted & expected) / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def fraction_supported(claims: set[str], support: set[str]) -> float:
    return len(claims & support) / len(claims) if claims else 0.0


def fraction_outside(claims: set[str], evidence: set[str]) -> float:
    return len(claims - evidence) / len(claims) if claims else 0.0


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    metrics = (
        "answer_precision",
        "answer_recall",
        "answer_f1",
        "retrievable_answer_f1",
        "prompt_gold_recall",
        "evidence_selection_f1",
        "citation_validity",
        "citation_entailment",
        "pack_hallucination_rate",
        "abstention_correct",
        "evidence_aware_abstention",
        "format_compliance",
        "citation_syntax_compliance",
    )
    summary = {}
    for qa_type in ("function", "literature", "mechanism"):
        selected = [row for row in rows if row["qa_type"] == qa_type]
        summary[qa_type] = {
            metric: sum(float(row[metric]) for row in selected) / len(selected) if selected else 0.0
            for metric in metrics
        }
    return summary


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Generated Agent QA Scoring",
        "",
        result["claim_scope"],
        "",
        f"Queries: `{result['query_count']}`; answers: `{result['answer_count']}`.",
        "",
        "| QA type | End-to-end F1 | Prompt gold recall | Retrievable F1 | Evidence-selection F1 | Citation validity | Citation entailment | Pack hallucination | Evidence-aware abstention | Correct mechanism abstention | Format | Citation syntax |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for qa_type, row in result["summary"].items():
        lines.append(
            f"| {qa_type} | {row['answer_f1']:.3f} | {row['prompt_gold_recall']:.3f} | "
            f"{row['retrievable_answer_f1']:.3f} | {row['evidence_selection_f1']:.3f} | "
            f"{row['citation_validity']:.3f} | "
            f"{row['citation_entailment']:.3f} | {row['pack_hallucination_rate']:.3f} | "
            f"{row['evidence_aware_abstention']:.3f} | {row['abstention_correct']:.3f} | "
            f"{row['format_compliance']:.3f} | "
            f"{row['citation_syntax_compliance']:.3f} |"
        )
    lines.extend(["", "Only structured identifier claims are automatically judged; narrative biomedical correctness remains outside this pilot.", ""])
    return "\n".join(lines)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def extract_pmids(text: str) -> set[str]:
    return set(re.findall(r"(?i)PMID\s*[:=]?\s*(\d{7,8})", text))


def ordered_unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score generated SeqLit agent QA answers")
    parser.add_argument("--input", required=True)
    parser.add_argument("--packs", default="reports/results/agent_qa_prott5_blast_packs.jsonl")
    parser.add_argument("--queries", default="data/seq_lit_dag_function_heldout_2k/queries.jsonl")
    parser.add_argument("--output", default="reports/results/agent_qa_generated_score.json")
    parser.add_argument("--markdown", default="reports/agent_qa_generated_score.md")
    return parser.parse_args()


if __name__ == "__main__":
    main()

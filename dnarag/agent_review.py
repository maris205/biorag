"""Utilities for blinded, free-form SeqLit Agent evaluation."""
from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict
from typing import Any, Iterable


REVIEW_ROUTES = (
    "no_retrieval",
    "r2r_text_only",
    "sequence_vector",
    "combined_blast_vector",
    "combined_blast_vector_dag",
)
REQUIRED_SECTIONS = (
    "FUNCTION HYPOTHESIS:",
    "EVIDENCE:",
    "LITERATURE:",
    "UNCERTAINTY:",
)
_CITATION_RE = re.compile(r"\[([CGP]\d+)\]")
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
_GO_RE = re.compile(r"GO:\d{7}")
_PMID_RE = re.compile(r"PMID\s*:\s*(\d+)", re.IGNORECASE)
_GO_CITATION_RE = re.compile(r"(GO:\d{7})(?:(?!GO:).){0,120}?\[(G\d+)\]", re.DOTALL)
_PMID_CITATION_RE = re.compile(r"PMID\s*:\s*(\d+)(?:(?!PMID).){0,100}?\[(P\d+)\]", re.IGNORECASE | re.DOTALL)
_OVERCLAIM_RE = re.compile(
    r"\b(proves?|proven|establishes?|confirmed|definitively|demonstrates? that the query|causes?)\b",
    re.IGNORECASE,
)
_CALIBRATION_RE = re.compile(
    r"\b(hypoth(?:esis|eses)|candidate|indirect|suggests?|consistent with|uncertain|"
    r"insufficient|requires? validation|not establish|cannot establish|cannot confirm|may|might)\b",
    re.IGNORECASE,
)
_ABSTENTION_RE = re.compile(
    r"\b(insufficient|abstain|no functional hypothes(?:is|es)|cannot propose|"
    r"no (?:retrieved |supporting )?evidence|absence of retrieved evidence|"
    r"cannot infer|cannot be proposed|remains uncharacterized)\b",
    re.IGNORECASE,
)


def query_stratum(query: dict[str, Any]) -> str:
    """Assign one of three preregistered evidence-density strata."""
    go_count = len({str(item) for item in query.get("expected_go_ids", [])})
    pmid_count = len({str(item) for item in query.get("expected_pmids", [])})
    if go_count > 1:
        return "multi_go"
    if pmid_count <= 3:
        return "single_go_sparse_literature"
    return "single_go_dense_literature"


def select_review_queries(
    queries: dict[str, dict[str, Any]],
    eligible_ids: Iterable[str],
    *,
    per_stratum: int = 10,
    seed: int = 20260831,
) -> list[dict[str, str]]:
    """Select a deterministic, outcome-independent stratified review sample."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for query_id in sorted({str(item) for item in eligible_ids}):
        if query_id not in queries:
            raise KeyError(f"Unknown review query ID: {query_id}")
        grouped[query_stratum(queries[query_id])].append(query_id)
    expected = {
        "single_go_sparse_literature",
        "single_go_dense_literature",
        "multi_go",
    }
    if set(grouped) != expected:
        raise ValueError(f"Review strata mismatch: {sorted(grouped)}")
    selected: list[dict[str, str]] = []
    for stratum in sorted(expected):
        members = list(grouped[stratum])
        random.Random(f"{seed}:{stratum}").shuffle(members)
        if len(members) < per_stratum:
            raise ValueError(f"Stratum {stratum} has {len(members)} rows; need {per_stratum}")
        selected.extend({"query_id": query_id, "stratum": stratum} for query_id in members[:per_stratum])
    selected.sort(key=lambda row: stable_digest(f"{seed}:{row['query_id']}"))
    return selected


def evidence_pmids(pack: dict[str, Any], *, evidence_mode: str, candidate_k: int = 5, paper_k: int = 5) -> list[str]:
    candidates = list(pack.get("candidates", []))[:candidate_k]
    supported = {
        str(pmid)
        for candidate in candidates
        for pmid in candidate.get("paper_ids", [])
    }
    if evidence_mode == "graph_idf":
        ordered = [str(item["pmid"]) for item in pack.get("paper_claims", [])]
    else:
        ordered = [str(pmid) for pmid in pack.get("papers", []) if str(pmid) in supported]
        if not ordered:
            ordered = [
                str(pmid)
                for candidate in candidates
                for pmid in candidate.get("paper_ids", [])
            ]
    return unique_in_order(ordered)[:paper_k]


def build_freeform_prompt(
    query: dict[str, Any],
    pack: dict[str, Any],
    *,
    evidence_mode: str,
    go_names: dict[str, str] | None = None,
    pubmed_metadata: dict[str, dict[str, Any]] | None = None,
    candidate_k: int = 5,
    go_k: int = 3,
    paper_k: int = 3,
) -> dict[str, Any]:
    """Build a route-normalized evidence note prompt and auditable registry."""
    go_names = go_names or {}
    pubmed_metadata = pubmed_metadata or {}
    candidates = list(pack.get("candidates", []))[:candidate_k]
    registry: dict[str, dict[str, Any]] = {}
    lines: list[str] = []
    candidate_labels: dict[str, str] = {}
    for rank, candidate in enumerate(candidates, start=1):
        label = f"C{rank}"
        accession = str(candidate.get("accession") or "unknown")
        symbol = str(candidate.get("symbol") or "unknown")
        candidate_labels[accession] = label
        registry[label] = {
            "kind": "candidate",
            "accession": accession,
            "symbol": symbol,
        }
        lines.append(f"[{label}] candidate accession={accession}; symbol={symbol}; indirect retrieved sequence neighbor.")

    go_records = _rank_go_records(
        pack,
        candidates=candidates,
        evidence_mode=evidence_mode,
        candidate_labels=candidate_labels,
    )[:go_k]
    for rank, record in enumerate(go_records, start=1):
        label = f"G{rank}"
        go_id = record["go_id"]
        name = go_names.get(go_id, "name unavailable")
        support = ",".join(record["candidate_labels"]) or "none"
        codes = ",".join(record["evidence_codes"]) or "not supplied"
        pmids = ",".join(record["pmids"]) or "none"
        registry[label] = {"kind": "go", "go_name": name, **record}
        lines.append(
            f"[{label}] candidates={support} -> {go_id} ({name}); "
            f"GOA evidence codes={codes}; linked PMIDs={pmids}."
        )

    paper_records = _rank_paper_records(
        pack,
        candidates=candidates,
        evidence_mode=evidence_mode,
        candidate_labels=candidate_labels,
        paper_k=paper_k,
    )
    for rank, record in enumerate(paper_records, start=1):
        label = f"P{rank}"
        pmid = record["pmid"]
        metadata = dict(pubmed_metadata.get(pmid) or {})
        title = clean_text(metadata.get("title")) or "title unavailable"
        year = clean_text(metadata.get("year")) or "year unavailable"
        abstract = truncate(clean_text(metadata.get("abstract")), 240)
        registry[label] = {"kind": "paper", **record, "title": title, "year": year}
        suffix = f"; abstract={abstract}" if abstract else ""
        lines.append(
            f"[{label}] PMID:{pmid}; title={title}; year={year}; "
            f"candidate support={','.join(record['candidate_labels']) or 'none'}; "
            f"GO links={','.join(record['go_ids']) or 'none'}{suffix}."
        )

    if not lines:
        lines.append("No retrieved sequence, function, or literature evidence is available.")
    sequence = clean_text(query.get("query"))
    prompt = "\n".join(
        [
            "Held-out query (accession masked):",
            f"protein sequence={sequence}",
            "",
            "Retrieved evidence:",
            *lines,
            "",
            "Write a concise evidence note for a biomedical scientist.",
            "The entire answer must be at most 150 words, with one line per required section.",
            "Propose at most two candidate functions and at most three papers for follow-up; do not summarize unused evidence.",
            "Every functional statement must include an explicit GO ID and cite its [G#] evidence.",
            "Every literature statement must cite its [P#] evidence.",
            "Use [C#] when naming a supporting candidate protein.",
            "Do not use a GO ID unless it appears in a [G#] line, even when a paper line mentions that GO ID.",
            "Treat all function transfer as an indirect retrieval-derived hypothesis, not validation of the query protein.",
            "Do not infer a molecular mechanism, disease association, or experimental conclusion not explicitly supplied.",
            "When evidence is absent or weak, abstain or state the limitation clearly.",
            "Use only identifiers and citations shown above.",
            "Respond with exactly these four section labels:",
            "FUNCTION HYPOTHESIS:",
            "EVIDENCE:",
            "LITERATURE:",
            "UNCERTAINTY:",
        ]
    )
    return {
        "prompt": prompt,
        "evidence_lines": lines,
        "evidence_registry": registry,
        "available_function_go_ids": sorted(
            {str(item["go_id"]) for item in registry.values() if item["kind"] == "go"}
        ),
        "available_go_ids": sorted(
            {
                str(go_id)
                for item in registry.values()
                for go_id in (
                    [item["go_id"]]
                    if item["kind"] == "go"
                    else item.get("go_ids", []) if item["kind"] == "paper" else []
                )
            }
        ),
        "available_pmids": sorted(
            {str(item["pmid"]) for item in registry.values() if item["kind"] == "paper"}
        ),
    }


def audit_freeform_answer(answer: str, context: dict[str, Any]) -> dict[str, Any]:
    registry = dict(context.get("evidence_registry") or {})
    citation_ids = unique_in_order(_CITATION_RE.findall(answer))
    valid_citations = [item for item in citation_ids if item in registry]
    invalid_citations = [item for item in citation_ids if item not in registry]
    mentioned_go = sorted(set(_GO_RE.findall(answer)))
    mentioned_pmids = sorted(set(_PMID_RE.findall(answer)))
    bracket_contents = _BRACKET_RE.findall(answer)
    available_go = set(context.get("available_go_ids") or [])
    available_function_go = set(context.get("available_function_go_ids") or [])
    available_pmids = set(context.get("available_pmids") or [])
    go_pairs = _GO_CITATION_RE.findall(answer)
    pmid_pairs = _PMID_CITATION_RE.findall(answer)
    valid_go_pairs = [
        (go_id, citation)
        for go_id, citation in go_pairs
        if citation in registry
        and registry[citation].get("kind") == "go"
        and str(registry[citation].get("go_id")) == go_id
    ]
    valid_pmid_pairs = [
        (pmid, citation)
        for pmid, citation in pmid_pairs
        if citation in registry
        and registry[citation].get("kind") == "paper"
        and str(registry[citation].get("pmid")) == pmid
    ]
    go_entailment = len(valid_go_pairs) / len(go_pairs) if go_pairs else (1.0 if not mentioned_go else 0.0)
    pmid_entailment = len(valid_pmid_pairs) / len(pmid_pairs) if pmid_pairs else (1.0 if not mentioned_pmids else 0.0)
    return {
        "citation_ids": citation_ids,
        "valid_citation_count": len(valid_citations),
        "invalid_citations": invalid_citations,
        "citation_validity": len(valid_citations) / len(citation_ids) if citation_ids else 1.0,
        "citation_syntax_compliance": all(re.fullmatch(r"[CGP]\d+", item) for item in bracket_contents),
        "mentioned_go_ids": mentioned_go,
        "mentioned_pmids": mentioned_pmids,
        "out_of_pack_go_ids": sorted(set(mentioned_go) - available_go),
        "go_ids_without_function_evidence": sorted(set(mentioned_go) - available_function_go),
        "out_of_pack_pmids": sorted(set(mentioned_pmids) - available_pmids),
        "go_citation_pairs": [{"go_id": go_id, "citation_id": cite} for go_id, cite in go_pairs],
        "pmid_citation_pairs": [{"pmid": pmid, "citation_id": cite} for pmid, cite in pmid_pairs],
        "go_citation_entailment": go_entailment,
        "pmid_citation_entailment": pmid_entailment,
        "format_compliance": all(section in answer for section in REQUIRED_SECTIONS),
        "calibration_language": bool(_CALIBRATION_RE.search(answer)),
        "overclaim_flag": bool(_OVERCLAIM_RE.search(answer)),
        "abstention": bool(_ABSTENTION_RE.search(answer)),
    }


def identifier_scores(answer: str, query: dict[str, Any]) -> dict[str, float]:
    predicted_go = set(_GO_RE.findall(answer))
    predicted_pmids = set(_PMID_RE.findall(answer))
    expected_go = {str(item) for item in query.get("expected_go_ids", [])}
    expected_pmids = {str(item) for item in query.get("expected_pmids", [])}
    go_precision, go_recall, go_f1 = set_scores(predicted_go, expected_go)
    pmid_precision, pmid_recall, pmid_f1 = set_scores(predicted_pmids, expected_pmids)
    return {
        "go_precision": go_precision,
        "go_recall": go_recall,
        "go_f1": go_f1,
        "pmid_precision": pmid_precision,
        "pmid_recall": pmid_recall,
        "pmid_f1": pmid_f1,
    }


def stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def unique_in_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def set_scores(predicted: set[str], expected: set[str]) -> tuple[float, float, float]:
    precision = len(predicted & expected) / len(predicted) if predicted else 0.0
    recall = len(predicted & expected) / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _rank_go_records(
    pack: dict[str, Any],
    *,
    candidates: list[dict[str, Any]],
    evidence_mode: str,
    candidate_labels: dict[str, str],
) -> list[dict[str, Any]]:
    by_accession = {str(item.get("accession")): item for item in candidates}
    if evidence_mode == "graph_idf":
        go_order = [str(item["go_id"]) for item in pack.get("go_claims", [])]
    else:
        go_order = [
            str(edge["go_id"])
            for candidate in candidates
            for edge in candidate.get("go_pmid_edges", [])
        ]
        go_order.extend(str(go_id) for candidate in candidates for go_id in candidate.get("go_ids", []))
    records: list[dict[str, Any]] = []
    for go_id in unique_in_order(go_order):
        labels: list[str] = []
        codes: list[str] = []
        pmids: list[str] = []
        for accession, candidate in by_accession.items():
            matching = [edge for edge in candidate.get("go_pmid_edges", []) if str(edge.get("go_id")) == go_id]
            if matching or go_id in {str(item) for item in candidate.get("go_ids", [])}:
                labels.append(candidate_labels[accession])
            for edge in matching:
                codes.extend(str(item) for item in edge.get("evidence_codes", []))
                if edge.get("pmid"):
                    pmids.append(str(edge["pmid"]))
        records.append(
            {
                "go_id": go_id,
                "candidate_labels": unique_in_order(labels),
                "evidence_codes": unique_in_order(codes),
                "pmids": unique_in_order(pmids)[:3],
            }
        )
    return records


def _rank_paper_records(
    pack: dict[str, Any],
    *,
    candidates: list[dict[str, Any]],
    evidence_mode: str,
    candidate_labels: dict[str, str],
    paper_k: int,
) -> list[dict[str, Any]]:
    candidate_by_accession = {str(item.get("accession")): item for item in candidates}
    claim_by_pmid = {
        str(item["pmid"]): item
        for item in pack.get("paper_claims", [])
        if item.get("pmid")
    }
    ordered_pmids = evidence_pmids(pack, evidence_mode=evidence_mode, candidate_k=len(candidates), paper_k=paper_k)
    records: list[dict[str, Any]] = []
    for pmid in ordered_pmids:
        labels: list[str] = []
        go_ids: list[str] = []
        claim = claim_by_pmid.get(pmid, {}) if evidence_mode == "graph_idf" else {}
        for accession in claim.get("accessions", []):
            if str(accession) in candidate_labels:
                labels.append(candidate_labels[str(accession)])
        go_ids.extend(str(item) for item in claim.get("go_ids", []))
        for accession, candidate in candidate_by_accession.items():
            if pmid in {str(item) for item in candidate.get("paper_ids", [])}:
                labels.append(candidate_labels[accession])
            for edge in candidate.get("go_pmid_edges", []):
                if str(edge.get("pmid")) == pmid:
                    go_ids.append(str(edge["go_id"]))
        records.append(
            {
                "pmid": pmid,
                "candidate_labels": unique_in_order(labels),
                "go_ids": unique_in_order(go_ids),
            }
        )
    return records

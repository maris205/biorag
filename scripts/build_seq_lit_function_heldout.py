#!/usr/bin/env python3
"""Build a held-out sequence-to-function-to-paper evaluation split."""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.seq_lit_dag.evaluate import read_jsonl
from scripts.build_seq_lit_heldout import load_proteins, write_index_documents, write_index_fasta


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    proteins = load_proteins(source / "documents.jsonl")
    evidence = load_go_evidence(source / "graph.sqlite")
    proteins_by_go = invert_go(evidence)
    eligible = eligible_accessions(evidence, proteins_by_go, args.min_go_df, args.max_go_df)
    heldout = select_heldout(
        eligible,
        evidence,
        proteins_by_go,
        target=args.queries,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
        seed=args.seed,
    )
    heldout_set = set(heldout)
    truth = make_function_ground_truth(
        heldout,
        evidence,
        proteins_by_go,
        heldout_set=heldout_set,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
    )
    heldout = [accession for accession in heldout if truth.get(accession)]
    heldout_set = set(heldout)
    truth = make_function_ground_truth(
        heldout,
        evidence,
        proteins_by_go,
        heldout_set=heldout_set,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
    )

    write_queries(output / "queries.jsonl", heldout, proteins, truth)
    document_count = write_index_documents(source / "documents.jsonl", output / "index_documents.jsonl", heldout_set)
    fasta_count = write_index_fasta(output / "index.fasta", proteins, heldout_set)
    report = audit(
        heldout,
        proteins,
        truth,
        proteins_by_go,
        index_document_count=document_count,
        index_fasta_count=fasta_count,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
        seed=args.seed,
    )
    (output / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "REPORT.md").write_text(render_report(report), encoding="utf-8")
    print(json.dumps({"output": str(output), **report["counts"]}, indent=2))


def load_go_evidence(graph_db: Path) -> dict[str, dict[str, set[str]]]:
    evidence: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    with sqlite3.connect(graph_db) as conn:
        rows = conn.execute("SELECT metadata_json FROM nodes WHERE entity_type = 'evidence'").fetchall()
    for (raw_metadata,) in rows:
        metadata = json.loads(raw_metadata or "{}")
        accession = str(metadata.get("accession") or "")
        go_id = str(metadata.get("go_id") or "")
        if not accession or not go_id:
            continue
        evidence[accession][go_id].update(str(pmid) for pmid in metadata.get("pmids") or [])
    return {accession: dict(go_map) for accession, go_map in evidence.items()}


def invert_go(evidence: dict[str, dict[str, set[str]]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for accession, go_map in evidence.items():
        for go_id in go_map:
            result[go_id].add(accession)
    return dict(result)


def eligible_accessions(
    evidence: dict[str, dict[str, set[str]]],
    proteins_by_go: dict[str, set[str]],
    min_go_df: int,
    max_go_df: int,
) -> list[str]:
    return [
        accession
        for accession, go_map in evidence.items()
        if any(
            min_go_df <= len(proteins_by_go[go_id]) <= max_go_df
            and bool(pmids)
            for go_id, pmids in go_map.items()
        )
    ]


def select_heldout(
    eligible: list[str],
    evidence: dict[str, dict[str, set[str]]],
    proteins_by_go: dict[str, set[str]],
    *,
    target: int,
    min_go_df: int,
    max_go_df: int,
    seed: int,
) -> list[str]:
    candidates = eligible[:]
    random.Random(seed).shuffle(candidates)
    heldout: list[str] = []
    for accession in candidates:
        proposed = set(heldout) | {accession}
        reachable = any(
            min_go_df <= len(proteins_by_go[go_id]) <= max_go_df
            and bool(pmids)
            and bool(proteins_by_go[go_id] - proposed)
            for go_id, pmids in evidence[accession].items()
        )
        if reachable:
            heldout.append(accession)
        if len(heldout) >= target:
            break
    return heldout


def make_function_ground_truth(
    heldout: list[str],
    evidence: dict[str, dict[str, set[str]]],
    proteins_by_go: dict[str, set[str]],
    *,
    heldout_set: set[str],
    min_go_df: int,
    max_go_df: int,
) -> dict[str, dict[str, list[str]]]:
    truth: dict[str, dict[str, list[str]]] = {}
    for accession in heldout:
        go_ids: list[str] = []
        relevant: set[str] = set()
        pmids: set[str] = set()
        for go_id, query_pmids in evidence[accession].items():
            if not min_go_df <= len(proteins_by_go[go_id]) <= max_go_df or not query_pmids:
                continue
            index_candidates = proteins_by_go[go_id] - heldout_set
            candidate_pmids = {
                pmid
                for candidate in index_candidates
                for pmid in evidence.get(candidate, {}).get(go_id, set())
            }
            if index_candidates and candidate_pmids:
                go_ids.append(go_id)
                relevant.update(index_candidates)
                pmids.update(candidate_pmids)
        if go_ids and pmids:
            truth[accession] = {
                "go_ids": sorted(go_ids),
                "candidate_accessions": sorted(relevant),
                "pmids": sorted(pmids, key=int),
            }
    return truth


def write_queries(
    path: Path,
    heldout: list[str],
    proteins: dict[str, dict[str, Any]],
    truth: dict[str, dict[str, list[str]]],
) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for accession in heldout:
            sequence = str(proteins[accession]["sequence"])
            start = max((len(sequence) - 160) // 2, 0)
            row = {
                "id": f"seq_lit_function_heldout:{accession}",
                "query": sequence[start : start + min(160, len(sequence))],
                "query_type": "heldout_parent_middle_fragment",
                "heldout_accession": accession,
                "expected_go_ids": truth[accession]["go_ids"],
                "expected_pmids": truth[accession]["pmids"],
                "relevant_index_accessions": truth[accession]["candidate_accessions"],
                "label_source": "shared low-frequency GO term plus index-side GOA paper evidence",
                "task": "heldout_sequence_to_function_to_literature",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def audit(
    heldout: list[str],
    proteins: dict[str, dict[str, Any]],
    truth: dict[str, dict[str, list[str]]],
    proteins_by_go: dict[str, set[str]],
    *,
    index_document_count: int,
    index_fasta_count: int,
    min_go_df: int,
    max_go_df: int,
    seed: int,
) -> dict[str, Any]:
    heldout_set = set(heldout)
    index_accessions = set(proteins) - heldout_set
    expected_go = [go_id for accession in heldout for go_id in truth[accession]["go_ids"]]
    expected_pmids = [pmid for accession in heldout for pmid in truth[accession]["pmids"]]
    substring_leaks = [
        accession
        for accession in heldout
        if any(str(proteins[accession]["sequence"]) in str(proteins[item]["sequence"]) for item in index_accessions)
    ]
    return {
        "dataset": "BioRAG-SeqLit-DAG held-out sequence-to-function-to-paper split",
        "claim_scope": "Held-out parents are absent; relevance is low-frequency shared GO plus index-side curated paper evidence.",
        "seed": seed,
        "go_df_range": [min_go_df, max_go_df],
        "counts": {
            "source_proteins": len(proteins),
            "heldout_queries": len(heldout),
            "index_proteins": index_fasta_count,
            "index_documents": index_document_count,
            "unique_expected_go_ids": len(set(expected_go)),
            "unique_expected_pmids": len(set(expected_pmids)),
            "query_go_pairs": len(expected_go),
            "query_pmid_pairs": len(expected_pmids),
        },
        "leakage": {
            "exact_accession_overlap": len(heldout_set & index_accessions),
            "full_sequence_substring_overlap": len(substring_leaks),
        },
        "reachability": {
            "queries_with_index_candidate": sum(bool(truth[a]["candidate_accessions"]) for a in heldout),
            "min_relevant_candidates": min((len(truth[a]["candidate_accessions"]) for a in heldout), default=0),
            "max_relevant_candidates": max((len(truth[a]["candidate_accessions"]) for a in heldout), default=0),
        },
        "go_df": dict(sorted(Counter(len(proteins_by_go[go_id]) for go_id in set(expected_go)).items())),
    }


def render_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    leakage = report["leakage"]
    return "\n".join(
        [
            "# SeqLit-DAG Held-Out Function-to-Paper Split",
            "",
            report["claim_scope"],
            "",
            f"- Held-out queries: `{counts['heldout_queries']}`",
            f"- Index proteins: `{counts['index_proteins']}`",
            f"- Unique expected GO IDs: `{counts['unique_expected_go_ids']}`",
            f"- Unique expected PMIDs: `{counts['unique_expected_pmids']}`",
            f"- Exact accession overlap: `{leakage['exact_accession_overlap']}`",
            f"- Full-sequence substring overlap: `{leakage['full_sequence_substring_overlap']}`",
            f"- GO document-frequency range: `{report['go_df_range'][0]}-{report['go_df_range'][1]}`",
            "",
            "Expected papers are index-side GOA citations attached to proteins sharing a low-frequency GO term with the held-out query. Retrieval models do not generate the labels.",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build held-out sequence-to-function-to-paper split")
    parser.add_argument("--source", default="data/seq_lit_dag_swissprot_sample")
    parser.add_argument("--output", default="data/seq_lit_dag_function_heldout")
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--min-go-df", type=int, default=2)
    parser.add_argument("--max-go-df", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260720)
    return parser.parse_args()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build a leakage-audited held-out parent sequence-to-paper split."""
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


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    proteins = load_proteins(source / "documents.jsonl")
    papers_by_protein, proteins_by_paper = load_direct_paper_links(source / "graph.sqlite")
    heldout = select_heldout(
        proteins,
        papers_by_protein,
        proteins_by_paper,
        target=args.queries,
        min_paper_df=args.min_paper_df,
        max_paper_df=args.max_paper_df,
        seed=args.seed,
    )
    heldout_set = set(heldout)
    ground_truth = make_ground_truth(
        heldout,
        papers_by_protein,
        proteins_by_paper,
        heldout_set=heldout_set,
        min_paper_df=args.min_paper_df,
        max_paper_df=args.max_paper_df,
    )
    heldout = [accession for accession in heldout if ground_truth.get(accession)]
    heldout_set = set(heldout)
    ground_truth = make_ground_truth(
        heldout,
        papers_by_protein,
        proteins_by_paper,
        heldout_set=heldout_set,
        min_paper_df=args.min_paper_df,
        max_paper_df=args.max_paper_df,
    )

    query_count = write_queries(output / "queries.jsonl", heldout, proteins, ground_truth)
    document_count = write_index_documents(
        source / "documents.jsonl", output / "index_documents.jsonl", heldout_set
    )
    fasta_count = write_index_fasta(output / "index.fasta", proteins, heldout_set)
    report = audit_split(
        heldout,
        proteins,
        ground_truth,
        proteins_by_paper,
        index_document_count=document_count,
        index_fasta_count=fasta_count,
        min_paper_df=args.min_paper_df,
        max_paper_df=args.max_paper_df,
        seed=args.seed,
    )
    (output / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "REPORT.md").write_text(render_report(report), encoding="utf-8")
    print(json.dumps({"output": str(output), "query_count": query_count, **report["counts"]}, indent=2))


def load_proteins(path: Path) -> dict[str, dict[str, Any]]:
    proteins: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if row.get("modality") != "protein_sequence":
            continue
        sequence = str(row.get("text") or "").partition("Sequence:\n")[2]
        proteins[str(row["accession"])] = {**row, "sequence": sequence}
    return proteins


def load_direct_paper_links(graph_db: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    by_protein: dict[str, set[str]] = defaultdict(set)
    by_paper: dict[str, set[str]] = defaultdict(set)
    with sqlite3.connect(graph_db) as conn:
        rows = conn.execute(
            """
            SELECT source_entity_id, target_entity_id
            FROM edges
            WHERE relation_type = 'supported_by_paper'
              AND source_entity_id LIKE 'protein:%'
              AND target_entity_id LIKE 'paper:PMID:%'
            """
        ).fetchall()
    for source, target in rows:
        accession = str(source).removeprefix("protein:")
        pmid = str(target).removeprefix("paper:PMID:")
        by_protein[accession].add(pmid)
        by_paper[pmid].add(accession)
    return dict(by_protein), dict(by_paper)


def select_heldout(
    proteins: dict[str, dict[str, Any]],
    papers_by_protein: dict[str, set[str]],
    proteins_by_paper: dict[str, set[str]],
    *,
    target: int,
    min_paper_df: int,
    max_paper_df: int,
    seed: int,
) -> list[str]:
    eligible = [
        accession
        for accession in proteins
        if any(min_paper_df <= len(proteins_by_paper[pmid]) <= max_paper_df for pmid in papers_by_protein.get(accession, set()))
    ]
    random.Random(seed).shuffle(eligible)
    heldout: list[str] = []
    for accession in eligible:
        proposed = set(heldout) | {accession}
        has_reachable_paper = any(
            min_paper_df <= len(proteins_by_paper[pmid]) <= max_paper_df
            and bool(proteins_by_paper[pmid] - proposed)
            for pmid in papers_by_protein.get(accession, set())
        )
        if has_reachable_paper:
            heldout.append(accession)
        if len(heldout) >= target:
            break
    return heldout


def make_ground_truth(
    heldout: list[str],
    papers_by_protein: dict[str, set[str]],
    proteins_by_paper: dict[str, set[str]],
    *,
    heldout_set: set[str],
    min_paper_df: int,
    max_paper_df: int,
) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = {}
    for accession in heldout:
        pmids: list[str] = []
        candidates: set[str] = set()
        for pmid in sorted(papers_by_protein.get(accession, set()), key=int):
            if not min_paper_df <= len(proteins_by_paper[pmid]) <= max_paper_df:
                continue
            reachable = proteins_by_paper[pmid] - heldout_set
            if reachable:
                pmids.append(pmid)
                candidates.update(reachable)
        if pmids:
            result[accession] = {"pmids": pmids, "candidate_accessions": sorted(candidates)}
    return result


def write_queries(
    path: Path,
    heldout: list[str],
    proteins: dict[str, dict[str, Any]],
    ground_truth: dict[str, dict[str, list[str]]],
) -> int:
    with path.open("wt", encoding="utf-8") as handle:
        for accession in heldout:
            protein = proteins[accession]
            sequence = str(protein["sequence"])
            start = max((len(sequence) - 160) // 2, 0)
            query = sequence[start : start + min(160, len(sequence))]
            truth = ground_truth[accession]
            row = {
                "id": f"seq_lit_heldout:{accession}",
                "query": query,
                "query_type": "heldout_parent_middle_fragment",
                "heldout_accession": accession,
                "expected_pmids": truth["pmids"],
                "relevant_index_accessions": truth["candidate_accessions"],
                "label_source": "GOA direct protein-supported_by_paper edges",
                "task": "heldout_sequence_to_literature",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(heldout)


def write_index_documents(source: Path, output: Path, heldout: set[str]) -> int:
    count = 0
    with output.open("wt", encoding="utf-8") as target:
        for row in read_jsonl(source):
            if str(row.get("accession") or "") in heldout:
                continue
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_index_fasta(path: Path, proteins: dict[str, dict[str, Any]], heldout: set[str]) -> int:
    count = 0
    with path.open("wt", encoding="utf-8") as handle:
        for accession, row in proteins.items():
            if accession in heldout:
                continue
            handle.write(f">sp|{accession}|{row.get('name') or accession}\n{row['sequence']}\n")
            count += 1
    return count


def audit_split(
    heldout: list[str],
    proteins: dict[str, dict[str, Any]],
    ground_truth: dict[str, dict[str, list[str]]],
    proteins_by_paper: dict[str, set[str]],
    *,
    index_document_count: int,
    index_fasta_count: int,
    min_paper_df: int,
    max_paper_df: int,
    seed: int,
) -> dict[str, Any]:
    index_accessions = set(proteins) - set(heldout)
    expected_pmids = [pmid for accession in heldout for pmid in ground_truth[accession]["pmids"]]
    substring_leaks = [
        accession
        for accession in heldout
        if any(str(proteins[accession]["sequence"]) in str(proteins[item]["sequence"]) for item in index_accessions)
    ]
    return {
        "dataset": "BioRAG-SeqLit-DAG held-out parent direct-paper split",
        "claim_scope": "Held-out parent accessions are absent from the index; PMID labels come only from curated GOA graph edges.",
        "seed": seed,
        "paper_df_range": [min_paper_df, max_paper_df],
        "counts": {
            "source_proteins": len(proteins),
            "heldout_queries": len(heldout),
            "index_proteins": len(index_accessions),
            "index_documents": index_document_count,
            "unique_expected_pmids": len(set(expected_pmids)),
            "query_pmid_pairs": len(expected_pmids),
        },
        "leakage": {
            "exact_accession_overlap": len(set(heldout) & index_accessions),
            "full_sequence_substring_overlap": len(substring_leaks),
            "substring_accessions": substring_leaks,
        },
        "reachability": {
            "queries_with_index_candidate": sum(bool(ground_truth[a]["candidate_accessions"]) for a in heldout),
            "min_relevant_candidates": min((len(ground_truth[a]["candidate_accessions"]) for a in heldout), default=0),
            "max_relevant_candidates": max((len(ground_truth[a]["candidate_accessions"]) for a in heldout), default=0),
        },
        "paper_df": dict(sorted(Counter(len(proteins_by_paper[pmid]) for pmid in set(expected_pmids)).items())),
    }


def render_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    leakage = report["leakage"]
    reachability = report["reachability"]
    return "\n".join(
        [
            "# SeqLit-DAG Held-Out Parent Split",
            "",
            report["claim_scope"],
            "",
            f"- Held-out queries: `{counts['heldout_queries']}`",
            f"- Index proteins: `{counts['index_proteins']}`",
            f"- Unique expected PMIDs: `{counts['unique_expected_pmids']}`",
            f"- Query-PMID pairs: `{counts['query_pmid_pairs']}`",
            f"- Exact accession overlap: `{leakage['exact_accession_overlap']}`",
            f"- Full-sequence substring overlap: `{leakage['full_sequence_substring_overlap']}`",
            f"- Queries with reachable index evidence: `{reachability['queries_with_index_candidate']}`",
            f"- Paper document-frequency range: `{report['paper_df_range'][0]}-{report['paper_df_range'][1]}`",
            "",
            "PMIDs supported by only one protein are excluded because no held-out retrieval path exists. Very high-frequency papers are excluded to reduce trivial recovery through broad interactome or proteome-scale studies.",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build held-out SeqLit-DAG sequence-to-paper split")
    parser.add_argument("--source", default="data/seq_lit_dag_swissprot_sample")
    parser.add_argument("--output", default="data/seq_lit_dag_heldout")
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--min-paper-df", type=int, default=2)
    parser.add_argument("--max-paper-df", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260720)
    return parser.parse_args()


if __name__ == "__main__":
    main()

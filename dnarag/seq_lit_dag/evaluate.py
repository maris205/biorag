"""CPU sanity evaluation for sequence-to-paper evidence paths."""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dnarag.retrieval.sequence import normalize_sequence


@dataclass(frozen=True, slots=True)
class ProteinCandidate:
    accession: str
    score: float


def evaluate_sequence_to_paper(
    *,
    queries_path: Path,
    documents_path: Path,
    graph_db: Path,
    blast_db: Path | None = None,
    limit: int = 0,
    top_k: int = 10,
    paper_k: int = 50,
    kmer_size: int = 3,
) -> dict[str, Any]:
    queries = read_jsonl(queries_path, limit=limit)
    protein_sequences = load_protein_sequences(documents_path)
    papers_by_accession = load_papers_by_accession(graph_db)
    methods: dict[str, Callable[[str], list[ProteinCandidate]]] = {
        "graph_oracle": lambda _query: [],
        "kmer_jaccard": lambda query: kmer_candidates(query, protein_sequences, k=kmer_size, limit=top_k),
    }
    blast_results: dict[str, list[ProteinCandidate]] = {}
    blast_amortized_ms = 0.0
    if blast_db is not None and shutil.which("blastp") and Path(f"{blast_db}.pin").exists():
        blast_results, blast_elapsed_ms = batch_blast_candidates(queries, blast_db=blast_db, limit=top_k)
        blast_amortized_ms = blast_elapsed_ms / len(queries) if queries else 0.0
        methods["blast"] = lambda _query: []

    details: list[dict[str, Any]] = []
    aggregates: dict[str, list[dict[str, float]]] = {method: [] for method in methods}
    for query_row in queries:
        expected_accessions = {str(item) for item in query_row.get("expected_accessions", [])}
        expected_pmids = {str(item) for item in query_row.get("expected_pmids", [])}
        for method, retrieve in methods.items():
            started = time.perf_counter()
            candidates = (
                [ProteinCandidate(accession, 1.0) for accession in sorted(expected_accessions)]
                if method == "graph_oracle"
                else blast_results.get(str(query_row.get("id")), [])
                if method == "blast"
                else retrieve(str(query_row["query"]))
            )
            candidate_ms = (time.perf_counter() - started) * 1000.0
            if method == "blast":
                candidate_ms = blast_amortized_ms
            ranked_accessions = [candidate.accession for candidate in candidates[:top_k]]
            ranked_pmids = rank_papers(candidates, papers_by_accession, limit=paper_k)
            matched_accessions = expected_accessions.intersection(ranked_accessions)
            matched_pmids = expected_pmids.intersection(ranked_pmids)
            metrics = {
                "accession_hit": float(bool(matched_accessions)),
                "paper_hit": float(bool(matched_pmids)),
                "paper_recall": len(matched_pmids) / len(expected_pmids) if expected_pmids else 0.0,
                "path_complete": float(bool(matched_accessions and matched_pmids)),
                "candidate_ms": candidate_ms,
            }
            aggregates[method].append(metrics)
            details.append(
                {
                    "query_id": query_row.get("id"),
                    "method": method,
                    "expected_accessions": sorted(expected_accessions),
                    "expected_pmids": sorted(expected_pmids),
                    "candidate_accessions": ranked_accessions,
                    "retrieved_pmids": ranked_pmids,
                    **metrics,
                }
            )

    return {
        "dataset": "BioRAG-SeqLit-DAG CPU in-index path sanity",
        "claim_scope": (
            "Pipeline validation only: queries are sequence windows from indexed parent proteins; "
            "results are not held-out homology or biological retrieval evidence."
        ),
        "query_count": len(queries),
        "top_k": top_k,
        "paper_k": paper_k,
        "kmer_size": kmer_size,
        "gpu_required": False,
        "summary": {method: summarize(rows) for method, rows in aggregates.items()},
        "details": details,
    }


def kmer_candidates(query: str, sequences: dict[str, str], *, k: int, limit: int) -> list[ProteinCandidate]:
    query_kmers = kmers(normalize_sequence(query), k)
    scored: list[ProteinCandidate] = []
    for accession, sequence in sequences.items():
        target_kmers = kmers(sequence, k)
        union = query_kmers | target_kmers
        score = len(query_kmers & target_kmers) / len(union) if union else 0.0
        scored.append(ProteinCandidate(accession, score))
    return sorted(scored, key=lambda item: (-item.score, item.accession))[:limit]


def batch_blast_candidates(
    queries: list[dict[str, Any]], *, blast_db: Path, limit: int
) -> tuple[dict[str, list[ProteinCandidate]], float]:
    """Run all evaluation queries in one blastp process to avoid repeated DB startup."""
    blastp = shutil.which("blastp")
    if not blastp:
        return {}, 0.0
    with tempfile.TemporaryDirectory(prefix="dnarag_seq_lit_blast_") as tmp:
        query_path = Path(tmp) / "queries.fa"
        with query_path.open("wt", encoding="utf-8") as handle:
            for row in queries:
                handle.write(f">{row['id']}\n{normalize_sequence(str(row['query']))}\n")
        started = time.perf_counter()
        completed = subprocess.run(
            [
                blastp,
                "-task",
                "blastp",
                "-query",
                str(query_path),
                "-db",
                str(blast_db),
                "-outfmt",
                "6 qseqid sseqid bitscore",
                "-max_target_seqs",
                str(max(limit, 1)),
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
    if completed.returncode != 0:
        raise RuntimeError(f"Batched blastp failed: {completed.stderr[-1000:]}")
    results: dict[str, list[ProteinCandidate]] = {}
    for line in completed.stdout.splitlines():
        query_id, subject_id, bitscore = line.split("\t", maxsplit=2)
        parts = subject_id.split("|")
        accession = parts[1] if len(parts) >= 3 else subject_id.split()[0]
        results.setdefault(query_id, []).append(ProteinCandidate(accession, float(bitscore)))
    return results, elapsed_ms


def load_protein_sequences(path: Path) -> dict[str, str]:
    sequences: dict[str, str] = {}
    for row in read_jsonl(path):
        if row.get("modality") != "protein_sequence":
            continue
        text = str(row.get("text") or "")
        sequence = text.partition("Sequence:\n")[2]
        if sequence:
            sequences[str(row["accession"])] = normalize_sequence(sequence)
    return sequences


def load_papers_by_accession(graph_db: Path) -> dict[str, list[str]]:
    mapping: dict[str, set[str]] = {}
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
        mapping.setdefault(accession, set()).add(pmid)
    return {accession: sorted(pmids, key=int) for accession, pmids in mapping.items()}


def rank_papers(candidates: list[ProteinCandidate], mapping: dict[str, list[str]], *, limit: int) -> list[str]:
    seen: set[str] = set()
    ranked: list[str] = []
    for candidate in candidates:
        for pmid in mapping.get(candidate.accession, []):
            if pmid not in seen:
                seen.add(pmid)
                ranked.append(pmid)
                if len(ranked) >= limit:
                    return ranked
    return ranked


def kmers(sequence: str, k: int) -> set[str]:
    return {sequence[index : index + k] for index in range(max(len(sequence) - k + 1, 0))}


def summarize(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    return {key: sum(row[key] for row in rows) / len(rows) for key in rows[0]}


def read_jsonl(path: Path, *, limit: int = 0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows

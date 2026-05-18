#!/usr/bin/env python3
"""Evaluate vector coarse retrieval followed by candidate-subset BLAST rerank.

The purpose of this experiment is not to replace full-database BLAST. It tests
the BioRAG operating pattern used in the paper:

1. use vector search as a fast, unified candidate generator;
2. extract the candidate parent sequences from the local BLAST database;
3. run BLAST only on that candidate subset to obtain alignment evidence;
4. rerank candidates and evaluate strict plus biological-equivalence metrics.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.evaluation import (
    BenchmarkTask,
    first_biological_match_rank,
    first_match_rank,
    has_biological_expected,
    load_benchmark,
)
from dnarag.retrieval.hybrid import HybridBioSearch
from dnarag.retrieval.sequence import detect_sequence


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    tasks = load_benchmark(args.benchmark)
    if args.limit:
        tasks = tasks[: max(int(args.limit), 0)]
    if args.categories:
        wanted = {item.strip() for item in args.categories.split(",") if item.strip()}
        tasks = [task for task in tasks if task.category in wanted]

    evaluator = VectorBlastRerankEvaluator(
        searcher=HybridBioSearch(config),
        protein_db=config.blast_db,
        nucleotide_db=config.blastn_db,
        candidate_limit=args.candidate_limit,
        final_limit=args.final_limit,
        blast_top_k=args.blast_top_k,
        append_unaligned=args.append_unaligned,
    )
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        if args.progress:
            print(f"[vector-blast-rerank] {index}/{len(tasks)} {task.task_id}", flush=True)
        rows.append(evaluator.run_one(task))
    result = {
        "dataset": "dnarag_vector_blast_rerank_eval",
        "config": args.config,
        "benchmark": args.benchmark,
        "task_count": len(rows),
        "candidate_limit": args.candidate_limit,
        "final_limit": args.final_limit,
        "blast_top_k": args.blast_top_k,
        "append_unaligned": args.append_unaligned,
        "summary": summarize_rows(rows),
        "category_summary": summarize_by_field(rows, "category"),
        "query_type_summary": summarize_by_field(rows, "query_type"),
        "details": rows,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2, ensure_ascii=False))


class VectorBlastRerankEvaluator:
    def __init__(
        self,
        *,
        searcher: HybridBioSearch,
        protein_db: Path,
        nucleotide_db: Path,
        candidate_limit: int,
        final_limit: int,
        blast_top_k: int,
        append_unaligned: bool,
    ):
        self.searcher = searcher
        self.protein_db = Path(protein_db)
        self.nucleotide_db = Path(nucleotide_db)
        self.candidate_limit = max(int(candidate_limit), 1)
        self.final_limit = max(int(final_limit), 1)
        self.blast_top_k = max(int(blast_top_k), 1)
        self.append_unaligned = append_unaligned

    def run_one(self, task: BenchmarkTask) -> dict[str, Any]:
        started = time.perf_counter()
        seq = detect_sequence(task.query)
        if seq is None or seq.alphabet not in {"dna", "protein"}:
            return {
                "task_id": task.task_id,
                "category": task.category,
                "query_type": task.query_type,
                "status": "not_sequence",
                "rank": None,
                "hit_at_10": False,
                "mrr": 0.0,
                "bio_evaluable": has_biological_expected(task.expected),
                "bio_rank": None,
                "bio_hit_at_10": False,
                "bio_mrr": 0.0,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }

        vector_started = time.perf_counter()
        vector_result = self.searcher.search(
            task.query,
            modes=["vector"],
            limit=self.candidate_limit,
            vector_target=task.vector_target,
        )
        vector_latency_ms = (time.perf_counter() - vector_started) * 1000
        vector_evidence = list(vector_result.get("evidence") or [])
        candidates = parent_candidates(vector_evidence, sequence_alphabet=seq.alphabet)

        blast_started = time.perf_counter()
        blast_result = run_candidate_blast(
            query_sequence=seq.sequence,
            sequence_alphabet=seq.alphabet,
            candidates=candidates,
            protein_db=self.protein_db,
            nucleotide_db=self.nucleotide_db,
            max_targets=max(self.blast_top_k, self.final_limit),
        )
        blast_latency_ms = (time.perf_counter() - blast_started) * 1000

        reranked = rerank_candidates(
            candidates,
            blast_result.get("hits") or [],
            sequence_alphabet=seq.alphabet,
            final_limit=self.final_limit,
            append_unaligned=self.append_unaligned,
        )
        rank = first_match_rank(reranked, task.expected)
        bio_evaluable = has_biological_expected(task.expected)
        bio_rank = first_biological_match_rank(reranked, task.expected) if bio_evaluable else None
        candidate_rank = first_match_rank([candidate["evidence"] for candidate in candidates], task.expected)
        candidate_bio_rank = (
            first_biological_match_rank([candidate["evidence"] for candidate in candidates], task.expected)
            if bio_evaluable
            else None
        )
        return {
            "task_id": task.task_id,
            "category": task.category,
            "query_type": task.query_type,
            "status": "ok" if blast_result.get("status") == "ok" else str(blast_result.get("status") or "unknown"),
            "expected": task.expected,
            "candidate_count": len(candidates),
            "candidate_rank": candidate_rank,
            "candidate_hit_at_10": bool(candidate_rank is not None and candidate_rank <= 10),
            "candidate_hit_at_n": bool(candidate_rank is not None),
            "candidate_bio_rank": candidate_bio_rank,
            "candidate_bio_hit_at_10": bool(candidate_bio_rank is not None and candidate_bio_rank <= 10),
            "candidate_bio_hit_at_n": bool(candidate_bio_rank is not None),
            "blast_candidate_count": int(blast_result.get("candidate_count") or 0),
            "blast_hit_count": len(blast_result.get("hits") or []),
            "rank": rank,
            "hit_at_1": bool(rank is not None and rank <= 1),
            "hit_at_5": bool(rank is not None and rank <= 5),
            "hit_at_10": bool(rank is not None and rank <= 10),
            "mrr": round(1.0 / rank, 6) if rank else 0.0,
            "bio_evaluable": bio_evaluable,
            "bio_rank": bio_rank,
            "bio_hit_at_1": bool(bio_rank is not None and bio_rank <= 1),
            "bio_hit_at_5": bool(bio_rank is not None and bio_rank <= 5),
            "bio_hit_at_10": bool(bio_rank is not None and bio_rank <= 10),
            "bio_mrr": round(1.0 / bio_rank, 6) if bio_rank else 0.0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "vector_latency_ms": round(vector_latency_ms, 3),
            "candidate_blast_latency_ms": round(blast_latency_ms, 3),
            "vector_trace": vector_result.get("retrieval_trace") or [],
            "blast_status": blast_result.get("status"),
            "blast_stderr": blast_result.get("stderr"),
            "top_candidates": [compact_candidate(item) for item in candidates[:10]],
            "top_evidence": [compact_evidence(item) for item in reranked[:10]],
        }


def parent_candidates(evidence: list[dict[str, Any]], *, sequence_alphabet: str) -> list[dict[str, Any]]:
    prefix = "dna_sequence:" if sequence_alphabet == "dna" else "protein_sequence:"
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for item in evidence:
        metadata = dict(item.get("metadata") or {})
        accession = optional_str(metadata.get("accession") or metadata.get("source_id") or item.get("source_id"))
        entity_id = optional_str(metadata.get("parent_record_id") or item.get("entity_id"))
        if accession is None and entity_id and ":" in entity_id:
            accession = entity_id.split(":", 1)[1]
        if accession is None:
            continue
        key = accession
        if key in seen:
            continue
        seen.add(key)
        parent_entity_id = entity_id if entity_id and entity_id.startswith(prefix) else f"{prefix}{accession}"
        evidence_row = dict(item)
        evidence_row["entity_id"] = parent_entity_id
        evidence_row["source_id"] = accession
        evidence_row["metadata"] = {**metadata, "accession": accession, "parent_record_id": parent_entity_id}
        candidates.append(
            {
                "accession": accession,
                "entity_id": parent_entity_id,
                "vector_score": float(item.get("score") or 0.0),
                "evidence": evidence_row,
            }
        )
    return candidates


def run_candidate_blast(
    *,
    query_sequence: str,
    sequence_alphabet: str,
    candidates: list[dict[str, Any]],
    protein_db: Path,
    nucleotide_db: Path,
    max_targets: int,
) -> dict[str, Any]:
    if not candidates:
        return {"status": "no_candidates", "candidate_count": 0, "hits": []}
    executable = shutil.which("blastn" if sequence_alphabet == "dna" else "blastp")
    blastdbcmd = shutil.which("blastdbcmd")
    if executable is None or blastdbcmd is None:
        return {"status": "missing_blast_tools", "candidate_count": len(candidates), "hits": []}
    db = nucleotide_db if sequence_alphabet == "dna" else protein_db
    if not blast_db_exists(db, sequence_alphabet=sequence_alphabet):
        return {"status": "missing_blast_db", "db": str(db), "candidate_count": len(candidates), "hits": []}

    with tempfile.TemporaryDirectory(prefix="dnarag_vector_blast_") as tmp_dir:
        tmp = Path(tmp_dir)
        query_path = tmp / "query.fa"
        entries_path = tmp / "entries.txt"
        subject_path = tmp / "candidate_subjects.fa"
        query_path.write_text(f">query\n{query_sequence}\n", encoding="utf-8")
        entries_path.write_text("\n".join(candidate["accession"] for candidate in candidates) + "\n", encoding="utf-8")

        extract = subprocess.run(
            [blastdbcmd, "-db", str(db), "-entry_batch", str(entries_path), "-out", str(subject_path)],
            check=False,
            text=True,
            capture_output=True,
        )
        if extract.returncode != 0 or not subject_path.exists() or subject_path.stat().st_size == 0:
            return {
                "status": "extract_failed",
                "candidate_count": len(candidates),
                "stderr": extract.stderr[-1000:],
                "hits": [],
            }

        sequence_length = len(query_sequence)
        task = (
            "blastn-short"
            if sequence_alphabet == "dna" and sequence_length < 50
            else "blastn"
            if sequence_alphabet == "dna"
            else "blastp-short"
            if sequence_length < 30
            else "blastp"
        )
        completed = subprocess.run(
            [
                executable,
                "-task",
                task,
                "-query",
                str(query_path),
                "-subject",
                str(subject_path),
                "-outfmt",
                "6 sseqid pident length evalue bitscore stitle",
                "-max_target_seqs",
                str(max(int(max_targets), 1)),
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            return {
                "status": "blast_failed",
                "candidate_count": len(candidates),
                "task": task,
                "stderr": completed.stderr[-1000:],
                "hits": [],
            }
        return {
            "status": "ok",
            "candidate_count": len(candidates),
            "task": task,
            "hits": [parse_blast_row(line) for line in completed.stdout.splitlines() if line.strip()],
        }


def rerank_candidates(
    candidates: list[dict[str, Any]],
    blast_hits: list[dict[str, Any]],
    *,
    sequence_alphabet: str,
    final_limit: int,
    append_unaligned: bool,
) -> list[dict[str, Any]]:
    candidate_by_accession = {str(candidate["accession"]): candidate for candidate in candidates}
    used: set[str] = set()
    evidence: list[dict[str, Any]] = []
    for hit in sorted(blast_hits, key=blast_sort_key):
        accession = accession_from_blast_id(hit.get("sseqid"))
        if accession is None or accession in used:
            continue
        candidate = candidate_by_accession.get(accession)
        if candidate is None:
            continue
        used.add(accession)
        evidence.append(blast_hit_to_evidence(hit, candidate=candidate, sequence_alphabet=sequence_alphabet))
        if len(evidence) >= final_limit:
            return evidence
    if append_unaligned and len(evidence) < final_limit:
        remaining = [candidate for candidate in candidates if candidate["accession"] not in used]
        remaining.sort(key=lambda item: float(item.get("vector_score") or 0.0), reverse=True)
        for candidate in remaining:
            row = dict(candidate["evidence"])
            metadata = dict(row.get("metadata") or {})
            metadata["candidate_blast_status"] = "unaligned"
            metadata["vector_score"] = candidate.get("vector_score")
            row["route"] = "vector_blast_rerank"
            row["metadata"] = metadata
            row["score"] = candidate.get("vector_score")
            evidence.append(row)
            if len(evidence) >= final_limit:
                break
    return evidence[:final_limit]


def blast_hit_to_evidence(hit: dict[str, Any], *, candidate: dict[str, Any], sequence_alphabet: str) -> dict[str, Any]:
    sequence_kind = "dna_sequence" if sequence_alphabet == "dna" else "protein_sequence"
    metadata = {
        **dict(candidate.get("evidence", {}).get("metadata") or {}),
        **hit,
        "accession": candidate["accession"],
        "parent_record_id": candidate["entity_id"],
        "vector_score": candidate.get("vector_score"),
        "candidate_blast_status": "aligned",
    }
    return {
        "route": "vector_blast_rerank",
        "entity_id": candidate["entity_id"],
        "kind": "candidate_subset_blast",
        "source_id": candidate["accession"],
        "symbol": candidate.get("evidence", {}).get("symbol"),
        "title": hit.get("title") or candidate.get("evidence", {}).get("title") or candidate["accession"],
        "snippet": (
            f"candidate_subset_blast pident={hit.get('pident')} "
            f"length={hit.get('alignment_length')} evalue={hit.get('evalue')}"
        ),
        "score": hit.get("bitscore"),
        "source": "Vector candidate + BLASTN" if sequence_kind == "dna_sequence" else "Vector candidate + BLASTP",
        "source_url": None,
        "metadata": metadata,
    }


def parse_blast_row(line: str) -> dict[str, Any]:
    parts = line.split("\t")
    while len(parts) < 6:
        parts.append("")
    return {
        "sseqid": parts[0],
        "pident": to_float(parts[1]),
        "alignment_length": to_int(parts[2]),
        "evalue": to_float(parts[3]),
        "bitscore": to_float(parts[4]),
        "title": parts[5],
    }


def blast_db_exists(db: Path, *, sequence_alphabet: str) -> bool:
    suffix = ".nin" if sequence_alphabet == "dna" else ".pin"
    return Path(f"{db}{suffix}").exists()


def blast_sort_key(hit: dict[str, Any]) -> tuple[float, float, float]:
    bitscore = float(hit.get("bitscore") or 0.0)
    pident = float(hit.get("pident") or 0.0)
    evalue = float(hit.get("evalue") if hit.get("evalue") is not None else math.inf)
    return (-bitscore, evalue, -pident)


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return empty_summary()
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    bio_rows = [row for row in rows if row.get("bio_evaluable")]
    summary = {
        "tasks": total,
        "ok_tasks": len(ok_rows),
        "hit_at_1": mean_bool(rows, "hit_at_1"),
        "hit_at_5": mean_bool(rows, "hit_at_5"),
        "hit_at_10": mean_bool(rows, "hit_at_10"),
        "mrr": mean_float(rows, "mrr"),
        "candidate_hit_at_10": mean_bool(rows, "candidate_hit_at_10"),
        "candidate_hit_at_n": mean_bool(rows, "candidate_hit_at_n"),
        "avg_candidate_count": mean_float(rows, "candidate_count"),
        "avg_blast_hit_count": mean_float(rows, "blast_hit_count"),
        "avg_latency_ms": mean_float(rows, "latency_ms", digits=3),
        "avg_vector_latency_ms": mean_float(rows, "vector_latency_ms", digits=3),
        "avg_candidate_blast_latency_ms": mean_float(rows, "candidate_blast_latency_ms", digits=3),
        "status_counts": dict(status_counts(rows)),
    }
    if bio_rows:
        summary.update(
            {
                "bio_tasks": len(bio_rows),
                "bio_hit_at_1": mean_bool(bio_rows, "bio_hit_at_1"),
                "bio_hit_at_5": mean_bool(bio_rows, "bio_hit_at_5"),
                "bio_hit_at_10": mean_bool(bio_rows, "bio_hit_at_10"),
                "bio_mrr": mean_float(bio_rows, "bio_mrr"),
                "candidate_bio_hit_at_10": mean_bool(bio_rows, "candidate_bio_hit_at_10"),
                "candidate_bio_hit_at_n": mean_bool(bio_rows, "candidate_bio_hit_at_n"),
            }
        )
    return summary


def summarize_by_field(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field) or "unknown")].append(row)
    return {key: summarize_rows(value) for key, value in sorted(grouped.items())}


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Vector Coarse Retrieval + Candidate BLAST Rerank",
        "",
        "This experiment evaluates vector retrieval as a candidate generator, followed by BLAST reranking on the vector-retrieved candidate subset. It should be interpreted as a BioRAG pipeline ablation, not as a claim that vectors replace full-database BLAST.",
        "",
        "## Overall",
        "",
        "| Method | Tasks | Hit@10 | MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Avg latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| Vector -> candidate BLAST rerank | {summary.get('tasks', 0)} | "
            f"{summary.get('hit_at_10', 0):.4f} | {summary.get('mrr', 0):.4f} | "
            f"{summary.get('bio_hit_at_10', 0):.4f} | {summary.get('bio_mrr', 0):.4f} | "
            f"{summary.get('candidate_bio_hit_at_n', 0):.4f} | {summary.get('avg_latency_ms', 0):.3f} |"
        ),
        "",
        "## By Modality",
        "",
        "| Category | Tasks | Hit@10 | MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Avg latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for category, row in result["category_summary"].items():
        lines.append(
            f"| {category} | {row.get('tasks', 0)} | {row.get('hit_at_10', 0):.4f} | "
            f"{row.get('mrr', 0):.4f} | {row.get('bio_hit_at_10', 0):.4f} | "
            f"{row.get('bio_mrr', 0):.4f} | {row.get('candidate_bio_hit_at_n', 0):.4f} | "
            f"{row.get('avg_latency_ms', 0):.3f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `Candidate Bio Recall@N` measures whether vector coarse retrieval placed a biologically equivalent candidate inside the candidate pool before BLAST reranking.",
            "- The final reranked metrics measure whether candidate-subset BLAST can promote the correct or biologically equivalent candidate into the top results.",
            "- Full-database BLAST remains the verification reference; this pipeline is intended for instant candidate generation plus verified reranking inside BioRAG/DRAG.",
            "",
        ]
    )
    return "\n".join(lines)


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "accession": candidate.get("accession"),
        "entity_id": candidate.get("entity_id"),
        "vector_score": round(float(candidate.get("vector_score") or 0.0), 6),
    }


def compact_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": item.get("route"),
        "entity_id": item.get("entity_id"),
        "source_id": item.get("source_id"),
        "title": item.get("title"),
        "score": item.get("score"),
        "metadata": {
            key: (item.get("metadata") or {}).get(key)
            for key in ("accession", "pident", "alignment_length", "evalue", "bitscore", "vector_score")
        },
    }


def accession_from_blast_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "|" in text:
        parts = [part for part in text.split("|") if part]
        if len(parts) >= 2:
            return parts[1]
    return text


def status_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("status") or "unknown")] += 1
    return counts


def mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row.get(key)) / len(rows), 4)


def mean_float(rows: list[dict[str, Any]], key: str, *, digits: int = 4) -> float:
    values = [float(row.get(key) or 0.0) for row in rows]
    if not values:
        return 0.0
    return round(sum(values) / len(values), digits)


def empty_summary() -> dict[str, Any]:
    return {
        "tasks": 0,
        "ok_tasks": 0,
        "hit_at_1": 0.0,
        "hit_at_5": 0.0,
        "hit_at_10": 0.0,
        "mrr": 0.0,
        "bio_hit_at_1": 0.0,
        "bio_hit_at_5": 0.0,
        "bio_hit_at_10": 0.0,
        "bio_mrr": 0.0,
    }


def optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def to_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate vector candidates followed by candidate-subset BLAST rerank")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--benchmark", default="benchmarks/sequence_search_100_seed20260516_bio.jsonl")
    parser.add_argument("--output", default="reports/vector_blast_rerank_eval.json")
    parser.add_argument("--markdown", default="reports/vector_blast_rerank_summary.md")
    parser.add_argument("--categories", default="", help="Optional comma-separated category filter")
    parser.add_argument("--limit", type=int, default=0, help="Optional max task count")
    parser.add_argument("--candidate-limit", type=int, default=50)
    parser.add_argument("--final-limit", type=int, default=10)
    parser.add_argument("--blast-top-k", type=int, default=50)
    parser.add_argument("--append-unaligned", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

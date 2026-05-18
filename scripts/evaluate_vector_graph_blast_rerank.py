#!/usr/bin/env python3
"""Evaluate vector candidates expanded through DRAG graph neighbors, then BLAST rerank.

This is a Plan 1 retrieval ablation:

1. use OmniGene/Chroma vector search to seed parent sequence candidates;
2. expand those seed candidates through an existing DRAG sequence view graph;
3. run candidate-subset BLAST on the expanded candidate set;
4. report whether DRAG improves the candidate pool before alignment reranking.

The bundled 10k view graphs are subgraphs, so this script reports graph coverage
explicitly. Low graph coverage should be interpreted as a limitation of the
available graph scale, not as a final full-graph result.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.evaluation import first_biological_match_rank, first_match_rank, has_biological_expected, load_benchmark
from dnarag.retrieval.hybrid import HybridBioSearch
from dnarag.retrieval.sequence import detect_sequence
from dnarag.retrieval.vector_db import ChromaVectorDB
from scripts.evaluate_vector_blast_rerank import parent_candidates, rerank_candidates, run_candidate_blast, summarize_rows


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    tasks = load_benchmark(args.benchmark)
    if args.limit:
        tasks = tasks[: max(int(args.limit), 0)]
    if args.categories:
        wanted = {item.strip() for item in args.categories.split(",") if item.strip()}
        tasks = [task for task in tasks if task.category in wanted]

    evaluator = VectorGraphBlastEvaluator(
        searcher=HybridBioSearch(config),
        vector_db=ChromaVectorDB(config.vector_dir),
        graph_dir=config.graph_dir,
        graph_mode=args.graph_mode,
        relations=[item.strip() for item in args.relations.split(",") if item.strip()],
        seed_limit=args.seed_limit,
        graph_neighbors=args.graph_neighbors,
        max_candidates=args.max_candidates,
        final_limit=args.final_limit,
        blast_top_k=args.blast_top_k,
        append_unaligned=args.append_unaligned,
        protein_db=config.blast_db,
        nucleotide_db=config.blastn_db,
    )
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        if args.progress:
            print(f"[vector-graph-blast] {index}/{len(tasks)} {task.task_id}", flush=True)
        rows.append(evaluator.run_one(task))

    result = {
        "dataset": "dnarag_vector_graph_blast_rerank_eval",
        "config": args.config,
        "benchmark": args.benchmark,
        "graph_mode": args.graph_mode,
        "relations": evaluator.relations,
        "task_count": len(rows),
        "seed_limit": args.seed_limit,
        "graph_neighbors": args.graph_neighbors,
        "max_candidates": args.max_candidates,
        "final_limit": args.final_limit,
        "blast_top_k": args.blast_top_k,
        "append_unaligned": args.append_unaligned,
        "summary": summarize_augmented(rows),
        "category_summary": summarize_by_field(rows, "category"),
        "query_type_summary": summarize_by_field(rows, "query_type"),
        "details": rows,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2, ensure_ascii=False))


class VectorGraphBlastEvaluator:
    def __init__(
        self,
        *,
        searcher: HybridBioSearch,
        vector_db: ChromaVectorDB,
        graph_dir: Path,
        graph_mode: str,
        relations: list[str],
        seed_limit: int,
        graph_neighbors: int,
        max_candidates: int,
        final_limit: int,
        blast_top_k: int,
        append_unaligned: bool,
        protein_db: Path,
        nucleotide_db: Path,
    ):
        self.searcher = searcher
        self.vector_db = vector_db
        self.graph_dir = Path(graph_dir)
        self.graph_mode = graph_mode
        self.relations = relations or ["blast_neighbor", "vector_neighbor"]
        self.seed_limit = max(int(seed_limit), 1)
        self.graph_neighbors = max(int(graph_neighbors), 0)
        self.max_candidates = max(int(max_candidates), self.seed_limit)
        self.final_limit = max(int(final_limit), 1)
        self.blast_top_k = max(int(blast_top_k), 1)
        self.append_unaligned = append_unaligned
        self.protein_db = Path(protein_db)
        self.nucleotide_db = Path(nucleotide_db)
        self._resolver = SequenceEvidenceResolver(vector_db)
        self._expanders: dict[str, GraphCandidateExpander] = {}

    def run_one(self, task: Any) -> dict[str, Any]:
        started = time.perf_counter()
        seq = detect_sequence(task.query)
        if seq is None or seq.alphabet not in {"dna", "protein"}:
            return empty_row(task, status="not_sequence", started=started)

        vector_started = time.perf_counter()
        vector_result = self.searcher.search(
            task.query,
            modes=["vector"],
            limit=self.seed_limit,
            vector_target=task.vector_target,
        )
        vector_latency_ms = (time.perf_counter() - vector_started) * 1000
        seed_candidates = parent_candidates(list(vector_result.get("evidence") or []), sequence_alphabet=seq.alphabet)

        graph_started = time.perf_counter()
        expanded, graph_stats = self.expand_candidates(seed_candidates, alphabet=seq.alphabet)
        graph_latency_ms = (time.perf_counter() - graph_started) * 1000
        candidates = expanded[: self.max_candidates]

        blast_started = time.perf_counter()
        blast_result = run_candidate_blast(
            query_sequence=seq.sequence,
            sequence_alphabet=seq.alphabet,
            candidates=candidates,
            protein_db=self.protein_db,
            nucleotide_db=self.nucleotide_db,
            max_targets=max(self.blast_top_k, self.max_candidates, self.final_limit),
        )
        blast_latency_ms = (time.perf_counter() - blast_started) * 1000

        reranked = rerank_candidates(
            candidates,
            list(blast_result.get("hits") or []),
            sequence_alphabet=seq.alphabet,
            final_limit=self.final_limit,
            append_unaligned=self.append_unaligned,
        )
        rank = first_match_rank(reranked, task.expected)
        bio_evaluable = has_biological_expected(task.expected)
        bio_rank = first_biological_match_rank(reranked, task.expected) if bio_evaluable else None
        seed_evidence = [candidate["evidence"] for candidate in seed_candidates]
        candidate_evidence = [candidate["evidence"] for candidate in candidates]
        seed_candidate_rank = first_match_rank(seed_evidence, task.expected)
        seed_candidate_bio_rank = first_biological_match_rank(seed_evidence, task.expected) if bio_evaluable else None
        candidate_rank = first_match_rank(candidate_evidence, task.expected)
        candidate_bio_rank = first_biological_match_rank(candidate_evidence, task.expected) if bio_evaluable else None
        return {
            "task_id": task.task_id,
            "category": task.category,
            "query_type": task.query_type,
            "status": "ok" if blast_result.get("status") == "ok" else str(blast_result.get("status") or "unknown"),
            "expected": task.expected,
            "seed_candidate_count": len(seed_candidates),
            "candidate_count": len(candidates),
            "graph_added_count": max(len(candidates) - len(seed_candidates), 0),
            "graph_raw_neighbor_count": graph_stats.get("raw_neighbor_count", 0),
            "graph_seed_nodes": graph_stats.get("seed_nodes", 0),
            "graph_seed_nodes_found": graph_stats.get("seed_nodes_found", 0),
            "graph_db": graph_stats.get("graph_db"),
            "graph_status": graph_stats.get("status"),
            "seed_candidate_rank": seed_candidate_rank,
            "seed_candidate_hit_at_n": bool(seed_candidate_rank is not None),
            "seed_candidate_bio_rank": seed_candidate_bio_rank,
            "seed_candidate_bio_hit_at_n": bool(seed_candidate_bio_rank is not None),
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
            "graph_expand_latency_ms": round(graph_latency_ms, 3),
            "candidate_blast_latency_ms": round(blast_latency_ms, 3),
            "blast_status": blast_result.get("status"),
            "blast_stderr": blast_result.get("stderr"),
            "top_candidates": [compact_candidate(item) for item in candidates[:10]],
            "top_evidence": [compact_evidence(item) for item in reranked[:10]],
        }

    def expand_candidates(self, seed_candidates: list[dict[str, Any]], *, alphabet: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if self.graph_neighbors <= 0:
            return list(seed_candidates), {
                "status": "disabled",
                "seed_nodes": len(seed_candidates),
                "seed_nodes_found": 0,
                "raw_neighbor_count": 0,
                "graph_db": None,
            }
        expander = self._graph_expander(alphabet)
        if expander is None:
            return list(seed_candidates), {
                "status": "missing_graph",
                "seed_nodes": len(seed_candidates),
                "seed_nodes_found": 0,
                "raw_neighbor_count": 0,
                "graph_db": str(graph_path(self.graph_dir, alphabet=alphabet, mode=self.graph_mode)),
            }
        seen = {str(candidate["accession"]) for candidate in seed_candidates}
        expanded = list(seed_candidates)
        raw_neighbors = expander.expand(seed_candidates, per_seed_limit=self.graph_neighbors)
        for neighbor in raw_neighbors:
            if len(expanded) >= self.max_candidates:
                break
            candidate = self._graph_neighbor_to_candidate(neighbor, alphabet=alphabet)
            if candidate is None:
                continue
            accession = str(candidate["accession"])
            if accession in seen:
                continue
            seen.add(accession)
            expanded.append(candidate)
        return expanded, {
            "status": "ok",
            "seed_nodes": len(seed_candidates),
            "seed_nodes_found": expander.last_seed_nodes_found,
            "raw_neighbor_count": len(raw_neighbors),
            "graph_db": str(expander.db_path),
        }

    def _graph_expander(self, alphabet: str) -> "GraphCandidateExpander | None":
        cached = self._expanders.get(alphabet)
        if cached is not None:
            return cached
        path = graph_path(self.graph_dir, alphabet=alphabet, mode=self.graph_mode)
        if not path.exists():
            return None
        expander = GraphCandidateExpander(path, relations=self.relations)
        self._expanders[alphabet] = expander
        return expander

    def _graph_neighbor_to_candidate(self, neighbor: dict[str, Any], *, alphabet: str) -> dict[str, Any] | None:
        entity_id = str(neighbor.get("entity_id") or "")
        accession = accession_from_entity(entity_id, neighbor.get("canonical_id") or neighbor.get("name"))
        if not accession:
            return None
        prefix = "dna_sequence:" if alphabet == "dna" else "protein_sequence:"
        parent_entity_id = entity_id if entity_id.startswith(prefix) else f"{prefix}{accession}"
        evidence = self._resolver.evidence_for(parent_entity_id, alphabet=alphabet, fallback_node=neighbor)
        metadata = dict(evidence.get("metadata") or {})
        metadata.update(
            {
                "accession": accession,
                "parent_record_id": parent_entity_id,
                "candidate_origin": "drag_graph_expand",
                "graph_seed_entity_id": neighbor.get("seed_entity_id"),
                "graph_relation_type": neighbor.get("relation_type"),
                "graph_confidence": neighbor.get("confidence"),
                "graph_metadata": neighbor.get("edge_metadata") or {},
            }
        )
        evidence["route"] = "vector_graph_blast_rerank"
        evidence["entity_id"] = parent_entity_id
        evidence["source_id"] = accession
        evidence["metadata"] = metadata
        evidence["score"] = neighbor_score(neighbor)
        return {
            "accession": accession,
            "entity_id": parent_entity_id,
            "vector_score": neighbor_score(neighbor),
            "evidence": evidence,
        }


class GraphCandidateExpander:
    def __init__(self, db_path: Path, *, relations: list[str]):
        self.db_path = Path(db_path)
        self.relations = relations
        self._relation_order = {relation: index for index, relation in enumerate(relations)}
        self.last_seed_nodes_found = 0

    def expand(self, seed_candidates: list[dict[str, Any]], *, per_seed_limit: int) -> list[dict[str, Any]]:
        seed_ids = [str(candidate.get("entity_id") or "") for candidate in seed_candidates if candidate.get("entity_id")]
        if not seed_ids:
            self.last_seed_nodes_found = 0
            return []
        rows: list[dict[str, Any]] = []
        found: set[str] = set()
        with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            for seed_rank, seed_entity_id in enumerate(seed_ids, start=1):
                if not node_exists(conn, seed_entity_id):
                    continue
                found.add(seed_entity_id)
                rows.extend(self._neighbors(conn, seed_entity_id, seed_rank=seed_rank, limit=per_seed_limit))
        self.last_seed_nodes_found = len(found)
        rows.sort(key=self._sort_key)
        return rows

    def _neighbors(self, conn: sqlite3.Connection, seed_entity_id: str, *, seed_rank: int, limit: int) -> list[dict[str, Any]]:
        params: list[Any] = [seed_entity_id]
        relation_sql = ""
        if self.relations:
            placeholders = ",".join("?" for _ in self.relations)
            relation_sql = f" AND e.relation_type IN ({placeholders})"
            params.extend(self.relations)
        params.append(max(int(limit), 1))
        outward = conn.execute(
            f"""
            SELECT e.source_entity_id, e.relation_type, e.target_entity_id, e.confidence,
                   e.metadata_json AS edge_metadata_json,
                   n.entity_id, n.canonical_id, n.name, n.source, n.description, n.metadata_json AS node_metadata_json
            FROM edges e
            JOIN nodes n ON n.entity_id = e.target_entity_id
            WHERE e.source_entity_id = ?
            {relation_sql}
            ORDER BY e.confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        params = [seed_entity_id]
        if self.relations:
            params.extend(self.relations)
        params.append(max(int(limit), 1))
        inward = conn.execute(
            f"""
            SELECT e.source_entity_id, e.relation_type, e.target_entity_id, e.confidence,
                   e.metadata_json AS edge_metadata_json,
                   n.entity_id, n.canonical_id, n.name, n.source, n.description, n.metadata_json AS node_metadata_json
            FROM edges e
            JOIN nodes n ON n.entity_id = e.source_entity_id
            WHERE e.target_entity_id = ?
            {relation_sql}
            ORDER BY e.confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._row_to_neighbor(row, seed_entity_id=seed_entity_id, seed_rank=seed_rank) for row in [*outward, *inward]]

    def _row_to_neighbor(self, row: sqlite3.Row, *, seed_entity_id: str, seed_rank: int) -> dict[str, Any]:
        return {
            "seed_entity_id": seed_entity_id,
            "seed_rank": seed_rank,
            "source_entity_id": row["source_entity_id"],
            "relation_type": row["relation_type"],
            "target_entity_id": row["target_entity_id"],
            "confidence": row["confidence"],
            "edge_metadata": json_load(row["edge_metadata_json"]),
            "entity_id": row["entity_id"],
            "canonical_id": row["canonical_id"],
            "name": row["name"],
            "source": row["source"],
            "description": row["description"],
            "node_metadata": json_load(row["node_metadata_json"]),
        }

    def _sort_key(self, row: dict[str, Any]) -> tuple[int, int, int, float]:
        edge_metadata = dict(row.get("edge_metadata") or {})
        relation = str(row.get("relation_type") or "")
        return (
            int(row.get("seed_rank") or 0),
            self._relation_order.get(relation, len(self._relation_order)),
            int(edge_metadata.get("rank") or 9999),
            -neighbor_score(row),
        )


class SequenceEvidenceResolver:
    def __init__(self, vector_db: ChromaVectorDB):
        self.vector_db = vector_db
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    def evidence_for(self, entity_id: str, *, alphabet: str, fallback_node: dict[str, Any]) -> dict[str, Any]:
        target = "dna_sequence_window" if alphabet == "dna" else "protein_sequence_window"
        key = (target, entity_id)
        cached = self._cache.get(key)
        if cached is not None:
            return dict(cached)
        try:
            rows = self.vector_db.get_records(target, record_ids=[entity_id], limit=1)
        except Exception:
            rows = []
        if rows:
            row = rows[0]
            metadata = dict(row.get("metadata") or {})
            accession = metadata.get("accession") or metadata.get("source_id") or strip_entity_prefix(entity_id)
            evidence = {
                "route": "vector_graph_candidate",
                "entity_id": entity_id,
                "kind": metadata.get("parent_kind") or metadata.get("kind") or target,
                "source_id": accession,
                "symbol": metadata.get("symbol"),
                "title": metadata.get("header") or metadata.get("symbol") or accession,
                "snippet": str(row.get("document") or "")[:500] or "DRAG-expanded sequence candidate",
                "score": None,
                "source": metadata.get("source"),
                "source_url": metadata.get("source_url"),
                "metadata": metadata,
            }
        else:
            accession = accession_from_entity(entity_id, fallback_node.get("canonical_id") or fallback_node.get("name"))
            metadata = dict(fallback_node.get("node_metadata") or {})
            evidence = {
                "route": "vector_graph_candidate",
                "entity_id": entity_id,
                "kind": "dna_sequence" if alphabet == "dna" else "protein_sequence",
                "source_id": accession,
                "symbol": None,
                "title": str(fallback_node.get("name") or accession or entity_id),
                "snippet": str(fallback_node.get("description") or "")[:500],
                "score": None,
                "source": fallback_node.get("source"),
                "source_url": None,
                "metadata": metadata,
            }
        self._cache[key] = dict(evidence)
        return evidence


def graph_path(graph_dir: Path, *, alphabet: str, mode: str) -> Path:
    prefix = "dna_sequence_window" if alphabet == "dna" else "protein_sequence_window"
    if mode == "vector":
        name = f"{prefix}_10k.sqlite"
    elif mode == "blast":
        name = f"{prefix}_blast_10k.sqlite"
    elif mode == "hybrid":
        name = f"{prefix}_hybrid_10k.sqlite"
    else:
        raise ValueError(f"Unknown graph mode: {mode}")
    return Path(graph_dir) / "views" / name


def node_exists(conn: sqlite3.Connection, entity_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM nodes WHERE entity_id = ? LIMIT 1", (entity_id,)).fetchone()
    return row is not None


def accession_from_entity(entity_id: Any, fallback: Any = None) -> str | None:
    for value in (fallback, entity_id):
        text = str(value or "").strip()
        if not text:
            continue
        if ":" in text:
            text = text.split(":", 1)[1]
        if text:
            return text
    return None


def strip_entity_prefix(value: Any) -> str:
    text = str(value or "")
    return text.split(":", 1)[1] if ":" in text else text


def neighbor_score(row: dict[str, Any]) -> float:
    value = row.get("confidence")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def summarize_augmented(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_rows(rows)
    if not rows:
        return summary
    bio_rows = [row for row in rows if row.get("bio_evaluable")]
    summary.update(
        {
            "seed_candidate_bio_recall": mean_bool(bio_rows, "seed_candidate_bio_hit_at_n") if bio_rows else 0.0,
            "expanded_candidate_bio_recall": mean_bool(bio_rows, "candidate_bio_hit_at_n") if bio_rows else 0.0,
            "avg_seed_candidate_count": mean_float(rows, "seed_candidate_count"),
            "avg_graph_added_count": mean_float(rows, "graph_added_count"),
            "avg_graph_raw_neighbor_count": mean_float(rows, "graph_raw_neighbor_count"),
            "avg_graph_seed_nodes_found": mean_float(rows, "graph_seed_nodes_found"),
            "avg_graph_expand_latency_ms": mean_float(rows, "graph_expand_latency_ms", digits=3),
            "graph_status_counts": dict(status_counts(rows, "graph_status")),
        }
    )
    return summary


def summarize_by_field(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field) or "unknown")].append(row)
    return {key: summarize_augmented(value) for key, value in sorted(grouped.items())}


def mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row.get(key)) / len(rows), 4)


def mean_float(rows: list[dict[str, Any]], key: str, *, digits: int = 4) -> float:
    if not rows:
        return 0.0
    return round(sum(float(row.get(key) or 0.0) for row in rows) / len(rows), digits)


def status_counts(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get(key) or "unknown")] += 1
    return counts


def empty_row(task: Any, *, status: str, started: float) -> dict[str, Any]:
    bio_evaluable = has_biological_expected(task.expected)
    return {
        "task_id": task.task_id,
        "category": task.category,
        "query_type": task.query_type,
        "status": status,
        "seed_candidate_count": 0,
        "candidate_count": 0,
        "graph_added_count": 0,
        "graph_status": "not_run",
        "rank": None,
        "hit_at_1": False,
        "hit_at_5": False,
        "hit_at_10": False,
        "mrr": 0.0,
        "bio_evaluable": bio_evaluable,
        "bio_rank": None,
        "bio_hit_at_1": False,
        "bio_hit_at_5": False,
        "bio_hit_at_10": False,
        "bio_mrr": 0.0,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(candidate.get("evidence", {}).get("metadata") or {})
    return {
        "accession": candidate.get("accession"),
        "entity_id": candidate.get("entity_id"),
        "score": round(float(candidate.get("vector_score") or 0.0), 6),
        "origin": metadata.get("candidate_origin") or "vector",
        "graph_relation_type": metadata.get("graph_relation_type"),
    }


def compact_evidence(item: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(item.get("metadata") or {})
    return {
        "route": item.get("route"),
        "entity_id": item.get("entity_id"),
        "source_id": item.get("source_id"),
        "title": item.get("title"),
        "score": item.get("score"),
        "candidate_blast_status": metadata.get("candidate_blast_status"),
        "graph_relation_type": metadata.get("graph_relation_type"),
    }


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Vector + DRAG Graph Candidates + Candidate BLAST Rerank",
        "",
        "This experiment expands vector-retrieved sequence candidates through an existing DRAG view graph before candidate-subset BLAST reranking. The current graph is a 10k view graph, so graph coverage is reported explicitly.",
        "",
        "## Overall",
        "",
        "| Method | Tasks | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Seed Bio Recall | Expanded Bio Recall | Graph added | Graph seeds found | BLAST ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| Vector({result['seed_limit']}) + DRAG({result['graph_mode']}) -> BLAST | {summary.get('tasks', 0)} | "
            f"{summary.get('hit_at_10', 0):.4f} | {summary.get('mrr', 0):.4f} | "
            f"{summary.get('bio_hit_at_10', 0):.4f} | {summary.get('bio_mrr', 0):.4f} | "
            f"{summary.get('seed_candidate_bio_recall', 0):.4f} | {summary.get('expanded_candidate_bio_recall', 0):.4f} | "
            f"{summary.get('avg_graph_added_count', 0):.2f} | {summary.get('avg_graph_seed_nodes_found', 0):.2f} | "
            f"{summary.get('avg_candidate_blast_latency_ms', 0):.3f} |"
        ),
        "",
        "## By Modality",
        "",
        "| Category | Tasks | Exact Hit@10 | Bio Hit@10 | Bio MRR | Seed Bio Recall | Expanded Bio Recall | Graph added | Graph seeds found |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for category, row in result["category_summary"].items():
        lines.append(
            f"| {category} | {row.get('tasks', 0)} | {row.get('hit_at_10', 0):.4f} | "
            f"{row.get('bio_hit_at_10', 0):.4f} | {row.get('bio_mrr', 0):.4f} | "
            f"{row.get('seed_candidate_bio_recall', 0):.4f} | {row.get('expanded_candidate_bio_recall', 0):.4f} | "
            f"{row.get('avg_graph_added_count', 0):.2f} | {row.get('avg_graph_seed_nodes_found', 0):.2f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `Seed Bio Recall` is the biological recall of the vector seed pool before graph expansion.",
            "- `Expanded Bio Recall` is the biological recall after adding DRAG graph neighbors.",
            "- Because the current DRAG view graphs cover only a 10k sequence subgraph, low `Graph seeds found` means this is a coverage-limited ablation rather than a full-scale DRAG result.",
            "- A full 100k or complete sequence DRAG graph is the next step before making a strong retrieval-quality claim for graph-expanded candidates.",
            "",
        ]
    )
    return "\n".join(lines)


def json_load(value: Any) -> dict[str, Any]:
    if value in {None, ""}:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate vector candidates expanded by DRAG graph neighbors before BLAST rerank")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--benchmark", default="benchmarks/sequence_search_100_seed20260516_bio.jsonl")
    parser.add_argument("--output", default="reports/vector_graph_blast_rerank_eval.json")
    parser.add_argument("--markdown", default="reports/vector_graph_blast_rerank_summary.md")
    parser.add_argument("--categories", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed-limit", type=int, default=50)
    parser.add_argument("--graph-neighbors", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--graph-mode", choices=["vector", "blast", "hybrid"], default="hybrid")
    parser.add_argument("--relations", default="blast_neighbor,vector_neighbor")
    parser.add_argument("--final-limit", type=int, default=10)
    parser.add_argument("--blast-top-k", type=int, default=50)
    parser.add_argument("--append-unaligned", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

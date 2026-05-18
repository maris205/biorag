"""Basic retrieval evaluation for local BioRAG conditions."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dnarag.config import BioKBConfig
from dnarag.retrieval.hybrid import HybridBioSearch


DEFAULT_CONDITIONS: dict[str, dict[str, Any]] = {
    "fts": {"modes": ["fts"], "description": "SQLite FTS text retrieval"},
    "blast": {"modes": ["blast"], "description": "Local BLAST sequence retrieval"},
    "classical": {"modes": ["fts", "blast"], "description": "Traditional local FTS + BLAST"},
    "vector": {"modes": ["vector"], "description": "OmniGene embeddings + Chroma"},
    "drag": {"modes": ["fts", "graph"], "description": "FTS-seeded DRAG graph expansion"},
    "hybrid": {"modes": ["fts", "blast", "graph", "vector"], "description": "Ungated FTS + BLAST + DRAG + vector"},
    "hybrid_gated": {"modes": ["auto"], "description": "Route-gated Hybrid BioRAG"},
}


@dataclass(frozen=True, slots=True)
class BenchmarkTask:
    task_id: str
    query: str
    category: str
    expected: dict[str, Any]
    vector_target: str | None = None
    query_type: str | None = None
    notes: str | None = None


class SearchEvaluator:
    def __init__(self, config: BioKBConfig):
        self.config = config
        self.searcher = HybridBioSearch(config)

    def run(
        self,
        tasks: Iterable[BenchmarkTask],
        *,
        conditions: Iterable[str],
        limit: int = 10,
        progress: bool = False,
    ) -> dict[str, Any]:
        selected_conditions = [name for name in conditions if name]
        unknown = [name for name in selected_conditions if name not in DEFAULT_CONDITIONS]
        if unknown:
            raise ValueError(f"Unknown evaluation condition(s): {', '.join(unknown)}")
        task_list = list(tasks)
        details: list[dict[str, Any]] = []
        summaries: dict[str, dict[str, Any]] = {}
        started = time.perf_counter()
        for condition in selected_conditions:
            condition_started = time.perf_counter()
            rows: list[dict[str, Any]] = []
            spec = DEFAULT_CONDITIONS[condition]
            for index, task in enumerate(task_list, start=1):
                if progress:
                    print(f"[eval:{condition}] {index}/{len(task_list)} {task.task_id}", flush=True)
                row = self._run_one(task, condition=condition, modes=spec["modes"], limit=limit)
                rows.append(row)
                details.append(row)
            summaries[condition] = _summarize_rows(rows, elapsed_s=time.perf_counter() - condition_started)
        return {
            "dataset": "dnarag_basic_search_eval",
            "task_count": len(task_list),
            "limit": limit,
            "conditions": {
                name: DEFAULT_CONDITIONS[name]
                for name in selected_conditions
            },
            "summary": summaries,
            "category_summary": _summarize_by_category(details),
            "query_type_summary": _summarize_by_field(details, "query_type"),
            "details": details,
            "elapsed_s": round(time.perf_counter() - started, 3),
        }

    def _run_one(
        self,
        task: BenchmarkTask,
        *,
        condition: str,
        modes: list[str],
        limit: int,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.searcher.search(
            task.query,
            modes=modes,
            limit=limit,
            vector_target=task.vector_target if "vector" in modes else None,
        )
        latency = time.perf_counter() - started
        evidence = list(result.get("evidence") or [])
        rank = first_match_rank(evidence, task.expected)
        bio_evaluable = has_biological_expected(task.expected)
        bio_rank = first_biological_match_rank(evidence, task.expected) if bio_evaluable else None
        return {
            "task_id": task.task_id,
            "category": task.category,
            "condition": condition,
            "query": task.query,
            "query_type": task.query_type,
            "expected": task.expected,
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
            "latency_ms": round(latency * 1000, 3),
            "local_coverage": result.get("local_coverage", 0.0),
            "routes": [trace.get("route") for trace in result.get("retrieval_trace", [])],
            "route_status": {
                str(trace.get("route")): trace.get("status")
                for trace in result.get("retrieval_trace", [])
            },
            "retrieval_trace": result.get("retrieval_trace", []),
            "top_evidence": [_compact_evidence(item) for item in evidence[: min(limit, 10)]],
        }


def load_benchmark(path: str | Path) -> list[BenchmarkTask]:
    tasks: list[BenchmarkTask] = []
    with Path(path).open("rt", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            row = json.loads(line)
            try:
                tasks.append(
                    BenchmarkTask(
                        task_id=str(row["id"]),
                        query=str(row["query"]),
                        category=str(row.get("category") or "unknown"),
                        expected=dict(row.get("expected") or {}),
                        vector_target=_optional_str(row.get("vector_target")),
                        query_type=_optional_str(row.get("query_type")),
                        notes=_optional_str(row.get("notes")),
                    )
                )
            except KeyError as exc:
                raise ValueError(f"Missing required field {exc!s} in {path}:{line_no}") from exc
    return tasks


def first_match_rank(evidence: list[dict[str, Any]], expected: dict[str, Any]) -> int | None:
    for index, item in enumerate(evidence, start=1):
        if matches_expected(item, expected):
            return index
    return None


def first_biological_match_rank(evidence: list[dict[str, Any]], expected: dict[str, Any]) -> int | None:
    if not has_biological_expected(expected):
        return None
    for index, item in enumerate(evidence, start=1):
        if matches_expected(item, expected) or matches_biological_expected(item, expected):
            return index
    return None


def matches_expected(item: dict[str, Any], expected: dict[str, Any]) -> bool:
    metadata = dict(item.get("metadata") or {})
    entity_id = _optional_str(item.get("entity_id"))
    source_id = _optional_str(item.get("source_id"))
    symbol = _optional_str(item.get("symbol") or metadata.get("symbol"))
    title = _optional_str(item.get("title"))
    accession = _optional_str(metadata.get("accession") or source_id)
    if _contains(expected.get("entity_ids"), entity_id):
        return True
    if _contains(expected.get("record_ids"), entity_id):
        return True
    if _contains(expected.get("source_ids"), source_id):
        return True
    if _contains(expected.get("accessions"), accession):
        return True
    if symbol and symbol.upper() in {str(value).upper() for value in _as_list(expected.get("symbols"))}:
        return True
    title_terms = [str(value).lower() for value in _as_list(expected.get("title_contains"))]
    if title and any(term in title.lower() for term in title_terms):
        return True
    return False


def has_biological_expected(expected: dict[str, Any]) -> bool:
    biological = dict(expected.get("biological") or {})
    return any(_as_list(value) for value in biological.values())


def matches_biological_expected(item: dict[str, Any], expected: dict[str, Any]) -> bool:
    biological = dict(expected.get("biological") or {})
    if not biological:
        return False
    candidate = _candidate_biological_fields(item)
    checks = [
        ("gene_ids", "gene_ids", False),
        ("gene_symbols", "gene_symbols", True),
        ("gene_symbols", "protein_gene_names", True),
        ("protein_gene_names", "protein_gene_names", True),
        ("protein_gene_names", "gene_symbols", True),
        ("gene_families", "gene_families", True),
    ]
    for expected_key, candidate_key, casefold in checks:
        expected_values = _as_list(biological.get(expected_key))
        candidate_values = _as_list(candidate.get(candidate_key))
        if _intersects(expected_values, candidate_values, casefold=casefold):
            return True
    return False


def _candidate_biological_fields(item: dict[str, Any]) -> dict[str, list[str]]:
    metadata = dict(item.get("metadata") or {})
    text = " ".join(
        str(value or "")
        for value in [
            item.get("title"),
            item.get("snippet"),
            metadata.get("title"),
            metadata.get("header"),
            metadata.get("description"),
        ]
    )
    gene_symbols = _regex_values(text, r"\bgene_symbol:([^\s\]]+)")
    protein_gene_names = _regex_values(text, r"\bGN=([^\s]+)")
    all_symbols = gene_symbols + protein_gene_names
    return {
        "gene_ids": _regex_values(text, r"\bgene:([A-Za-z0-9_.-]+)"),
        "gene_symbols": gene_symbols,
        "protein_gene_names": protein_gene_names,
        "gene_biotypes": _regex_values(text, r"\bgene_biotype:([^\s\]]+)"),
        "transcript_biotypes": _regex_values(text, r"\btranscript_biotype:([^\s\]]+)"),
        "gene_families": [_gene_family(symbol) for symbol in all_symbols if _gene_family(symbol)],
    }


def _regex_values(text: str, pattern: str) -> list[str]:
    return [match.group(1).strip(";,") for match in re.finditer(pattern, text)]


def _gene_family(symbol: Any) -> str | None:
    text = str(symbol or "").upper()
    if text.startswith(("IGHV", "IGKV", "IGLV", "TRAV", "TRBV", "TRGV", "TRDV")):
        match = re.match(r"^([A-Z]+)", text)
        if match:
            return match.group(1)
    return None


def _summarize_rows(rows: list[dict[str, Any]], *, elapsed_s: float) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "tasks": 0,
            "hit_at_1": 0.0,
            "hit_at_5": 0.0,
            "hit_at_10": 0.0,
            "mrr": 0.0,
            "avg_latency_ms": 0.0,
            "avg_local_coverage": 0.0,
            "elapsed_s": round(elapsed_s, 3),
        }
    summary = {
        "tasks": total,
        "hit_at_1": _mean_bool(rows, "hit_at_1"),
        "hit_at_5": _mean_bool(rows, "hit_at_5"),
        "hit_at_10": _mean_bool(rows, "hit_at_10"),
        "mrr": round(sum(float(row.get("mrr") or 0.0) for row in rows) / total, 4),
        "avg_latency_ms": round(sum(float(row.get("latency_ms") or 0.0) for row in rows) / total, 3),
        "avg_local_coverage": round(sum(float(row.get("local_coverage") or 0.0) for row in rows) / total, 4),
        "elapsed_s": round(elapsed_s, 3),
    }
    bio_rows = [row for row in rows if row.get("bio_evaluable")]
    summary["bio_tasks"] = len(bio_rows)
    if bio_rows:
        summary.update(
            {
                "bio_hit_at_1": _mean_bool(bio_rows, "bio_hit_at_1"),
                "bio_hit_at_5": _mean_bool(bio_rows, "bio_hit_at_5"),
                "bio_hit_at_10": _mean_bool(bio_rows, "bio_hit_at_10"),
                "bio_mrr": round(sum(float(row.get("bio_mrr") or 0.0) for row in bio_rows) / len(bio_rows), 4),
            }
        )
    return summary


def _summarize_by_category(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _summarize_by_field(rows, "category")


def _summarize_by_field(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        condition = str(row.get("condition") or "unknown")
        value = str(row.get(field) or "unknown")
        grouped.setdefault(condition, {}).setdefault(value, []).append(row)
    return {
        condition: {
            value: _summarize_rows(field_rows, elapsed_s=0.0)
            for value, field_rows in sorted(values.items())
        }
        for condition, values in sorted(grouped.items())
    }


def _mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(1 for row in rows if row.get(key)) / len(rows), 4)


def _compact_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": item.get("route"),
        "entity_id": item.get("entity_id"),
        "source_id": item.get("source_id"),
        "symbol": item.get("symbol"),
        "title": item.get("title"),
        "score": item.get("score"),
        "source": item.get("source"),
    }


def _contains(values: Any, candidate: str | None) -> bool:
    if not candidate:
        return False
    return candidate in {str(value) for value in _as_list(values)}


def _intersects(left: Any, right: Any, *, casefold: bool) -> bool:
    left_values = [str(value) for value in _as_list(left) if value not in {None, ""}]
    right_values = [str(value) for value in _as_list(right) if value not in {None, ""}]
    if casefold:
        left_set = {value.upper() for value in left_values}
        right_set = {value.upper() for value in right_values}
    else:
        left_set = set(left_values)
        right_set = set(right_values)
    return bool(left_set & right_set)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)

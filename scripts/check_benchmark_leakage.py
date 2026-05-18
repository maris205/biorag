#!/usr/bin/env python3
"""Audit held-out benchmark leakage against an index FASTA."""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path
from typing import Any, Iterable


def main() -> None:
    args = parse_args()
    benchmark_path = Path(args.benchmark)
    index_fasta = Path(args.index_fasta)
    tasks = load_jsonl(benchmark_path)
    index_records = list(iter_fasta(index_fasta))
    index_accessions = {accession_from_header(header) for header, _sequence in index_records}
    heldout_accessions = sorted(
        {
            str(accession)
            for task in tasks
            for accession in as_list(dict(task.get("expected") or {}).get("heldout_accessions"))
            if accession
        }
    )
    parent_leaks = [accession for accession in heldout_accessions if accession in index_accessions]

    query_substring_leaks: list[dict[str, Any]] = []
    if not args.skip_query_substrings:
        query_substring_leaks = check_query_substrings(tasks, index_records, max_hits=args.max_substring_hits)

    report = {
        "benchmark": str(benchmark_path),
        "index_fasta": str(index_fasta),
        "task_count": len(tasks),
        "index_record_count": len(index_records),
        "heldout_accession_count": len(heldout_accessions),
        "exact_parent_leakage_count": len(parent_leaks),
        "exact_parent_leakage_rate": round(len(parent_leaks) / max(len(heldout_accessions), 1), 6),
        "exact_parent_leaks": parent_leaks[: args.max_reported_leaks],
        "query_substring_checked": not args.skip_query_substrings,
        "query_substring_leakage_count": len(query_substring_leaks),
        "query_substring_leaks": query_substring_leaks[: args.max_reported_leaks],
        "pass": len(parent_leaks) == 0,
        "stop_go": "GO" if len(parent_leaks) == 0 else "STOP",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))


def check_query_substrings(
    tasks: list[dict[str, Any]],
    index_records: list[tuple[str, str]],
    *,
    max_hits: int,
) -> list[dict[str, Any]]:
    normalized_index = [
        (accession_from_header(header), clean_sequence(sequence))
        for header, sequence in index_records
    ]
    leaks: list[dict[str, Any]] = []
    for task in tasks:
        query = clean_sequence(str(task.get("query") or ""))
        if not query:
            continue
        hits: list[str] = []
        for accession, sequence in normalized_index:
            if query in sequence:
                hits.append(accession)
                if len(hits) >= max_hits:
                    break
        if hits:
            leaks.append(
                {
                    "task_id": task.get("id"),
                    "query_type": task.get("query_type"),
                    "query_length": len(query),
                    "index_accessions": hits,
                }
            )
    return leaks


def render_markdown(report: dict[str, Any]) -> str:
    parent_leaks = report.get("exact_parent_leaks") or []
    substring_leaks = report.get("query_substring_leaks") or []
    lines = [
        "# Held-Out Benchmark Leakage Report",
        "",
        f"- Benchmark: `{report['benchmark']}`",
        f"- Index FASTA: `{report['index_fasta']}`",
        f"- Tasks: {report['task_count']}",
        f"- Index records: {report['index_record_count']}",
        f"- Held-out accessions: {report['heldout_accession_count']}",
        f"- Stop/go: **{report['stop_go']}**",
        "",
        "| Check | Count | Rate | Interpretation |",
        "| --- | ---: | ---: | --- |",
        (
            "| Exact held-out parent accession present in index | "
            f"{report['exact_parent_leakage_count']} | "
            f"{report['exact_parent_leakage_rate']:.6f} | "
            "Must be 0 for held-out evaluation |"
        ),
        (
            "| Query exact substring present in indexed records | "
            f"{report['query_substring_leakage_count']} | n/a | "
            "Near-duplicate/conserved-fragment warning, not automatic failure |"
        ),
        "",
    ]
    if parent_leaks:
        lines.extend(["## Exact Parent Leaks", ""])
        lines.extend(f"- `{accession}`" for accession in parent_leaks)
        lines.append("")
    if substring_leaks:
        lines.extend(["## Query Substring Warnings", ""])
        for item in substring_leaks:
            accessions = ", ".join(f"`{value}`" for value in item.get("index_accessions", []))
            lines.append(
                f"- `{item.get('task_id')}` ({item.get('query_type')}, "
                f"{item.get('query_length')} aa/nt): {accessions}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("rt", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}") from exc
    return rows


def iter_fasta(path: Path) -> Iterable[tuple[str, str]]:
    if path.suffix == ".gz":
        handle_factory = lambda: gzip.open(path, "rt", encoding="utf-8", errors="replace")
    else:
        handle_factory = lambda: path.open("rt", encoding="utf-8", errors="replace")
    with handle_factory() as handle:
        header = ""
        chunks: list[str] = []
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if header and chunks:
                    yield header, "".join(chunks)
                header = line[1:]
                chunks = []
            elif line:
                chunks.append(line)
        if header and chunks:
            yield header, "".join(chunks)


def accession_from_header(header: str) -> str:
    token = header.split()[0]
    if "|" in token:
        parts = token.split("|")
        if len(parts) > 1:
            return parts[1]
    return token


def clean_sequence(sequence: str) -> str:
    return "".join(ch for ch in str(sequence or "").upper() if ch.isalpha() or ch == "*")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check held-out benchmark leakage")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--index-fasta", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--skip-query-substrings", action="store_true")
    parser.add_argument("--max-substring-hits", type=int, default=5)
    parser.add_argument("--max-reported-leaks", type=int, default=50)
    return parser.parse_args()


if __name__ == "__main__":
    main()

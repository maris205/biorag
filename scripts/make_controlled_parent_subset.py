#!/usr/bin/env python3
"""Build a controlled FASTA subset for held-out parent-fragment evaluation.

The subset keeps indexed records that share benchmark gene labels with held-out
queries, then adds random background records. This makes small vector-index
experiments interpretable: failures are less likely to be caused by a subset
that simply omitted all biologically matching candidates.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class FastaRecord:
    header: str
    sequence: str
    accession: str
    gene_name: str | None


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    tasks = load_jsonl(Path(args.benchmark))
    heldout_accessions = {
        str(accession)
        for task in tasks
        for accession in as_list(dict(task.get("expected") or {}).get("heldout_accessions"))
        if accession
    }
    query_genes = {
        gene
        for task in tasks
        for gene in task_genes(task)
        if gene
    }
    if not query_genes:
        raise SystemExit(f"No gene labels found in benchmark: {args.benchmark}")

    positives: list[FastaRecord] = []
    background: list[FastaRecord] = []
    gene_to_accessions: dict[str, list[str]] = {gene: [] for gene in query_genes}
    for record in iter_fasta_records(Path(args.index_fasta)):
        gene = normalize_gene(record.gene_name)
        if record.accession in heldout_accessions:
            continue
        if gene and gene in query_genes:
            positives.append(record)
            gene_to_accessions.setdefault(gene, []).append(record.accession)
        else:
            background.append(record)

    rng.shuffle(background)
    target_count = max(int(args.target_count), len(positives))
    selected = positives + background[: max(target_count - len(positives), 0)]
    rng.shuffle(selected)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_fasta(output, selected)

    task_coverage = [
        {
            "task_id": task.get("id"),
            "genes": sorted(task_genes(task)),
            "positive_accessions": sorted(
                {
                    accession
                    for gene in task_genes(task)
                    for accession in gene_to_accessions.get(gene, [])
                }
            ),
        }
        for task in tasks
    ]
    covered_tasks = [item for item in task_coverage if item["positive_accessions"]]
    report = {
        "benchmark": args.benchmark,
        "index_fasta": args.index_fasta,
        "output": str(output),
        "seed": args.seed,
        "target_count": args.target_count,
        "selected_records": len(selected),
        "positive_records": len(positives),
        "background_records": len(selected) - len(positives),
        "query_genes": len(query_genes),
        "tasks": len(tasks),
        "tasks_with_positive_candidates": len(covered_tasks),
        "task_positive_coverage": round(len(covered_tasks) / max(len(tasks), 1), 6),
        "exact_heldout_parent_leakage": sorted(
            {record.accession for record in selected if record.accession in heldout_accessions}
        ),
        "gene_positive_counts": {
            gene: len(accessions)
            for gene, accessions in sorted(gene_to_accessions.items())
            if accessions
        },
        "uncovered_tasks": [
            {
                "task_id": item["task_id"],
                "genes": item["genes"],
            }
            for item in task_coverage
            if not item["positive_accessions"]
        ],
    }

    if args.report_json:
        report_json = Path(args.report_json)
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.report_md:
        report_md = Path(args.report_md)
        report_md.parent.mkdir(parents=True, exist_ok=True)
        report_md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def task_genes(task: dict[str, Any]) -> set[str]:
    biological = dict(dict(task.get("expected") or {}).get("biological") or {})
    genes: set[str] = set()
    for key in ("protein_gene_names", "gene_symbols"):
        genes.update(normalize_gene(value) for value in as_list(biological.get(key)))
    return {gene for gene in genes if gene}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Controlled Held-Out Parent Subset",
        "",
        f"- Benchmark: `{report['benchmark']}`",
        f"- Source index FASTA: `{report['index_fasta']}`",
        f"- Output FASTA: `{report['output']}`",
        f"- Selected records: {report['selected_records']}",
        f"- Positive same-gene records: {report['positive_records']}",
        f"- Random background records: {report['background_records']}",
        f"- Query genes: {report['query_genes']}",
        f"- Task positive-candidate coverage: {report['tasks_with_positive_candidates']}/{report['tasks']} ({report['task_positive_coverage']:.3f})",
        f"- Exact held-out parent leakage: {len(report['exact_heldout_parent_leakage'])}",
        "",
    ]
    uncovered = report.get("uncovered_tasks") or []
    if uncovered:
        lines.extend(["## Uncovered Tasks", ""])
        for item in uncovered[:50]:
            genes = ", ".join(f"`{gene}`" for gene in item.get("genes", []))
            lines.append(f"- `{item.get('task_id')}`: {genes}")
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


def iter_fasta_records(path: Path) -> Iterable[FastaRecord]:
    for header, sequence in iter_fasta(path):
        yield FastaRecord(
            header=header,
            sequence=clean_sequence(sequence),
            accession=accession_from_header(header),
            gene_name=match_header_field(header, "GN") or match_header_key_value(header, "gene_symbol"),
        )


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


def write_fasta(path: Path, records: list[FastaRecord]) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(f">{record.header}\n")
            for start in range(0, len(record.sequence), 80):
                handle.write(record.sequence[start : start + 80] + "\n")


def accession_from_header(header: str) -> str:
    token = header.split()[0]
    if "|" in token:
        parts = token.split("|")
        if len(parts) > 1:
            return parts[1]
    return token


def match_header_field(header: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}=([^\s]+)", header)
    return match.group(1).strip(";,") if match else None


def match_header_key_value(header: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}:([^\s]+)", header)
    return match.group(1).strip(";,") if match else None


def clean_sequence(sequence: str) -> str:
    return "".join(ch for ch in str(sequence or "").upper() if ch.isalpha() or ch == "*")


def normalize_gene(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a controlled same-gene + background FASTA subset")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--index-fasta", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target-count", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260516)
    parser.add_argument("--report-json", default=None)
    parser.add_argument("--report-md", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()

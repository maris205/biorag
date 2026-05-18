#!/usr/bin/env python3
"""Build a partitioned BioRAG annotation dataset from Standard KB artifacts.

The output is a JSONL-based dataset with two layers:

- corpus: retrievable RAG records from Open-Rosalind Standard and selected
  vector/sequence extensions.
- tasks: annotated queries with expected entity/source/accession labels and
  optional links back to exported corpus records.

The default export is intentionally modest for inspection. Use larger limits or
``--chroma-limit 0`` when building the full paper artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import as_jsonable, load_config
from dnarag.localdb.standard import StandardDocument, StandardKB
from dnarag.retrieval.sequence import detect_sequence
from dnarag.retrieval.vector_db import ChromaVectorDB


DATASET_VERSION = "0.1.0"
DEFAULT_TASKS = (
    "benchmarks/basic_search.jsonl,"
    "benchmarks/sequence_search_100_seed20260516_bio.jsonl"
)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    output_dir = Path(args.output)
    reset_output(output_dir, reset=args.reset)
    corpus_dir = output_dir / "corpus"
    tasks_dir = output_dir / "tasks"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir.mkdir(parents=True, exist_ok=True)

    lookup = CorpusLookup()
    corpus_counts: dict[str, Any] = {}
    task_counts: dict[str, Any] = {}

    standard = StandardKB(config.sqlite_path, config.manifest_path)
    standard_path = corpus_dir / "standard_text.jsonl"
    standard_counts = export_standard_corpus(
        standard,
        output=standard_path,
        lookup=lookup,
        limit=args.standard_limit,
        kinds=split_csv(args.standard_kinds),
    )
    corpus_counts["standard_text"] = standard_counts

    chroma = ChromaVectorDB(config.vector_dir)
    for target in split_csv(args.chroma_targets):
        target_path = corpus_dir / f"{safe_name(target)}.jsonl"
        corpus_counts[target] = export_chroma_corpus(
            chroma,
            target=target,
            output=target_path,
            lookup=lookup,
            limit=args.chroma_limit,
            batch_size=args.chroma_batch_size,
        )

    task_files = [Path(path) for path in split_csv(args.tasks)]
    task_path = tasks_dir / "rag_tasks.jsonl"
    task_counts = export_tasks(
        task_files,
        output=task_path,
        lookup=lookup,
        split_policy=args.task_split_policy,
    )

    schema_path = output_dir / "SCHEMA.md"
    schema_path.write_text(render_schema(), encoding="utf-8")
    manifest = {
        "dataset": "biorag_standard",
        "version": DATASET_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "description": (
            "Partitioned BioRAG annotation dataset from Open-Rosalind Standard, "
            "OmniGene sequence-vector extensions, BLAST-ready identifiers, and "
            "retrieval benchmark labels."
        ),
        "config": as_jsonable(config),
        "source_status": {
            "standard": standard.status(),
            "chroma": chroma.status(),
        },
        "files": {
            "corpus_dir": str(corpus_dir),
            "tasks": str(task_path),
            "schema": str(schema_path),
        },
        "corpus": corpus_counts,
        "tasks": task_counts,
        "annotation_policy": annotation_policy(),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_dir), "manifest": str(manifest_path), "corpus": corpus_counts, "tasks": task_counts}, indent=2, ensure_ascii=False))


def export_standard_corpus(
    standard: StandardKB,
    *,
    output: Path,
    lookup: "CorpusLookup",
    limit: int,
    kinds: list[str],
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wt", encoding="utf-8") as handle:
        for doc in standard.iter_documents(limit=limit, kinds=kinds or None):
            record = standard_doc_to_corpus(doc)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            lookup.add(record)
            counts[str(record["partition"])] += 1
    return {"file": str(output), "records": sum(counts.values()), "partitions": dict(sorted(counts.items()))}


def standard_doc_to_corpus(doc: StandardDocument) -> dict[str, Any]:
    labels: dict[str, list[str]] = {}
    if doc.kind == "hgnc_gene":
        labels["gene_ids"] = [doc.source_id]
        if doc.symbol:
            labels["gene_symbols"] = [doc.symbol]
    text = compact_parts(
        [
            f"[TYPE={doc.kind}]",
            doc.symbol,
            doc.name,
            doc.organism,
            doc.description,
        ]
    )
    return {
        "id": f"standard:{doc.entity_id}",
        "record_id": doc.entity_id,
        "entity_id": doc.entity_id,
        "source_id": doc.source_id,
        "accession": None,
        "symbol": doc.symbol,
        "name": doc.name,
        "modality": "text_knowledge",
        "partition": f"standard/{doc.kind}",
        "kind": doc.kind,
        "source": doc.source,
        "source_url": doc.source_url,
        "organism": doc.organism,
        "text": text,
        "labels": labels,
        "metadata": doc.payload,
    }


def export_chroma_corpus(
    chroma: ChromaVectorDB,
    *,
    target: str,
    output: Path,
    lookup: "CorpusLookup",
    limit: int,
    batch_size: int,
) -> dict[str, Any]:
    info = chroma.collection_info(target)
    if not info or int(info.get("count") or 0) <= 0:
        return {"file": str(output), "target": target, "status": "missing_or_empty", "records": 0}
    collection = chroma._collection(target)
    total = int(info.get("count") or 0)
    requested = total if int(limit) <= 0 else min(int(limit), total)
    counts: Counter[str] = Counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wt", encoding="utf-8") as handle:
        for offset in range(0, requested, max(int(batch_size), 1)):
            current_limit = min(max(int(batch_size), 1), requested - offset)
            result = collection.get(
                limit=current_limit,
                offset=offset,
                include=["metadatas", "documents"],
            )
            for row in chroma_records_from_get(result):
                record = chroma_row_to_corpus(target, row)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                lookup.add(record)
                counts[str(record["partition"])] += 1
    return {
        "file": str(output),
        "target": target,
        "status": "ok",
        "records": sum(counts.values()),
        "available_records": total,
        "partitions": dict(sorted(counts.items())),
        "metadata": dict(info.get("metadata") or {}),
    }


def chroma_records_from_get(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    ids = list(result.get("ids") or [])
    metadatas = list(result.get("metadatas") or [])
    documents = list(result.get("documents") or [])
    rows: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        raw = dict(metadata or {})
        try:
            nested = json.loads(str(raw.get("metadata_json") or "{}"))
        except json.JSONDecodeError:
            nested = {}
        raw.update(nested if isinstance(nested, dict) else {})
        rows.append(
            {
                "id": ids[index] if index < len(ids) else "",
                "metadata": raw,
                "document": documents[index] if index < len(documents) else None,
            }
        )
    return rows


def chroma_row_to_corpus(target: str, row: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(row.get("metadata") or {})
    record_id = str(metadata.get("record_id") or row.get("id") or "")
    source_id = optional_str(metadata.get("source_id") or metadata.get("accession"))
    parent_id = optional_str(metadata.get("parent_record_id"))
    entity_id = parent_id or record_id or f"{target}:{row.get('id')}"
    modality = modality_for_target(target, metadata)
    text = str(row.get("document") or "")
    labels = extract_biological_labels(metadata)
    return {
        "id": f"chroma:{target}:{row.get('id')}",
        "record_id": record_id,
        "entity_id": entity_id,
        "source_id": source_id,
        "accession": optional_str(metadata.get("accession") or source_id),
        "symbol": optional_str(metadata.get("symbol")),
        "name": optional_str(metadata.get("header") or metadata.get("title")),
        "modality": modality,
        "partition": f"vector/{target}",
        "kind": optional_str(metadata.get("kind") or target),
        "source": optional_str(metadata.get("source") or f"Chroma:{target}"),
        "source_url": optional_str(metadata.get("source_url")),
        "organism": optional_str(metadata.get("organism")),
        "text": text,
        "labels": labels,
        "metadata": {
            key: value
            for key, value in metadata.items()
            if key not in {"metadata_json"} and value not in {None, ""}
        },
    }


def export_tasks(
    task_files: list[Path],
    *,
    output: Path,
    lookup: "CorpusLookup",
    split_policy: str,
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    positive_ref_counts: Counter[str] = Counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wt", encoding="utf-8") as handle:
        for task_file in task_files:
            if not task_file.exists():
                continue
            with task_file.open("rt", encoding="utf-8") as source:
                for line_no, line in enumerate(source, start=1):
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    raw = json.loads(line)
                    task = task_to_annotation(
                        raw,
                        source_file=task_file,
                        line_no=line_no,
                        lookup=lookup,
                        split_policy=split_policy,
                    )
                    handle.write(json.dumps(task, ensure_ascii=False) + "\n")
                    counts[str(task["partition"])] += 1
                    split_counts[str(task["split"])] += 1
                    source_counts[task_file.name] += 1
                    positive_ref_counts[str(bool(task["positive_corpus_refs"]))] += 1
    total = sum(counts.values())
    return {
        "file": str(output),
        "records": total,
        "partitions": dict(sorted(counts.items())),
        "splits": dict(sorted(split_counts.items())),
        "source_files": dict(sorted(source_counts.items())),
        "with_positive_corpus_refs": positive_ref_counts.get("True", 0),
        "without_positive_corpus_refs": positive_ref_counts.get("False", 0),
    }


def task_to_annotation(
    raw: dict[str, Any],
    *,
    source_file: Path,
    line_no: int,
    lookup: "CorpusLookup",
    split_policy: str,
) -> dict[str, Any]:
    task_id = str(raw.get("id") or f"{source_file.stem}:{line_no}")
    expected = dict(raw.get("expected") or {})
    query = str(raw.get("query") or "")
    seq = detect_sequence(query)
    positives = lookup.match_expected(expected)
    return {
        "id": task_id,
        "split": task_split(task_id, policy=split_policy),
        "partition": str(raw.get("category") or "unknown"),
        "query_type": optional_str(raw.get("query_type")),
        "query": query,
        "query_modality": query_modality(seq),
        "target_partitions": target_partitions(raw, seq),
        "expected": expected,
        "positive_corpus_refs": positives,
        "label_type": label_type(expected),
        "source_benchmark": source_file.name,
        "source_line": line_no,
        "notes": optional_str(raw.get("notes")),
    }


class CorpusLookup:
    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], list[str]] = defaultdict(list)

    def add(self, record: Mapping[str, Any]) -> None:
        record_id = str(record.get("id") or "")
        for key_name in ("id", "record_id", "entity_id", "source_id", "accession", "symbol"):
            value = record.get(key_name)
            if value in {None, ""}:
                continue
            self.by_key[(key_name, str(value))].append(record_id)
            self.by_key[(key_name, str(value).upper())].append(record_id)

    def match_expected(self, expected: Mapping[str, Any], *, limit: int = 20) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        mappings = [
            ("entity_ids", "entity_id"),
            ("record_ids", "record_id"),
            ("source_ids", "source_id"),
            ("accessions", "accession"),
            ("symbols", "symbol"),
        ]
        for expected_key, lookup_key in mappings:
            for value in as_list(expected.get(expected_key)):
                for candidate in [str(value), str(value).upper()]:
                    for corpus_id in self.by_key.get((lookup_key, candidate), []):
                        item = (expected_key, str(value), corpus_id)
                        if item in seen:
                            continue
                        seen.add(item)
                        refs.append({"match_field": expected_key, "match_value": str(value), "corpus_id": corpus_id})
                        if len(refs) >= limit:
                            return refs
        return refs


def annotation_policy() -> dict[str, Any]:
    return {
        "positive_labels": [
            "entity_ids",
            "source_ids",
            "accessions",
            "symbols",
            "title_contains",
            "biological.gene_ids",
            "biological.gene_symbols",
            "biological.protein_gene_names",
            "biological.gene_families",
        ],
        "negative_labels": "not explicitly generated in v0.1; use unjudged corpus records as unknown, not negative",
        "retrieval_use": (
            "Use corpus records for BioRAG indexing. Use tasks/rag_tasks.jsonl for "
            "retrieval and agent-grounding evaluation."
        ),
        "blast_role": "BLAST is a verification/reranking route, not a target to replace.",
    }


def render_schema() -> str:
    return """# BioRAG-Standard Dataset Schema

## Corpus JSONL

Each row in `corpus/*.jsonl` is a retrievable RAG record.

Required fields:

- `id`: stable dataset-local corpus row ID
- `record_id`: source record ID
- `entity_id`: biological entity or parent sequence ID
- `source_id`: source accession or database ID when available
- `modality`: `text_knowledge`, `protein_sequence`, `dna_sequence`, or `mixed`
- `partition`: corpus partition, for example `standard/hgnc_gene` or `vector/protein_sequence_window`
- `text`: retrievable text or sequence payload
- `labels`: extracted biological labels such as gene symbols, gene IDs, families, and biotypes
- `metadata`: source-specific metadata used for traceability

## Task JSONL

`tasks/rag_tasks.jsonl` stores annotated retrieval queries.

Required fields:

- `id`: task ID
- `split`: deterministic dataset split
- `partition`: task family, such as `gene_lookup`, `pathway_lookup`, `protein_sequence`, or `dna_sequence`
- `query`: user/query string
- `query_modality`: text, DNA, protein, or mixed
- `expected`: exact and biological positive labels
- `positive_corpus_refs`: exported corpus rows matching exact expected labels when present in this export
- `label_type`: `exact_id`, `biological`, or `mixed`

Rows without `positive_corpus_refs` can still be valid evaluation rows when the
positive target exists in BLAST or a full corpus export but was not included in a
small sample export.
"""


def extract_biological_labels(metadata: Mapping[str, Any]) -> dict[str, list[str]]:
    header = str(metadata.get("header") or metadata.get("name") or metadata.get("title") or "")
    result: dict[str, list[str]] = {}
    for key, pattern in [
        ("gene_ids", r"\bgene:([A-Za-z0-9_.-]+)"),
        ("gene_symbols", r"\bgene_symbol:([^\s\]]+)"),
        ("gene_biotypes", r"\bgene_biotype:([^\s\]]+)"),
        ("transcript_biotypes", r"\btranscript_biotype:([^\s\]]+)"),
        ("protein_gene_names", r"\bGN=([^\s]+)"),
    ]:
        values = sorted({match.group(1).strip(";,") for match in re.finditer(pattern, header)})
        if values:
            result[key] = values
    family_sources = result.get("gene_symbols", []) + result.get("protein_gene_names", [])
    families = sorted({gene_family(value) for value in family_sources if gene_family(value)})
    if families:
        result["gene_families"] = families
    return result


def gene_family(symbol: str) -> str | None:
    text = str(symbol or "").upper()
    if text.startswith(("IGHV", "IGKV", "IGLV", "TRAV", "TRBV", "TRGV", "TRDV")):
        match = re.match(r"^([A-Z]+)", text)
        if match:
            return match.group(1)
    return None


def modality_for_target(target: str, metadata: Mapping[str, Any]) -> str:
    kind = str(metadata.get("kind") or target).lower()
    alphabet = str(metadata.get("alphabet") or "").lower()
    if alphabet == "dna" or "dna" in kind or "cdna" in kind:
        return "dna_sequence"
    if alphabet == "protein" or "protein" in kind or "peptide" in kind:
        return "protein_sequence"
    if target == "mixed":
        return "mixed"
    return "text_knowledge"


def query_modality(seq: Any) -> str:
    if seq is None:
        return "text"
    if seq.alphabet == "dna":
        return "dna_sequence"
    if seq.alphabet == "protein":
        return "protein_sequence"
    return str(seq.sequence_type)


def target_partitions(raw: Mapping[str, Any], seq: Any) -> list[str]:
    vector_target = optional_str(raw.get("vector_target"))
    if vector_target:
        return [f"vector/{vector_target}"]
    category = str(raw.get("category") or "")
    if category == "gene_lookup":
        return ["standard/hgnc_gene"]
    if category == "pathway_lookup":
        return ["standard/reactome_pathway"]
    if seq is not None and seq.alphabet == "dna":
        return ["vector/dna_sequence_window", "blast/ensembl_cdna"]
    if seq is not None and seq.alphabet == "protein":
        return ["vector/protein_sequence_window", "blast/swissprot"]
    return ["standard"]


def label_type(expected: Mapping[str, Any]) -> str:
    has_exact = any(as_list(expected.get(key)) for key in ("entity_ids", "record_ids", "source_ids", "accessions", "symbols"))
    has_bio = any(as_list(value) for value in dict(expected.get("biological") or {}).values())
    if has_exact and has_bio:
        return "mixed"
    if has_bio:
        return "biological"
    return "exact_id" if has_exact else "weak"


def task_split(task_id: str, *, policy: str) -> str:
    if policy == "all_test":
        return "test"
    digest = hashlib.sha1(task_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def compact_parts(parts: Iterable[Any]) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value)).strip("_") or "partition"


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def reset_output(output_dir: Path, *, reset: bool) -> None:
    if output_dir.exists() and reset:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a partitioned BioRAG annotation dataset")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--output", default="data/biorag_standard_v0")
    parser.add_argument("--reset", action="store_true", help="Remove the existing output directory before writing")
    parser.add_argument("--standard-limit", type=int, default=0, help="0 exports all Standard documents")
    parser.add_argument("--standard-kinds", default="", help="Optional comma-separated Standard document kinds")
    parser.add_argument(
        "--chroma-targets",
        default="protein_sequence_window,dna_sequence_window,mixed",
        help="Comma-separated Chroma targets to export as corpus partitions",
    )
    parser.add_argument("--chroma-limit", type=int, default=1000, help="Per-target Chroma rows; 0 exports all rows")
    parser.add_argument("--chroma-batch-size", type=int, default=1000)
    parser.add_argument("--tasks", default=DEFAULT_TASKS, help="Comma-separated benchmark JSONL files")
    parser.add_argument("--task-split-policy", choices=["hash", "all_test"], default="hash")
    return parser.parse_args()


if __name__ == "__main__":
    main()

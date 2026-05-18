#!/usr/bin/env python3
"""Evaluate biological-label enrichment in sequence vector neighborhoods."""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.retrieval.vector_db import ChromaVectorDB


IDENTITY_LABELS = ("gene_ids", "gene_symbols", "protein_gene_names", "gene_families")
MATCH_TYPES = ("gene_id", "gene_symbol", "gene_family", "biotype", "any_identity")


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    config = load_config(args.config)
    db = ChromaVectorDB(config.vector_dir)
    started = time.perf_counter()
    targets = [target.strip() for target in args.targets.split(",") if target.strip()]
    result = {
        "dataset": "dnarag_vector_neighborhood_enrichment",
        "config": args.config,
        "seed": args.seed,
        "targets": targets,
        "top_k": args.top_k,
        "query_results": args.query_results,
        "anchor_count": args.anchor_count,
        "metadata_limit": args.metadata_limit,
        "exclude_same_parent": not args.include_same_parent,
        "dedupe_parent": not args.keep_parent_duplicates,
        "target_summary": {},
        "details": {},
    }
    for target in targets:
        target_result = evaluate_target(
            db,
            target,
            anchor_count=args.anchor_count,
            top_k=args.top_k,
            query_results=args.query_results,
            metadata_limit=args.metadata_limit,
            rng=rng,
            exclude_same_parent=not args.include_same_parent,
            dedupe_parent=not args.keep_parent_duplicates,
        )
        result["target_summary"][target] = target_result["summary"]
        if not args.summary_only:
            result["details"][target] = target_result["details"]
    result["elapsed_s"] = round(time.perf_counter() - started, 3)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2, ensure_ascii=False))


def evaluate_target(
    db: ChromaVectorDB,
    target: str,
    *,
    anchor_count: int,
    top_k: int,
    query_results: int,
    metadata_limit: int,
    rng: random.Random,
    exclude_same_parent: bool,
    dedupe_parent: bool,
) -> dict[str, Any]:
    info = db.collection_info(target)
    if not info or int(info.get("count") or 0) == 0:
        raise SystemExit(f"Missing or empty Chroma collection: {target}")
    collection = db._collection(target)
    count = int(info["count"])
    metadata_count = min(max(int(metadata_limit), 1), count)
    records = load_records(collection, limit=metadata_count)
    labeled = [record for record in records if has_identity_labels(record["labels"])]
    if not labeled:
        raise SystemExit(f"No biological labels found in loaded records for {target}")
    anchors = rng.sample(labeled, min(max(int(anchor_count), 1), len(labeled)))
    rows: list[dict[str, Any]] = []
    for base_anchor in anchors:
        anchor = get_record(collection, str(base_anchor["id"]), include_embedding=True)
        if anchor.get("embedding") is None or not has_identity_labels(anchor["labels"]):
            continue
        vector_neighbors = vector_neighbors_for_anchor(
            collection,
            anchor,
            top_k=top_k,
            query_results=query_results,
            exclude_same_parent=exclude_same_parent,
            dedupe_parent=dedupe_parent,
        )
        random_neighbors = random_neighbors_for_anchor(
            records,
            anchor,
            top_k=top_k,
            rng=rng,
            exclude_same_parent=exclude_same_parent,
            dedupe_parent=dedupe_parent,
        )
        rows.append(score_anchor(anchor, vector_neighbors, random_neighbors, top_k=top_k))
    return {
        "summary": summarize_target(
            target,
            info=info,
            loaded_records=len(records),
            labeled_records=len(labeled),
            rows=rows,
            top_k=top_k,
        ),
        "details": rows,
    }


def load_records(collection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    batch_size = 5000
    target = max(int(limit), 1)
    for offset in range(0, target, batch_size):
        current_limit = min(batch_size, target - offset)
        result = collection.get(limit=current_limit, offset=offset, include=["metadatas", "documents"])
        batch = records_from_chroma_get(result)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < current_limit:
            break
    return rows


def get_record(collection: Any, item_id: str, *, include_embedding: bool) -> dict[str, Any]:
    include = ["metadatas", "documents"]
    if include_embedding:
        include.append("embeddings")
    result = collection.get(ids=[item_id], include=include)
    records = records_from_chroma_get(result)
    if not records:
        raise KeyError(f"Missing Chroma record: {item_id}")
    return records[0]


def vector_neighbors_for_anchor(
    collection: Any,
    anchor: dict[str, Any],
    *,
    top_k: int,
    query_results: int,
    exclude_same_parent: bool,
    dedupe_parent: bool,
) -> list[dict[str, Any]]:
    embedding = np.asarray(anchor["embedding"], dtype=np.float32)
    result = collection.query(
        query_embeddings=[embedding.tolist()],
        n_results=max(int(query_results), int(top_k) + 1),
        include=["metadatas", "documents", "distances"],
    )
    candidates = records_from_chroma_query(result)
    return filter_neighbors(
        candidates,
        anchor,
        top_k=top_k,
        exclude_same_parent=exclude_same_parent,
        dedupe_parent=dedupe_parent,
    )


def random_neighbors_for_anchor(
    records: list[dict[str, Any]],
    anchor: dict[str, Any],
    *,
    top_k: int,
    rng: random.Random,
    exclude_same_parent: bool,
    dedupe_parent: bool,
) -> list[dict[str, Any]]:
    shuffled = list(records)
    rng.shuffle(shuffled)
    return filter_neighbors(
        shuffled,
        anchor,
        top_k=top_k,
        exclude_same_parent=exclude_same_parent,
        dedupe_parent=dedupe_parent,
    )


def filter_neighbors(
    candidates: Iterable[dict[str, Any]],
    anchor: dict[str, Any],
    *,
    top_k: int,
    exclude_same_parent: bool,
    dedupe_parent: bool,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_parents: set[str] = set()
    anchor_id = str(anchor.get("id") or "")
    anchor_parent = str(anchor.get("parent_record_id") or anchor.get("record_id") or "")
    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "")
        candidate_parent = str(candidate.get("parent_record_id") or candidate.get("record_id") or "")
        if candidate_id and candidate_id == anchor_id:
            continue
        if exclude_same_parent and candidate_parent and candidate_parent == anchor_parent:
            continue
        if dedupe_parent and candidate_parent:
            if candidate_parent in seen_parents:
                continue
            seen_parents.add(candidate_parent)
        selected.append(candidate)
        if len(selected) >= top_k:
            break
    return selected


def score_anchor(
    anchor: dict[str, Any],
    vector_neighbors: list[dict[str, Any]],
    random_neighbors: list[dict[str, Any]],
    *,
    top_k: int,
) -> dict[str, Any]:
    k_values = [value for value in (1, 5, 10, top_k) if value <= top_k]
    k_values = sorted(set(k_values))
    scores: dict[str, Any] = {}
    for match_type in MATCH_TYPES:
        if not anchor_has_match_type(anchor["labels"], match_type):
            continue
        scores[match_type] = {}
        for k in k_values:
            vector_flags = [labels_match(match_type, anchor["labels"], item["labels"]) for item in vector_neighbors[:k]]
            random_flags = [labels_match(match_type, anchor["labels"], item["labels"]) for item in random_neighbors[:k]]
            scores[match_type][str(k)] = {
                "vector_hit": any(vector_flags),
                "random_hit": any(random_flags),
                "vector_precision": round(sum(vector_flags) / max(len(vector_flags), 1), 6),
                "random_precision": round(sum(random_flags) / max(len(random_flags), 1), 6),
                "vector_count": len(vector_flags),
                "random_count": len(random_flags),
            }
    return {
        "anchor_id": anchor.get("id"),
        "parent_record_id": anchor.get("parent_record_id") or anchor.get("record_id"),
        "labels": anchor["labels"],
        "scores": scores,
        "top_vector_neighbors": compact_neighbors(vector_neighbors),
        "top_random_neighbors": compact_neighbors(random_neighbors),
    }


def summarize_target(
    target: str,
    *,
    info: dict[str, Any],
    loaded_records: int,
    labeled_records: int,
    rows: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "target": target,
        "collection_count": int(info.get("count") or 0),
        "loaded_records": loaded_records,
        "labeled_records": labeled_records,
        "anchors_evaluated": len(rows),
        "label_coverage": label_coverage(rows),
        "match_summary": {},
    }
    k_values = [value for value in (1, 5, 10, top_k) if value <= top_k]
    for match_type in MATCH_TYPES:
        eligible = [row for row in rows if match_type in row.get("scores", {})]
        if not eligible:
            continue
        summary["match_summary"][match_type] = {"anchors": len(eligible)}
        for k in sorted(set(k_values)):
            key = str(k)
            vector_hits = [row["scores"][match_type][key]["vector_hit"] for row in eligible if key in row["scores"][match_type]]
            random_hits = [row["scores"][match_type][key]["random_hit"] for row in eligible if key in row["scores"][match_type]]
            vector_precision = [
                row["scores"][match_type][key]["vector_precision"]
                for row in eligible
                if key in row["scores"][match_type]
            ]
            random_precision = [
                row["scores"][match_type][key]["random_precision"]
                for row in eligible
                if key in row["scores"][match_type]
            ]
            vector_p = mean(vector_precision)
            random_p = mean(random_precision)
            summary["match_summary"][match_type][f"hit_at_{k}"] = {
                "vector": mean_bool(vector_hits),
                "random": mean_bool(random_hits),
                "delta": round(mean_bool(vector_hits) - mean_bool(random_hits), 4),
            }
            summary["match_summary"][match_type][f"precision_at_{k}"] = {
                "vector": vector_p,
                "random": random_p,
                "delta": round(vector_p - random_p, 4),
                "enrichment": enrichment(vector_p, random_p),
            }
    return summary


def label_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    coverage = {key: 0 for key in (*IDENTITY_LABELS, "gene_biotypes", "transcript_biotypes")}
    for row in rows:
        labels = dict(row.get("labels") or {})
        for key in coverage:
            if labels.get(key):
                coverage[key] += 1
    return coverage


def records_from_chroma_get(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []
    embeddings = result.get("embeddings")
    records: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        record = record_from_metadata(
            ids[index] if index < len(ids) else "",
            metadata or {},
            documents[index] if index < len(documents) else None,
        )
        if embeddings is not None and index < len(embeddings):
            record["embedding"] = np.asarray(embeddings[index], dtype=np.float32).tolist()
        records.append(record)
    return records


def records_from_chroma_query(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = (result.get("ids") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    records: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        record = record_from_metadata(
            ids[index] if index < len(ids) else "",
            metadata or {},
            documents[index] if index < len(documents) else None,
        )
        if index < len(distances):
            record["score"] = round(1.0 - float(distances[index]), 6)
        records.append(record)
    return records


def record_from_metadata(item_id: str, raw_metadata: dict[str, Any], document: str | None) -> dict[str, Any]:
    metadata = dict(raw_metadata)
    try:
        nested = json.loads(str(metadata.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        nested = {}
    metadata.update(nested)
    record_id = str(metadata.get("record_id") or raw_metadata.get("record_id") or item_id)
    parent_record_id = str(metadata.get("parent_record_id") or record_id)
    labels = extract_biological_labels(metadata)
    return {
        "id": item_id,
        "record_id": record_id,
        "parent_record_id": parent_record_id,
        "metadata": metadata,
        "document": document,
        "labels": labels,
        "score": None,
    }


def extract_biological_labels(metadata: dict[str, Any]) -> dict[str, list[str]]:
    header = str(metadata.get("header") or "")
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


def labels_match(match_type: str, left: dict[str, list[str]], right: dict[str, list[str]]) -> bool:
    if match_type == "gene_id":
        return intersects(left.get("gene_ids"), right.get("gene_ids"), casefold=False)
    if match_type == "gene_symbol":
        return intersects(symbol_values(left), symbol_values(right), casefold=True)
    if match_type == "gene_family":
        return intersects(left.get("gene_families"), right.get("gene_families"), casefold=True)
    if match_type == "biotype":
        return intersects(biotype_values(left), biotype_values(right), casefold=True)
    if match_type == "any_identity":
        return (
            labels_match("gene_id", left, right)
            or labels_match("gene_symbol", left, right)
            or labels_match("gene_family", left, right)
        )
    raise ValueError(f"Unknown match type: {match_type}")


def anchor_has_match_type(labels: dict[str, list[str]], match_type: str) -> bool:
    if match_type == "gene_id":
        return bool(labels.get("gene_ids"))
    if match_type == "gene_symbol":
        return bool(symbol_values(labels))
    if match_type == "gene_family":
        return bool(labels.get("gene_families"))
    if match_type == "biotype":
        return bool(biotype_values(labels))
    if match_type == "any_identity":
        return has_identity_labels(labels)
    return False


def has_identity_labels(labels: dict[str, list[str]]) -> bool:
    return any(labels.get(key) for key in IDENTITY_LABELS)


def symbol_values(labels: dict[str, list[str]]) -> list[str]:
    return [*labels.get("gene_symbols", []), *labels.get("protein_gene_names", [])]


def biotype_values(labels: dict[str, list[str]]) -> list[str]:
    return [*labels.get("gene_biotypes", []), *labels.get("transcript_biotypes", [])]


def intersects(left: Any, right: Any, *, casefold: bool) -> bool:
    left_values = [str(value) for value in as_list(left) if value not in {None, ""}]
    right_values = [str(value) for value in as_list(right) if value not in {None, ""}]
    if casefold:
        return bool({value.upper() for value in left_values} & {value.upper() for value in right_values})
    return bool(set(left_values) & set(right_values))


def gene_family(symbol: str) -> str | None:
    text = str(symbol or "").upper()
    if text.startswith(("IGHV", "IGKV", "IGLV", "TRAV", "TRBV", "TRGV", "TRDV")):
        match = re.match(r"^([A-Z]+)", text)
        if match:
            return match.group(1)
    return None


def compact_neighbors(neighbors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "parent_record_id": item.get("parent_record_id"),
            "score": item.get("score"),
            "labels": item.get("labels"),
        }
        for item in neighbors
    ]


def mean_bool(values: list[bool]) -> float:
    return round(sum(1 for value in values if value) / len(values), 4) if values else 0.0


def mean(values: list[float]) -> float:
    return round(float(statistics.fmean(values)), 4) if values else 0.0


def enrichment(vector_value: float, random_value: float) -> float | str:
    if random_value == 0:
        return "inf" if vector_value > 0 else 0.0
    return round(vector_value / random_value, 4)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate biological enrichment in vector neighborhoods")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--targets", default="protein_sequence_window,dna_sequence_window")
    parser.add_argument("--anchor-count", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--query-results", type=int, default=1000)
    parser.add_argument("--metadata-limit", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=20260515)
    parser.add_argument("--include-same-parent", action="store_true")
    parser.add_argument("--keep-parent-duplicates", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()

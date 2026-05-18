#!/usr/bin/env python3
"""Create a reproducible sequence-window benchmark from Chroma records."""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.retrieval.vector_db import ChromaVectorDB


QUERY_RECIPES: tuple[str, ...] = (
    "exact_window",
    "prefix_96",
    "suffix_96",
    "middle_short",
    "mutated_96",
)


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    config = load_config(args.config)
    db = ChromaVectorDB(config.vector_dir)
    per_modality = max(int(args.per_modality), 1)
    rows: list[dict[str, Any]] = []
    rows.extend(
        make_rows(
            db,
            target="protein_sequence_window",
            category="protein_sequence",
            vector_target="protein_sequence_window",
            per_modality=per_modality,
            seed=rng.randrange(1_000_000_000),
        )
    )
    rows.extend(
        make_rows(
            db,
            target="dna_sequence_window",
            category="dna_sequence",
            vector_target="dna_sequence_window",
            per_modality=per_modality,
            seed=rng.randrange(1_000_000_000),
        )
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(output), "tasks": len(rows), "per_modality": per_modality}, indent=2))


def make_rows(
    db: ChromaVectorDB,
    *,
    target: str,
    category: str,
    vector_target: str,
    per_modality: int,
    seed: int,
) -> list[dict[str, Any]]:
    info = db.collection_info(target)
    if not info or int(info.get("count") or 0) == 0:
        raise SystemExit(f"Missing or empty Chroma collection: {target}")
    count = int(info["count"])
    rng = random.Random(seed)
    recipes = [QUERY_RECIPES[index % len(QUERY_RECIPES)] for index in range(per_modality)]
    rng.shuffle(recipes)
    collection = db._collection(target)
    rows: list[dict[str, Any]] = []
    used_parents: set[str] = set()
    used_offsets: set[int] = set()
    attempts = 0
    while len(rows) < per_modality and attempts < per_modality * 200:
        attempts += 1
        offset = rng.randrange(count)
        if offset in used_offsets:
            continue
        used_offsets.add(offset)
        record = get_one(collection, offset)
        sequence = normalize_sequence(record.get("document") or "")
        metadata = dict(record.get("metadata") or {})
        parent = str(metadata.get("record_id") or "")
        if not sequence or len(sequence) < 96 or not parent or parent in used_parents:
            continue
        used_parents.add(parent)
        recipe = recipes[len(rows)]
        query = make_query(sequence, recipe=recipe, category=category, rng=rng)
        if len(query) < (50 if category == "dna_sequence" else 30):
            continue
        accession = parent.split(":", 1)[1] if ":" in parent else parent
        biological = biological_expected(metadata)
        expected = {
            "entity_ids": [parent],
            "source_ids": [accession],
            "accessions": [accession],
        }
        if biological:
            expected["biological"] = biological
        rows.append(
            {
                "id": f"{category}_{recipe}_{len(rows) + 1:03d}",
                "category": category,
                "query_type": recipe,
                "query": query,
                "vector_target": vector_target,
                "expected": expected,
                "notes": f"sampled_from={target}; seed={seed}; offset={offset}",
            }
        )
    if len(rows) != per_modality:
        raise SystemExit(f"Only generated {len(rows)} / {per_modality} rows for {target}")
    return rows


def get_one(collection: Any, offset: int) -> dict[str, Any]:
    result = collection.get(limit=1, offset=offset, include=["metadatas", "documents"])
    metadata = dict((result.get("metadatas") or [{}])[0] or {})
    try:
        nested = json.loads(str(metadata.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        nested = {}
    metadata.update(nested)
    return {"metadata": metadata, "document": (result.get("documents") or [""])[0]}


def biological_expected(metadata: dict[str, Any]) -> dict[str, list[str]]:
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
    families = sorted({gene_family(value) for value in result.get("gene_symbols", []) if gene_family(value)})
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


def make_query(sequence: str, *, recipe: str, category: str, rng: random.Random) -> str:
    if recipe == "exact_window":
        return sequence
    if recipe == "prefix_96":
        return sequence[:96]
    if recipe == "suffix_96":
        return sequence[-96:]
    if recipe == "middle_short":
        size = 80 if category == "dna_sequence" else 64
        start = max((len(sequence) - size) // 2, 0)
        return sequence[start : start + size]
    if recipe == "mutated_96":
        return mutate(sequence[:96], category=category, rng=rng)
    raise ValueError(f"Unknown query recipe: {recipe}")


def mutate(sequence: str, *, category: str, rng: random.Random) -> str:
    alphabet = "ACGT" if category == "dna_sequence" else "ACDEFGHIKLMNPQRSTVWY"
    chars = list(sequence)
    mutation_count = max(1, round(len(chars) * 0.05))
    for position in rng.sample(range(len(chars)), mutation_count):
        current = chars[position]
        choices = [base for base in alphabet if base != current]
        chars[position] = rng.choice(choices)
    return "".join(chars)


def normalize_sequence(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalpha() or ch == "*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a sequence-window retrieval benchmark")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--output", default="benchmarks/sequence_search_100.jsonl")
    parser.add_argument("--per-modality", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260515)
    return parser.parse_args()


if __name__ == "__main__":
    main()

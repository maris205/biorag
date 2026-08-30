#!/usr/bin/env python3
"""Run a comparable DNA/cDNA embedding retrieval matrix.

The benchmark is a held-out-parent control: query parents are absent from the
FASTA index, while same-gene indexed transcripts are retained by the
controlled20k construction.  This runner deliberately keeps model loading,
pooling, windowing, orientation handling, and parent collapse in one place so
results from different DNA encoders are comparable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.retrieval.vector import make_embedder


DNA_COMPLEMENT = str.maketrans("ACGTNacgtn", "TGCANtgcan")
GENE_RE = re.compile(r"(?:^|\s)gene_symbol:([^\s]+)")


def main() -> None:
    args = parse_args()
    if args.max_length:
        os.environ["DNARAG_EMBED_MAX_LENGTH"] = str(args.max_length)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    records = load_fasta_records(Path(args.index_fasta))
    if args.index_record_limit:
        records = dict(list(records.items())[: args.index_record_limit])
    queries = load_jsonl(Path(args.benchmark))[: max(args.limit, 0) or None]
    accessions, sequences = make_windows(
        records,
        size=args.window_size,
        stride=args.window_stride,
        min_size=args.min_window_size,
    )
    if args.index_window_limit:
        accessions = accessions[: args.index_window_limit]
        sequences = sequences[: args.index_window_limit]
    if not sequences:
        raise SystemExit("No DNA windows were produced from the index FASTA")
    if not queries:
        raise SystemExit("No benchmark queries were found")

    import torch

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    embedder = make_embedder(
        args.backend,
        model_name=args.model,
        pooling=args.pooling,
        dtype=args.dtype,
    )
    model_load_s = time.perf_counter() - load_started

    index_started = time.perf_counter()
    index_vectors = embed_dna_batches(
        embedder,
        sequences,
        batch_size=args.batch_size,
        orientation=args.orientation,
    )
    index_embedding_s = time.perf_counter() - index_started

    query_sequences = [clean_dna(str(row["query"])) for row in queries]
    query_started = time.perf_counter()
    query_vectors = embed_dna_batches(
        embedder,
        query_sequences,
        batch_size=args.batch_size,
        orientation=args.orientation,
    )
    query_embedding_s = time.perf_counter() - query_started

    details: list[dict[str, Any]] = []
    lookup_times: list[float] = []
    for query_index, (row, query_vector) in enumerate(zip(queries, query_vectors)):
        lookup_started = time.perf_counter()
        scores = index_vectors @ query_vector
        parent_scores: dict[str, float] = {}
        for index, score in enumerate(scores):
            accession = accessions[index]
            parent_scores[accession] = max(parent_scores.get(accession, -1.0), float(score))
        ranked = [
            accession
            for accession, _score in sorted(
                parent_scores.items(), key=lambda item: (-item[1], item[0])
            )[: args.top_k]
        ]
        lookup_times.append((time.perf_counter() - lookup_started) * 1000.0)

        expected = dict(row.get("expected") or {})
        expected_accessions = set(as_strings(expected.get("heldout_accessions")))
        biological = dict(expected.get("biological") or {})
        expected_genes = normalize_set(
            [*as_strings(biological.get("gene_symbols")), *as_strings(biological.get("protein_gene_names"))]
        )
        exact_rank = first_rank(ranked, expected_accessions)
        bio_rank = first_rank(
            ranked,
            {accession for accession in ranked if expected_genes.intersection(records[accession].genes)},
        )
        details.append(
            {
                "query_id": row.get("id"),
                "query_type": row.get("query_type"),
                "query_length": len(query_sequences[query_index]),
                "exact_rank": exact_rank,
                "exact_hit_at_1": bool(exact_rank == 1),
                "exact_hit_at_5": bool(exact_rank and exact_rank <= 5),
                "exact_hit_at_10": bool(exact_rank and exact_rank <= 10),
                "exact_mrr": 1.0 / exact_rank if exact_rank else 0.0,
                "bio_rank": bio_rank,
                "bio_hit_at_1": bool(bio_rank == 1),
                "bio_hit_at_5": bool(bio_rank and bio_rank <= 5),
                "bio_hit_at_10": bool(bio_rank and bio_rank <= 10),
                "bio_mrr": 1.0 / bio_rank if bio_rank else 0.0,
                "expected_genes": sorted(expected_genes),
                "top_accessions": ranked[:10],
            }
        )

    peak_memory_gib = (
        torch.cuda.max_memory_allocated() / (1024**3) if torch.cuda.is_available() else 0.0
    )
    result = {
        "dataset": "BioRAG DNA held-out parent-fragment controlled20k",
        "claim_scope": (
            "Held-out parent accessions are absent from the index. Biological matching uses shared gene labels; "
            "this is a DNA/cDNA dense-retrieval control, not evidence that embeddings replace BLASTN."
        ),
        "benchmark": args.benchmark,
        "index_fasta": args.index_fasta,
        "backend": args.backend,
        "model": args.model,
        "pooling": args.pooling,
        "dtype": args.dtype,
        "orientation": args.orientation,
        "window_size": args.window_size,
        "window_stride": args.window_stride,
        "min_window_size": args.min_window_size,
        "index_record_count": len(records),
        "index_window_count": len(sequences),
        "query_count": len(queries),
        "top_k": args.top_k,
        "command": " ".join(sys.argv),
        "software": software_versions(),
        "summary": summarize(details),
        "timing": {
            "model_load_s": model_load_s,
            "index_embedding_s": index_embedding_s,
            "query_embedding_ms_per_query": query_embedding_s * 1000.0 / len(queries),
            "lookup_ms_per_query": float(np.mean(lookup_times)) if lookup_times else 0.0,
            "end_to_end_ms_per_query": query_embedding_s * 1000.0 / len(queries)
            + (float(np.mean(lookup_times)) if lookup_times else 0.0),
        },
        "gpu": {
            "available": bool(torch.cuda.is_available()),
            "name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "peak_memory_gib": peak_memory_gib,
        },
        "details": details,
    }
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2, ensure_ascii=False))


def embed_dna_batches(embedder: Any, sequences: list[str], *, batch_size: int, orientation: str) -> np.ndarray:
    """Encode forward strands, optionally averaging forward and reverse-complement vectors."""
    chunks: list[np.ndarray] = []
    batch_size = max(int(batch_size), 1)
    for start in range(0, len(sequences), batch_size):
        batch = sequences[start : start + batch_size]
        forward = embedder.embed(batch)
        if orientation == "rc_mean":
            reverse = embedder.embed([reverse_complement(item) for item in batch])
            forward = (forward + reverse) / 2.0
            norms = np.linalg.norm(forward, axis=1, keepdims=True)
            forward = forward / np.maximum(norms, 1e-12)
        chunks.append(forward.astype(np.float32, copy=False))
        print(json.dumps({"embedded": min(start + batch_size, len(sequences)), "total": len(sequences)}), flush=True)
    return np.vstack(chunks) if chunks else np.zeros((0, 0), dtype=np.float32)


def load_fasta_records(path: Path) -> dict[str, "FastaRecord"]:
    records: dict[str, FastaRecord] = {}
    header: str | None = None
    sequence: list[str] = []
    with path.open("rt", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    record = make_record(header, "".join(sequence))
                    records[record.accession] = record
                header, sequence = line[1:], []
            else:
                sequence.append(line)
    if header is not None:
        record = make_record(header, "".join(sequence))
        records[record.accession] = record
    return records


class FastaRecord:
    def __init__(self, accession: str, sequence: str, genes: set[str]):
        self.accession = accession
        self.sequence = sequence
        self.genes = genes


def make_record(header: str, sequence: str) -> FastaRecord:
    accession = header.split(None, 1)[0]
    genes = normalize_set(GENE_RE.findall(header))
    return FastaRecord(accession, clean_dna(sequence), genes)


def make_windows(records: dict[str, FastaRecord], *, size: int, stride: int, min_size: int) -> tuple[list[str], list[str]]:
    accessions: list[str] = []
    windows: list[str] = []
    for accession, record in records.items():
        sequence = record.sequence
        starts = list(range(0, max(len(sequence) - size + 1, 1), max(stride, 1)))
        tail = max(len(sequence) - size, 0)
        if tail not in starts:
            starts.append(tail)
        for start in sorted(set(starts)):
            window = sequence[start : start + size]
            if len(window) >= min_size:
                accessions.append(accession)
                windows.append(window)
    return accessions, windows


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clean_dna(sequence: str) -> str:
    return "".join(char for char in sequence.upper() if char in "ACGTN")


def reverse_complement(sequence: str) -> str:
    return clean_dna(sequence).translate(DNA_COMPLEMENT)[::-1]


def as_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [str(value)]


def normalize_set(values: list[str]) -> set[str]:
    return {value.strip().upper() for value in values if value and value.strip()}


def first_rank(items: list[str], expected: set[str]) -> int | None:
    return next((index for index, item in enumerate(items, start=1) if item in expected), None)


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = (
        "exact_hit_at_1", "exact_hit_at_5", "exact_hit_at_10", "exact_mrr",
        "bio_hit_at_1", "bio_hit_at_5", "bio_hit_at_10", "bio_mrr",
    )
    return {key: sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0 for key in keys}


def software_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": sys.version.split()[0], "numpy": np.__version__}
    try:
        import torch

        versions["torch"] = str(torch.__version__)
        try:
            import transformers

            versions["transformers"] = str(transformers.__version__)
        except Exception:
            pass
    except Exception:
        pass
    return versions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate DNA embedding models on the held-out parent benchmark")
    parser.add_argument(
        "--backend",
        required=True,
        choices=["omnigene", "transformers4bit", "nucleotide", "dnabert", "dnabert2", "dnabert-2", "dnabert_s", "dnabert-s", "caduceus", "hyenadna", "gena_lm", "gena-lm", "dna_es2", "dna-es2", "hf_encoder"],
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--pooling", default="mean", choices=["mean", "last", "cls"])
    parser.add_argument("--dtype", default="bf16", choices=["auto", "bf16", "fp16", "fp32"])
    parser.add_argument("--orientation", default="none", choices=["none", "rc_mean"])
    parser.add_argument("--benchmark", default="benchmarks/dna_parent_frag_100.jsonl")
    parser.add_argument("--index-fasta", default="data/heldout/dna_parent_frag_100_controlled20k_index.fasta")
    parser.add_argument("--index-record-limit", type=int, default=0, help="Limit FASTA parents for smoke tests; 0 means all")
    parser.add_argument("--index-window-limit", type=int, default=0, help="Limit encoded windows; 0 means all")
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--window-size", type=int, default=128)
    parser.add_argument("--window-stride", type=int, default=64)
    parser.add_argument("--min-window-size", type=int, default=24)
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-length", type=int, default=0)
    return parser.parse_args()


if __name__ == "__main__":
    main()

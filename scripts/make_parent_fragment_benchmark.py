#!/usr/bin/env python3
"""Create a held-out parent-fragment benchmark from a FASTA corpus.

The benchmark is designed for construct-validity checks: queries are sampled
from held-out parent sequences, while the emitted index FASTA excludes those
parents. Expected exact parent accessions are kept for leakage audits, and
biological labels are kept separately for retrieval evaluation.
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


PROTEIN_ALPHABET = "ACDEFGHIKLMNPQRSTVWY"
DNA_ALPHABET = "ACGT"
DEFAULT_QUERY_TYPES = ("exact_fragment", "prefix", "suffix", "middle", "mutated")


@dataclass(frozen=True, slots=True)
class FastaRecord:
    header: str
    sequence: str
    accession: str
    entry_name: str | None
    gene_name: str | None
    organism: str | None
    taxon_id: str | None
    protein_name: str | None


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    fasta = Path(args.fasta)
    records = [
        record
        for record in iter_fasta_records(fasta, alphabet=args.alphabet)
        if len(record.sequence) >= args.min_sequence_len
    ]
    if not records:
        raise SystemExit(f"No usable records found in {fasta}")

    query_types = tuple(split_csv(args.query_types)) or DEFAULT_QUERY_TYPES
    heldout = sample_heldout_records(
        records,
        n=args.n,
        rng=rng,
        min_gene_copies=args.min_gene_copies,
        min_index_gene_copies=args.min_index_gene_copies,
        max_heldout_per_gene=args.max_heldout_per_gene,
        require_gene=not args.allow_missing_gene,
    )
    heldout_accessions = {record.accession for record in heldout}
    rows = make_rows(
        heldout,
        index_records=[record for record in records if record.accession not in heldout_accessions],
        query_types=query_types,
        rng=rng,
        category=args.category,
        vector_target=args.vector_target,
        min_query_len=args.min_query_len,
        max_query_len=args.max_query_len,
        alphabet=args.alphabet,
        seed=args.seed,
        include_exact_expected=args.include_exact_expected,
        reject_index_substrings=args.reject_index_substrings,
        max_query_attempts=args.max_query_attempts,
        skip_unsamplable=args.skip_unsamplable,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    heldout_output = Path(args.heldout_output)
    heldout_output.parent.mkdir(parents=True, exist_ok=True)
    with heldout_output.open("wt", encoding="utf-8") as handle:
        for record in sorted(heldout, key=lambda item: item.accession):
            handle.write(
                "\t".join(
                    [
                        record.accession,
                        record.gene_name or "",
                        record.entry_name or "",
                        record.organism or "",
                    ]
                )
                + "\n"
            )

    index_fasta = Path(args.index_fasta)
    index_fasta.parent.mkdir(parents=True, exist_ok=True)
    write_index_fasta(index_fasta, records, heldout_accessions)

    summary = {
        "output": str(output),
        "heldout_output": str(heldout_output),
        "index_fasta": str(index_fasta),
        "source_fasta": str(fasta),
        "source_records": len(records),
        "heldout_parents": len(heldout),
        "index_records": len(records) - len(heldout),
        "category": args.category,
        "vector_target": args.vector_target,
        "query_types": list(query_types),
        "seed": args.seed,
        "min_gene_copies": args.min_gene_copies,
        "min_index_gene_copies": args.min_index_gene_copies,
        "max_heldout_per_gene": args.max_heldout_per_gene,
        "reject_index_substrings": args.reject_index_substrings,
        "sampled_tasks": len(rows),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def sample_heldout_records(
    records: list[FastaRecord],
    *,
    n: int,
    rng: random.Random,
    min_gene_copies: int,
    min_index_gene_copies: int,
    max_heldout_per_gene: int,
    require_gene: bool,
) -> list[FastaRecord]:
    by_gene: dict[str, list[FastaRecord]] = {}
    no_gene: list[FastaRecord] = []
    for record in records:
        key = normalize_gene(record.gene_name)
        if key:
            by_gene.setdefault(key, []).append(record)
        else:
            no_gene.append(record)

    eligible_groups = [
        group[:]
        for group in by_gene.values()
        if len(group) >= max(min_gene_copies, min_index_gene_copies + 1)
    ]
    for group in eligible_groups:
        rng.shuffle(group)
    rng.shuffle(eligible_groups)

    heldout: list[FastaRecord] = []
    used_accessions: set[str] = set()
    for group in eligible_groups:
        capacity = min(max_heldout_per_gene, max(len(group) - min_index_gene_copies, 0))
        for record in group[:capacity]:
            if record.accession in used_accessions:
                continue
            heldout.append(record)
            used_accessions.add(record.accession)
            if len(heldout) >= n:
                return heldout

    if not require_gene and len(heldout) < n:
        fallback = no_gene[:]
        rng.shuffle(fallback)
        for record in fallback:
            if record.accession in used_accessions:
                continue
            heldout.append(record)
            used_accessions.add(record.accession)
            if len(heldout) >= n:
                return heldout

    raise SystemExit(
        "Only selected "
        f"{len(heldout)} / {n} held-out parents. Try lowering --min-gene-copies, "
        "--min-index-gene-copies, or --max-heldout-per-gene."
    )


def make_rows(
    records: list[FastaRecord],
    *,
    index_records: list[FastaRecord],
    query_types: tuple[str, ...],
    rng: random.Random,
    category: str,
    vector_target: str,
    min_query_len: int,
    max_query_len: int,
    alphabet: str,
    seed: int,
    include_exact_expected: bool,
    reject_index_substrings: bool,
    max_query_attempts: int,
    skip_unsamplable: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    recipes = [query_types[index % len(query_types)] for index in range(len(records))]
    rng.shuffle(recipes)
    index_sequences = [record.sequence for record in index_records] if reject_index_substrings else []
    for index, (record, recipe) in enumerate(zip(records, recipes, strict=True), start=1):
        try:
            query, start, end = make_nonleaking_query(
                record,
                recipe=recipe,
                rng=rng,
                min_query_len=min_query_len,
                max_query_len=max_query_len,
                alphabet=alphabet,
                index_sequences=index_sequences,
                reject_index_substrings=reject_index_substrings,
                max_query_attempts=max_query_attempts,
            )
        except ValueError:
            if skip_unsamplable:
                continue
            raise
        expected = {
            "heldout_entity_ids": [f"{category}:{record.accession}"],
            "heldout_accessions": [record.accession],
            "biological": biological_expected(record),
        }
        if include_exact_expected:
            expected["entity_ids"] = [f"{category}:{record.accession}"]
            expected["source_ids"] = [record.accession]
            expected["accessions"] = [record.accession]
        rows.append(
            {
                "id": f"{category}_heldout_{recipe}_{index:04d}",
                "category": category,
                "query_type": recipe,
                "query": query,
                "vector_target": vector_target,
                "expected": expected,
                "notes": (
                    f"heldout_parent={record.accession}; seed={seed}; "
                    f"fragment_start={start}; fragment_end={end}; source=parent_fasta"
                ),
            }
        )
    return rows


def make_nonleaking_query(
    record: FastaRecord,
    *,
    recipe: str,
    rng: random.Random,
    min_query_len: int,
    max_query_len: int,
    alphabet: str,
    index_sequences: list[str],
    reject_index_substrings: bool,
    max_query_attempts: int,
) -> tuple[str, int, int]:
    last_query: tuple[str, int, int] | None = None
    for _attempt in range(max(max_query_attempts, 1)):
        query, start, end = make_query(
            record.sequence,
            recipe=recipe,
            rng=rng,
            min_query_len=min_query_len,
            max_query_len=max_query_len,
            alphabet=alphabet,
        )
        last_query = (query, start, end)
        if not reject_index_substrings or not any(query in sequence for sequence in index_sequences):
            return query, start, end
    raise ValueError(
        f"Could not sample a non-substring query for {record.accession} "
        f"after {max_query_attempts} attempts; last_query_len={len(last_query[0]) if last_query else 0}"
    )


def make_query(
    sequence: str,
    *,
    recipe: str,
    rng: random.Random,
    min_query_len: int,
    max_query_len: int,
    alphabet: str,
) -> tuple[str, int, int]:
    if len(sequence) < min_query_len:
        raise ValueError("sequence shorter than requested minimum query length")
    size = rng.randint(min_query_len, min(max_query_len, len(sequence)))
    if recipe == "prefix":
        start = 0
    elif recipe == "suffix":
        start = len(sequence) - size
    elif recipe == "middle":
        start = max((len(sequence) - size) // 2, 0)
    elif recipe in {"exact_fragment", "mutated"}:
        start = rng.randint(0, len(sequence) - size)
    else:
        raise ValueError(f"Unknown query type: {recipe}")
    end = start + size
    query = sequence[start:end]
    if recipe == "mutated":
        query = mutate(query, alphabet=alphabet, rng=rng)
    return query, start, end


def mutate(sequence: str, *, alphabet: str, rng: random.Random) -> str:
    bases = DNA_ALPHABET if alphabet == "dna" else PROTEIN_ALPHABET
    chars = list(sequence)
    if not chars:
        return sequence
    mutation_count = max(1, round(len(chars) * 0.05))
    for position in rng.sample(range(len(chars)), min(mutation_count, len(chars))):
        current = chars[position]
        choices = [base for base in bases if base != current]
        if choices:
            chars[position] = rng.choice(choices)
    return "".join(chars)


def write_index_fasta(path: Path, records: list[FastaRecord], heldout_accessions: set[str]) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for record in records:
            if record.accession in heldout_accessions:
                continue
            handle.write(f">{record.header}\n")
            for start in range(0, len(record.sequence), 80):
                handle.write(record.sequence[start : start + 80] + "\n")


def biological_expected(record: FastaRecord) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if record.gene_name:
        result["gene_symbols"] = [record.gene_name]
        result["protein_gene_names"] = [record.gene_name]
        family = gene_family(record.gene_name)
        if family:
            result["gene_families"] = [family]
    if record.entry_name:
        result["entry_names"] = [record.entry_name]
    if record.protein_name:
        result["protein_names"] = [record.protein_name]
    if record.organism:
        result["organisms"] = [record.organism]
    if record.taxon_id:
        result["taxon_ids"] = [record.taxon_id]
    return result


def iter_fasta_records(path: Path, *, alphabet: str) -> Iterable[FastaRecord]:
    allow_stop = alphabet == "protein"
    for header, raw_sequence in iter_fasta(path):
        sequence = clean_sequence(raw_sequence, allow_stop=allow_stop)
        if not sequence:
            continue
        meta = fasta_header_metadata(header)
        yield FastaRecord(
            header=header,
            sequence=sequence,
            accession=accession_from_header(header),
            entry_name=entry_name_from_header(header) or meta.get("transcript_id"),
            gene_name=match_header_field(header, "GN") or meta.get("gene_symbol"),
            organism=match_header_span(header, "OS", ("OX", "GN", "PE", "SV")),
            taxon_id=match_header_field(header, "OX"),
            protein_name=protein_name_from_header(header) if alphabet == "protein" else meta.get("description"),
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


def accession_from_header(header: str) -> str:
    token = header.split()[0]
    if "|" in token:
        parts = token.split("|")
        if len(parts) > 1:
            return parts[1]
    return token


def entry_name_from_header(header: str) -> str | None:
    token = header.split()[0]
    if "|" in token:
        parts = token.split("|")
        if len(parts) > 2 and parts[2]:
            return parts[2]
    return None


def protein_name_from_header(header: str) -> str | None:
    text = re.sub(r"^\S+\s*", "", header).strip()
    match = re.search(r"\bOS=", text)
    if match:
        text = text[: match.start()].strip()
    return text or None


def match_header_field(header: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}=([^\s]+)", header)
    return match.group(1).strip(";,") if match else None


def match_header_span(header: str, key: str, stop_keys: tuple[str, ...]) -> str | None:
    match = re.search(rf"\b{re.escape(key)}=", header)
    if not match:
        return None
    start = match.end()
    stop_positions = [
        stop.start()
        for stop_key in stop_keys
        if stop_key != key
        for stop in [re.search(rf"\b{re.escape(stop_key)}=", header[start:])]
        if stop
    ]
    end = start + min(stop_positions) if stop_positions else len(header)
    value = header[start:end].strip()
    return value or None


def fasta_header_metadata(header: str) -> dict[str, str]:
    """Parse common key:value FASTA header fields from Ensembl-style records."""
    result: dict[str, str] = {}
    first_token = header.split()[0] if header.split() else ""
    if first_token:
        result["transcript_id"] = first_token
    for key, value in re.findall(r"\b([A-Za-z_]+):([^\s]+)", header):
        result[key] = value.strip(";,")
    if "description:" in header:
        result["description"] = header.split("description:", 1)[1].strip()
    return result


def clean_sequence(sequence: str, *, allow_stop: bool) -> str:
    allowed_extra = {"*"} if allow_stop else set()
    return "".join(ch for ch in str(sequence or "").upper() if ch.isalpha() or ch in allowed_extra)


def normalize_gene(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def gene_family(symbol: str) -> str | None:
    text = str(symbol or "").upper()
    if text.startswith(("IGHV", "IGKV", "IGLV", "TRAV", "TRBV", "TRGV", "TRDV")):
        match = re.match(r"^([A-Z]+)", text)
        if match:
            return match.group(1)
    return None


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a held-out parent-fragment benchmark")
    parser.add_argument("--fasta", required=True, help="Source FASTA or FASTA.GZ")
    parser.add_argument("--n", type=int, default=500, help="Number of held-out parent queries")
    parser.add_argument("--min-query-len", type=int, default=64)
    parser.add_argument("--max-query-len", type=int, default=128)
    parser.add_argument("--min-sequence-len", type=int, default=128)
    parser.add_argument("--query-types", default=",".join(DEFAULT_QUERY_TYPES))
    parser.add_argument("--seed", type=int, default=20260516)
    parser.add_argument("--category", default="protein_sequence")
    parser.add_argument("--vector-target", default="protein_sequence")
    parser.add_argument("--alphabet", choices=["protein", "dna"], default="protein")
    parser.add_argument("--min-gene-copies", type=int, default=2)
    parser.add_argument("--min-index-gene-copies", type=int, default=1)
    parser.add_argument("--max-heldout-per-gene", type=int, default=1)
    parser.add_argument("--allow-missing-gene", action="store_true")
    parser.add_argument(
        "--reject-index-substrings",
        action="store_true",
        help="Reject sampled queries that occur exactly in any non-held-out indexed record.",
    )
    parser.add_argument("--max-query-attempts", type=int, default=100)
    parser.add_argument(
        "--skip-unsamplable",
        action="store_true",
        help="Skip held-out parents whose sampled queries always occur in the index.",
    )
    parser.add_argument(
        "--include-exact-expected",
        action="store_true",
        help="Also include held-out exact accession in standard expected fields.",
    )
    parser.add_argument("--output", default="benchmarks/protein_parent_frag_500.jsonl")
    parser.add_argument(
        "--heldout-output",
        default="benchmarks/protein_parent_frag_500_heldout_accessions.txt",
    )
    parser.add_argument("--index-fasta", default="data/heldout/protein_parent_frag_500_index.fasta")
    return parser.parse_args()


if __name__ == "__main__":
    main()

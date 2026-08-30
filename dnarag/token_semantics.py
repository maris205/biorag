"""Utilities for exploratory biological semantics of sequence tokenization."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class AnnotatedSequence:
    accession: str
    sequence: str
    labels: tuple[str, ...]
    name: str = ""


@dataclass(slots=True)
class SparseTokenIndex:
    """Small in-memory BM25 index over sequence token nodes."""

    accessions: tuple[str, ...]
    postings: dict[str, tuple[tuple[int, int], ...]]
    document_frequency: dict[str, int]
    document_lengths: np.ndarray
    average_document_length: float
    k1: float = 1.2
    b: float = 0.75

    @classmethod
    def build(
        cls,
        accessions: Sequence[str],
        token_counts: Sequence[Counter[str]],
        *,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> "SparseTokenIndex":
        if len(accessions) != len(token_counts):
            raise ValueError("accessions and token_counts must have the same length")
        mutable: dict[str, list[tuple[int, int]]] = {}
        lengths = np.zeros(len(accessions), dtype=np.float64)
        for document_index, counts in enumerate(token_counts):
            lengths[document_index] = sum(counts.values())
            for token, count in counts.items():
                mutable.setdefault(token, []).append((document_index, int(count)))
        postings = {token: tuple(rows) for token, rows in mutable.items()}
        return cls(
            accessions=tuple(accessions),
            postings=postings,
            document_frequency={token: len(rows) for token, rows in postings.items()},
            document_lengths=lengths,
            average_document_length=float(lengths.mean()) if lengths.size else 0.0,
            k1=k1,
            b=b,
        )

    def idf(self, token: str) -> float:
        frequency = self.document_frequency.get(token, 0)
        total = len(self.accessions)
        if not frequency or not total:
            return 0.0
        return math.log1p((total - frequency + 0.5) / (frequency + 0.5))

    def scores(self, query_tokens: Sequence[str]) -> np.ndarray:
        scores = np.zeros(len(self.accessions), dtype=np.float64)
        if not self.average_document_length:
            return scores
        for token, query_frequency in Counter(query_tokens).items():
            idf = self.idf(token)
            if not idf:
                continue
            query_weight = 1.0 + math.log(max(query_frequency, 1))
            for document_index, term_frequency in self.postings.get(token, ()):
                length_ratio = self.document_lengths[document_index] / self.average_document_length
                denominator = term_frequency + self.k1 * (1.0 - self.b + self.b * length_ratio)
                scores[document_index] += (
                    idf * query_weight * term_frequency * (self.k1 + 1.0) / denominator
                )
        return scores

    def rank(self, query_tokens: Sequence[str], *, limit: int) -> list[tuple[str, float]]:
        scores = self.scores(query_tokens)
        positive = np.flatnonzero(scores > 0.0)
        ordered = sorted(positive, key=lambda index: (-scores[index], self.accessions[index]))
        return [(self.accessions[index], float(scores[index])) for index in ordered[:limit]]


def extract_sequence(text: str) -> str:
    """Extract a sequence from a SeqLit protein document."""
    marker = "Sequence:\n"
    if marker not in text:
        raise ValueError("SeqLit document does not contain a Sequence field")
    return "".join(text.rsplit(marker, 1)[1].split()).upper()


def load_seq_lit_proteins(path: str | Path) -> list[AnnotatedSequence]:
    records: list[AnnotatedSequence] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("partition") != "seq_lit_dag/protein":
                continue
            records.append(
                AnnotatedSequence(
                    accession=str(row["accession"]),
                    sequence=extract_sequence(str(row["text"])),
                    labels=tuple(sorted(set(row.get("labels", {}).get("go_ids", [])))),
                    name=str(row.get("name") or ""),
                )
            )
    if not records:
        raise ValueError(f"No SeqLit protein documents found in {path}")
    return records


def fixed_kmers(sequence: str, k: int = 3) -> list[str]:
    if k <= 0:
        raise ValueError("k must be positive")
    if len(sequence) < k:
        return [sequence] if sequence else []
    return [sequence[index : index + k] for index in range(len(sequence) - k + 1)]


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    """Return Benjamini-Hochberg adjusted p-values with the input shape."""
    values = np.asarray(p_values, dtype=np.float64)
    flat = values.ravel()
    if flat.size == 0:
        return values.copy()
    order = np.argsort(flat, kind="mergesort")
    ranked = flat[order] * flat.size / np.arange(1, flat.size + 1, dtype=np.float64)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.empty_like(ranked)
    adjusted[order] = np.minimum(ranked, 1.0)
    return adjusted.reshape(values.shape)


def length_stratified_permutation(
    lengths: Sequence[int],
    rng: np.random.Generator,
    bins: int = 10,
) -> np.ndarray:
    """Permute record labels within approximately equal-size length strata."""
    if bins <= 0:
        raise ValueError("bins must be positive")
    order = np.argsort(np.asarray(lengths), kind="mergesort")
    permutation = np.arange(len(lengths))
    for group in np.array_split(order, min(bins, max(len(order), 1))):
        if group.size > 1:
            permutation[group] = rng.permutation(group)
    return permutation


def stable_token_id(namespace: str, token: str) -> str:
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()[:16]
    return f"bio_token:{namespace}:{digest}"


def tokenize_records(
    records: Sequence[AnnotatedSequence],
    tokenizer: Callable[[str], Sequence[str]],
) -> tuple[list[list[str]], list[Counter[str]]]:
    token_lists: list[list[str]] = []
    token_counts: list[Counter[str]] = []
    for record in records:
        tokens = [str(token) for token in tokenizer(record.sequence) if str(token)]
        token_lists.append(tokens)
        token_counts.append(Counter(tokens))
    return token_lists, token_counts

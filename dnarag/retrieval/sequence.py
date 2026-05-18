"""Sequence detection and local BLAST search."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DNA_ALPHABET = set("ACGTNURYKMSWBDHV")
RNA_ALPHABET = set("ACGUNURYKMSWBDHV")
PROTEIN_ALPHABET = set("ABCDEFGHIKLMNPQRSTVWXYZ*")


@dataclass(frozen=True, slots=True)
class SequenceQuery:
    sequence: str
    sequence_type: str
    length: int
    alphabet: str


class BlastUnavailable(RuntimeError):
    pass


def normalize_sequence(text: str) -> str:
    return "".join(ch for ch in str(text or "").upper() if ch.isalpha() or ch == "*")


def detect_sequence(text: str) -> SequenceQuery | None:
    if not _looks_like_sequence_input(text):
        return None
    sequence = normalize_sequence(_strip_fasta_headers(text))
    if len(sequence) < 8:
        return None
    chars = set(sequence)
    if chars <= DNA_ALPHABET and "U" not in chars:
        seq_type = "dna"
        alphabet = "dna"
    elif chars <= RNA_ALPHABET and "T" not in chars:
        seq_type = "rna"
        alphabet = "rna"
    elif chars <= PROTEIN_ALPHABET:
        seq_type = "protein" if len(sequence) >= 25 else "peptide_fragment"
        alphabet = "protein"
    else:
        return None
    return SequenceQuery(sequence=sequence, sequence_type=seq_type, length=len(sequence), alphabet=alphabet)


def _strip_fasta_headers(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        if line.lstrip().startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _looks_like_sequence_input(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if raw.startswith(">"):
        return True
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz* \t\r\n")
    if any(ch not in allowed for ch in raw):
        return False
    chunks = [chunk for chunk in raw.replace("\n", " ").replace("\t", " ").split(" ") if chunk]
    if len(chunks) <= 1:
        return True
    # Permit line-wrapped sequences, but reject short natural-language phrases
    # such as "DNA repair" or "BRCA DNA repair".
    return max(len(chunk) for chunk in chunks) >= 12


class LocalBlastSearch:
    def __init__(self, blast_db: str | Path, nucleotide_db: str | Path | None = None):
        self.blast_db = Path(blast_db)
        self.nucleotide_db = Path(nucleotide_db) if nucleotide_db else None

    def available(self) -> bool:
        return self.protein_available() or self.nucleotide_available()

    def protein_available(self) -> bool:
        return bool(shutil.which("blastp")) and Path(f"{self.blast_db}.pin").exists()

    def nucleotide_available(self) -> bool:
        return bool(shutil.which("blastn")) and self.nucleotide_db is not None and Path(f"{self.nucleotide_db}.nin").exists()

    def search(self, sequence: str, max_targets: int = 5) -> dict[str, Any]:
        query = detect_sequence(sequence)
        if query is None:
            return {"route": "blast", "status": "not_sequence", "hits": []}
        if query.alphabet == "dna":
            return self._search_nucleotide(query, max_targets=max_targets)
        if query.alphabet != "protein":
            return {
                "route": "blast",
                "status": "unsupported_sequence_type",
                "sequence_type": query.sequence_type,
                "hits": [],
            }
        return self._search_protein(query, max_targets=max_targets)

    def _search_protein(self, query: SequenceQuery, *, max_targets: int) -> dict[str, Any]:
        blastp = shutil.which("blastp")
        if not blastp or not Path(f"{self.blast_db}.pin").exists():
            raise BlastUnavailable(f"blastp or BLAST database unavailable for {self.blast_db}")

        task = "blastp-short" if query.length < 30 else "blastp"
        completed = _run_blast(
            executable=blastp,
            task=task,
            db=self.blast_db,
            sequence=query.sequence,
            max_targets=max_targets,
        )
        if completed.returncode != 0:
            return {
                "route": "blast",
                "status": "failed",
                "returncode": completed.returncode,
                "stderr": completed.stderr[-1000:],
                "hits": [],
            }
        return {
            "route": "blast",
            "status": "ok",
            "sequence_type": query.sequence_type,
            "length": query.length,
            "task": task,
            "hits": [_parse_blast_row(line) for line in completed.stdout.splitlines() if line.strip()],
        }

    def _search_nucleotide(self, query: SequenceQuery, *, max_targets: int) -> dict[str, Any]:
        blastn = shutil.which("blastn")
        if not blastn or self.nucleotide_db is None or not Path(f"{self.nucleotide_db}.nin").exists():
            raise BlastUnavailable(f"blastn or nucleotide BLAST database unavailable for {self.nucleotide_db}")
        task = "blastn-short" if query.length < 50 else "blastn"
        completed = _run_blast(
            executable=blastn,
            task=task,
            db=self.nucleotide_db,
            sequence=query.sequence,
            max_targets=max_targets,
        )
        if completed.returncode != 0:
            return {
                "route": "blast",
                "status": "failed",
                "returncode": completed.returncode,
                "stderr": completed.stderr[-1000:],
                "hits": [],
            }
        return {
            "route": "blast",
            "status": "ok",
            "sequence_type": query.sequence_type,
            "length": query.length,
            "task": task,
            "hits": [_parse_blast_row(line) for line in completed.stdout.splitlines() if line.strip()],
        }


def _run_blast(
    *,
    executable: str,
    task: str,
    db: Path,
    sequence: str,
    max_targets: int,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="dnarag_blast_") as tmp:
        query_path = Path(tmp) / "query.fa"
        query_path.write_text(f">query\n{sequence}\n", encoding="utf-8")
        cmd = [
            executable,
            "-task",
            task,
            "-query",
            str(query_path),
            "-db",
            str(db),
            "-outfmt",
            "6 sseqid pident length evalue bitscore stitle",
            "-max_target_seqs",
            str(max(max_targets, 1)),
        ]
        return subprocess.run(cmd, check=False, text=True, capture_output=True)


def _parse_blast_row(line: str) -> dict[str, Any]:
    parts = line.split("\t")
    while len(parts) < 6:
        parts.append("")
    return {
        "sseqid": parts[0],
        "pident": _float(parts[1]),
        "alignment_length": _int(parts[2]),
        "evalue": _float(parts[3]),
        "bitscore": _float(parts[4]),
        "title": parts[5],
    }


def _float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None

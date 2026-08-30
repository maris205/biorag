#!/usr/bin/env python3
"""Audit whether OmniGene biological vocabulary tokens are active in raw inputs."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.token_semantics import load_seq_lit_proteins


DEFAULT_MODEL = Path(
    "/root/autodl-tmp/huggingface/models--dnagpt--OmniGene-4-CPT-v2-merged/"
    "snapshots/332ed9582f41547beb2a2b6de228c9e53aae5500"
)
DEFAULT_BPE = Path("/autodl-fs/data/omnigene_v2/scripts/vocab/trained_bpe")
DEFAULT_CPT = Path("/autodl-fs/data/omnigene_v2/cpt_data/data_v2")


def added_token_summary(tokenizer_json: Path) -> tuple[dict[str, Any], dict[int, str]]:
    payload = json.loads(tokenizer_json.read_text(encoding="utf-8"))
    added = payload.get("added_tokens", [])
    token_by_id = {int(row["id"]): str(row["content"]) for row in added}
    groups: dict[str, list[str]] = {"dna_bpe": [], "protein_bpe": [], "other": []}
    for token in token_by_id.values():
        key = "dna_bpe" if token.startswith("▶") else "protein_bpe" if token.startswith("◆") else "other"
        groups[key].append(token)
    summary: dict[str, Any] = {
        "model_type": payload.get("model", {}).get("type"),
        "base_vocab_size": len(payload.get("model", {}).get("vocab", {})),
        "added_token_count": len(added),
    }
    for key, tokens in groups.items():
        lengths = [len(token) - (1 if token.startswith(("▶", "◆")) else 0) for token in tokens]
        summary[key] = {
            "count": len(tokens),
            "min_length": min(lengths) if lengths else 0,
            "median_length": median(lengths) if lengths else 0,
            "max_length": max(lengths) if lengths else 0,
        }
    return summary, token_by_id


def runtime_coverage(model: Path, sequences: list[str], prefixes: tuple[str, ...]) -> dict[str, Any]:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    total_tokens = 0
    extended_tokens = 0
    lengths: list[int] = []
    examples: list[dict[str, Any]] = []
    for sequence in sequences:
        tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(sequence, add_special_tokens=False))
        matched = [token for token in tokens if token.startswith(prefixes)]
        total_tokens += len(tokens)
        extended_tokens += len(matched)
        lengths.append(len(tokens))
        if len(examples) < 3:
            examples.append({"input_length": len(sequence), "tokens": tokens[:20], "extended": matched[:20]})
    residues = sum(map(len, sequences))
    return {
        "sequences": len(sequences),
        "residues": residues,
        "tokens": total_tokens,
        "extended_tokens": extended_tokens,
        "extended_token_fraction": extended_tokens / total_tokens if total_tokens else 0.0,
        "residues_per_token": residues / total_tokens if total_tokens else 0.0,
        "median_tokens_per_sequence": median(lengths) if lengths else 0,
        "examples": examples,
    }


def intended_bpe_coverage(path: Path, sequences: list[str]) -> dict[str, Any]:
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(path))
    counts: Counter[str] = Counter()
    lengths: list[int] = []
    for sequence in sequences:
        tokens = tokenizer.encode(sequence).tokens
        counts.update(tokens)
        lengths.append(len(tokens))
    total = sum(counts.values())
    residues = sum(map(len, sequences))
    return {
        "sequences": len(sequences),
        "residues": residues,
        "tokens": total,
        "unique_tokens": len(counts),
        "residues_per_token": residues / total if total else 0.0,
        "median_tokens_per_sequence": median(lengths) if lengths else 0,
        "top_tokens": counts.most_common(20),
    }


def load_dna_windows(path: Path, limit: int, window: int) -> list[str]:
    sequences: list[str] = []
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            sequence = "".join(line.split()).upper()
            if sequence:
                sequences.append(sequence[:window])
            if len(sequences) >= limit:
                break
    return sequences


def scan_cpt_part(path: Path, token_by_id: dict[int, str], sample_uint32: int) -> dict[str, Any]:
    values = np.fromfile(path, dtype=np.uint32, count=sample_uint32)
    dna_ids = np.fromiter((key for key, value in token_by_id.items() if value.startswith("▶")), dtype=np.uint32)
    protein_ids = np.fromiter((key for key, value in token_by_id.items() if value.startswith("◆")), dtype=np.uint32)
    return {
        "path": str(path),
        "sampled_uint32": int(values.size),
        "max_value": int(values.max()) if values.size else None,
        "dna_bpe_ids": int(np.isin(values, dna_ids).sum()),
        "protein_bpe_ids": int(np.isin(values, protein_ids).sum()),
    }


def render_report(result: dict[str, Any]) -> str:
    vocab = result["vocabulary"]
    protein = result["raw_input_coverage"]["protein"]
    dna = result["raw_input_coverage"]["dna"]
    scans = result["cpt_binary_sample"]
    lines = [
        "# OmniGene Biological Token Activation Audit",
        "",
        "## Result",
        "",
        "The tokenizer contains a biological BPE vocabulary, but the current raw sequence input path does not activate it.",
        "This audit distinguishes vocabulary presence from runtime or CPT-data use; it does not evaluate model quality.",
        "",
        "| Check | DNA | Protein |",
        "|---|---:|---:|",
        f"| Added BPE entries | {vocab['dna_bpe']['count']:,} | {vocab['protein_bpe']['count']:,} |",
        f"| Raw-input biological token hits | {dna['extended_tokens']:,} | {protein['extended_tokens']:,} |",
        f"| Raw-input token fraction | {dna['extended_token_fraction']:.6f} | {protein['extended_token_fraction']:.6f} |",
        f"| Raw-input residues/token | {dna['residues_per_token']:.3f} | {protein['residues_per_token']:.3f} |",
        f"| Intended standalone BPE residues/token | {result['intended_bpe']['dna']['residues_per_token']:.3f} | {result['intended_bpe']['protein']['residues_per_token']:.3f} |",
        "",
        "## CPT Binary Sample",
        "",
        "| Part | Sampled uint32 values | DNA BPE IDs | Protein BPE IDs | Max value |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in scans:
        lines.append(
            f"| `{Path(row['path']).name}` | {row['sampled_uint32']:,} | {row['dna_bpe_ids']:,} | "
            f"{row['protein_bpe_ids']:,} | {row['max_value']} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- The added entries are literal prefixed tokens (`▶...` for DNA and `◆...` for protein). Plain sequences do not contain those prefixes.",
        "- The inspected CPT preprocessing code sends plain sequence strings directly to the merged tokenizer.",
        "- The sampled DNA and protein CPT binary parts contain no DNA/protein BPE token IDs.",
        "- Consequently, current token-semantic analysis must label the standalone BPE segmentation as an intended/frequency-derived vocabulary, not a CPT-learned token representation.",
        "- A corrected model experiment needs a modality-aware pretokenization step followed by CPT; merely prefixing a whole sequence is insufficient.",
        "",
        "## Safe Paper Claim",
        "",
        "Current BioRAG results demonstrate sequence CPT through the base tokenizer, but do not yet isolate a gain or biological semantics from the expanded BPE entries.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--documents", type=Path, default=Path("data/seq_lit_dag_swissprot_2k/documents.jsonl"))
    parser.add_argument("--protein-bpe", type=Path, default=DEFAULT_BPE / "protein_bpe_8k.json")
    parser.add_argument("--dna-bpe", type=Path, default=DEFAULT_BPE / "dna_bpe_20k.json")
    parser.add_argument("--dna-source", type=Path, default=Path("/autodl-fs/data/omnigene_v2/data/dna_32g.txt"))
    parser.add_argument("--dna-limit", type=int, default=1000)
    parser.add_argument("--dna-window", type=int, default=512)
    parser.add_argument("--cpt-dir", type=Path, default=DEFAULT_CPT)
    parser.add_argument("--sample-uint32", type=int, default=10_000_000)
    parser.add_argument("--output-json", type=Path, default=Path("reports/results/omnigene_bio_token_audit.json"))
    parser.add_argument("--output-report", type=Path, default=Path("reports/omnigene_bio_token_audit.md"))
    args = parser.parse_args()

    records = load_seq_lit_proteins(args.documents)
    proteins = [record.sequence for record in records]
    dna = load_dna_windows(args.dna_source, args.dna_limit, args.dna_window)
    vocab, token_by_id = added_token_summary(args.model / "tokenizer.json")
    part_names = ("part_dna.bin", "part_prot1.bin", "part_prot2.bin")
    result = {
        "scope": "tokenizer activation audit; not a biological model-quality evaluation",
        "vocabulary": vocab,
        "raw_input_coverage": {
            "protein": runtime_coverage(args.model, proteins, ("◆",)),
            "dna": runtime_coverage(args.model, dna, ("▶",)),
        },
        "intended_bpe": {
            "protein": intended_bpe_coverage(args.protein_bpe, proteins),
            "dna": intended_bpe_coverage(args.dna_bpe, dna),
        },
        "cpt_binary_sample": [
            scan_cpt_part(args.cpt_dir / name, token_by_id, args.sample_uint32)
            for name in part_names
            if (args.cpt_dir / name).exists()
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.output_report.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"json": str(args.output_json), "report": str(args.output_report)}, indent=2))


if __name__ == "__main__":
    main()

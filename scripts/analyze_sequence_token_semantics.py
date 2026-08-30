#!/usr/bin/env python3
"""Build an exploratory protein-token-to-GO association graph with controls."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.token_semantics import (
    AnnotatedSequence,
    benjamini_hochberg,
    fixed_kmers,
    length_stratified_permutation,
    load_seq_lit_proteins,
    stable_token_id,
    tokenize_records,
)


def load_go_names(nodes_path: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with nodes_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("entity_type") == "go_term":
                canonical = str(row.get("canonical_id") or "")
                if canonical:
                    names[canonical] = str(row.get("name") or canonical)
    return names


def enrichment_analysis(
    records: Sequence[AnnotatedSequence],
    token_lists: Sequence[Sequence[str]],
    *,
    min_token_df: int,
    min_label_df: int,
    max_df_fraction: float,
    min_overlap: int,
    fdr: float,
    permutations: int,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        from scipy.sparse import csr_matrix
        from scipy.stats import hypergeom
    except ImportError as exc:
        raise RuntimeError("Install scipy to run token enrichment analysis") from exc

    n_records = len(records)
    max_df = max(int(n_records * max_df_fraction), min_token_df)
    token_df: Counter[str] = Counter()
    label_df: Counter[str] = Counter()
    for tokens, record in zip(token_lists, records, strict=True):
        token_df.update(set(tokens))
        label_df.update(record.labels)
    tokens = sorted(token for token, count in token_df.items() if min_token_df <= count <= max_df)
    labels = sorted(label for label, count in label_df.items() if min_label_df <= count <= max_df)
    if not tokens or not labels:
        raise ValueError("No tokens or labels survive the document-frequency filters")

    token_index = {token: index for index, token in enumerate(tokens)}
    label_index = {label: index for index, label in enumerate(labels)}
    matrix_rows: list[int] = []
    matrix_cols: list[int] = []
    label_matrix = np.zeros((n_records, len(labels)), dtype=np.int16)
    for record_index, (record_tokens, record) in enumerate(zip(token_lists, records, strict=True)):
        for token in set(record_tokens):
            index = token_index.get(token)
            if index is not None:
                matrix_rows.append(index)
                matrix_cols.append(record_index)
        for label in record.labels:
            index = label_index.get(label)
            if index is not None:
                label_matrix[record_index, index] = 1
    token_matrix = csr_matrix(
        (np.ones(len(matrix_rows), dtype=np.int16), (matrix_rows, matrix_cols)),
        shape=(len(tokens), n_records),
    )
    token_counts = np.asarray(token_matrix.sum(axis=1)).ravel().astype(np.int64)
    label_counts = label_matrix.sum(axis=0).astype(np.int64)

    def statistics(current_labels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        overlap = np.asarray(token_matrix @ current_labels, dtype=np.int64)
        p_values = hypergeom.sf(
            overlap - 1,
            n_records,
            label_counts[None, :],
            token_counts[:, None],
        )
        q_values = benjamini_hochberg(p_values)
        a = overlap.astype(np.float64)
        b = token_counts[:, None] - a
        c = label_counts[None, :] - a
        d = n_records - a - b - c
        odds = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
        return overlap, q_values, odds

    overlap, q_values, odds = statistics(label_matrix)
    significant = (q_values <= fdr) & (odds > 1.0) & (overlap >= min_overlap)
    rows: list[dict[str, Any]] = []
    for token_index_value, label_index_value in np.argwhere(significant):
        rows.append(
            {
                "token": tokens[int(token_index_value)],
                "go_id": labels[int(label_index_value)],
                "overlap": int(overlap[token_index_value, label_index_value]),
                "token_df": int(token_counts[token_index_value]),
                "go_df": int(label_counts[label_index_value]),
                "odds_ratio": float(odds[token_index_value, label_index_value]),
                "q_value": float(q_values[token_index_value, label_index_value]),
            }
        )
    rows.sort(key=lambda row: (row["q_value"], -row["odds_ratio"], -row["overlap"], row["token"]))

    rng = np.random.default_rng(seed)
    lengths = [len(record.sequence) for record in records]
    null_counts: list[int] = []
    for _ in range(permutations):
        permutation = length_stratified_permutation(lengths, rng)
        null_overlap, null_q, null_odds = statistics(label_matrix[permutation])
        null_counts.append(int(((null_q <= fdr) & (null_odds > 1.0) & (null_overlap >= min_overlap)).sum()))
    observed = len(rows)
    empirical_p = (
        (1 + sum(count >= observed for count in null_counts)) / (permutations + 1)
        if permutations
        else None
    )
    summary = {
        "records": n_records,
        "eligible_tokens": len(tokens),
        "eligible_go_terms": len(labels),
        "tests": len(tokens) * len(labels),
        "significant_associations": observed,
        "significant_tokens": len({row["token"] for row in rows}),
        "significant_go_terms": len({row["go_id"] for row in rows}),
        "fdr": fdr,
        "min_overlap": min_overlap,
        "null_permutations": permutations,
        "null_significant_counts": null_counts,
        "null_mean": float(np.mean(null_counts)) if null_counts else None,
        "null_max": max(null_counts) if null_counts else None,
        "empirical_p": empirical_p,
    }
    return summary, rows


def bpe_tokenizer(path: Path) -> Callable[[str], Sequence[str]]:
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(path))
    return lambda sequence: tokenizer.encode(sequence).tokens


def runtime_tokenizer(path: Path) -> Callable[[str], Sequence[str]]:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    return lambda sequence: tokenizer.convert_ids_to_tokens(tokenizer.encode(sequence, add_special_tokens=False))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_graph(
    output_dir: Path,
    records: Sequence[AnnotatedSequence],
    token_counts: Sequence[Counter[str]],
    associations: Sequence[dict[str, Any]],
    go_names: dict[str, str],
    tokenizer_hash: str,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    significant_tokens = {row["token"] for row in associations}
    significant_go = {row["go_id"] for row in associations}
    node_count = 0
    edge_count = 0
    with (output_dir / "nodes.jsonl").open("w", encoding="utf-8") as nodes:
        for token in sorted(significant_tokens):
            entity_id = stable_token_id("omnigene_protein_bpe", token)
            row = {
                "entity_id": entity_id,
                "entity_type": "bio_sequence_token",
                "canonical_id": entity_id,
                "name": token,
                "source": "OmniGene intended protein BPE vocabulary",
                "description": "Frequency-derived protein BPE unit; not asserted to be a biological motif.",
                "organism": None,
                "metadata_json": json.dumps(
                    {"raw_token": token, "length": len(token), "tokenizer_sha256": tokenizer_hash},
                    separators=(",", ":"),
                ),
            }
            nodes.write(json.dumps(row) + "\n")
            node_count += 1
        for go_id in sorted(significant_go):
            row = {
                "entity_id": f"go_term:{go_id}",
                "entity_type": "go_term",
                "canonical_id": go_id,
                "name": go_names.get(go_id, go_id),
                "source": "Gene Ontology via SeqLit-DAG",
                "description": "Reference to an existing curated SeqLit-DAG GO node.",
                "organism": None,
                "metadata_json": "{}",
            }
            nodes.write(json.dumps(row) + "\n")
            node_count += 1
    with (output_dir / "edges.jsonl").open("w", encoding="utf-8") as edges:
        for record, counts in zip(records, token_counts, strict=True):
            for token in sorted(significant_tokens.intersection(counts)):
                row = {
                    "source_entity_id": stable_token_id("omnigene_protein_bpe", token),
                    "relation_type": "observed_in_sequence",
                    "target_entity_id": f"protein:{record.accession}",
                    "source": "deterministic protein BPE tokenization",
                    "source_record": f"protein:{record.accession}",
                    "evidence_level": "computed_exact_tokenization",
                    "confidence": 1.0,
                    "retrieval_score": None,
                    "verification_method": "exact BPE segmentation",
                    "database_version": f"tokenizer-sha256:{tokenizer_hash[:16]}",
                    "metadata_json": json.dumps({"occurrence_count": counts[token]}, separators=(",", ":")),
                }
                edges.write(json.dumps(row) + "\n")
                edge_count += 1
        for association in associations:
            token = association["token"]
            row = {
                "source_entity_id": stable_token_id("omnigene_protein_bpe", token),
                "relation_type": "statistically_associated_with",
                "target_entity_id": f"go_term:{association['go_id']}",
                "source": "SeqLit token enrichment analysis",
                "source_record": "data/seq_lit_dag_swissprot_2k/documents.jsonl",
                "evidence_level": "exploratory_statistical_association",
                "confidence": float(1.0 - association["q_value"]),
                "retrieval_score": None,
                "verification_method": "hypergeometric enrichment with BH-FDR",
                "database_version": f"tokenizer-sha256:{tokenizer_hash[:16]}",
                "metadata_json": json.dumps(
                    {key: value for key, value in association.items() if key != "token"},
                    separators=(",", ":"),
                ),
            }
            edges.write(json.dumps(row) + "\n")
            edge_count += 1
    manifest = {
        "dataset": "BioRAG sequence-token semantics pilot",
        "version": "0.1.0-exploratory",
        "claim_scope": "frequency-derived token association; tokens are not asserted to be motifs",
        "dag_view": "bio_sequence_token -> protein -> curated GO/evidence -> PubMed",
        "computed_edge": "bio_sequence_token -> statistically_associated_with -> GO",
        "tokenizer_sha256": tokenizer_hash,
        "node_count": node_count,
        "edge_count": edge_count,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"nodes": node_count, "edges": edge_count}


def render_report(result: dict[str, Any], go_names: dict[str, str]) -> str:
    lines = [
        "# Sequence Token Biological-Semantics Pilot",
        "",
        "## Scope",
        "",
        "This is an exploratory association analysis over parent-level Swiss-Prot proteins. A token is not assumed to be a motif, and a statistically associated edge is not curated biological evidence.",
        "The intended OmniGene protein BPE vocabulary is analyzed independently of the current merged tokenizer activation issue documented in `reports/omnigene_bio_token_audit.md`.",
        "",
        "## Controlled Comparison",
        "",
        "| Tokenization | Eligible tokens | GO terms | Significant token-GO pairs | Significant tokens | Null mean/max | Empirical p |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, payload in result["methods"].items():
        summary = payload["summary"]
        null_text = (
            f"{summary['null_mean']:.2f}/{summary['null_max']}" if summary["null_mean"] is not None else "not run"
        )
        empirical = f"{summary['empirical_p']:.4f}" if summary["empirical_p"] is not None else "not run"
        lines.append(
            f"| {name} | {summary['eligible_tokens']:,} | {summary['eligible_go_terms']:,} | "
            f"{summary['significant_associations']:,} | {summary['significant_tokens']:,} | {null_text} | {empirical} |"
        )
    lines += ["", "## Top Intended-BPE Associations", "", "| Token | Length | GO term | Support | Token df | GO df | Odds ratio | q |", "|---|---:|---|---:|---:|---:|---:|---:|"]
    for row in result["methods"]["intended_protein_bpe"]["associations"][:30]:
        go_label = f"{row['go_id']} {go_names.get(row['go_id'], '')}".strip()
        lines.append(
            f"| `{row['token']}` | {len(row['token'])} | {go_label} | {row['overlap']} | {row['token_df']} | "
            f"{row['go_df']} | {row['odds_ratio']:.2f} | {row['q_value']:.2e} |"
        )
    lines += [
        "",
        "## Interpretation Boundary",
        "",
        "- A positive result means token occurrence is associated with curated GO labels more often than expected after length-stratified label permutation.",
        "- It does not show that a token is a known motif, that the association is independent of homology, or that CPT learned the token semantics.",
        "- The fixed 3-mer and current runtime-token conditions indicate how much of the signal can be explained by ordinary local sequence composition.",
        "- Paper-grade motif claims require PROSITE/Pfam coordinate overlap and a UniRef50 family-held-out control.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=Path("data/seq_lit_dag_swissprot_2k/documents.jsonl"))
    parser.add_argument("--nodes", type=Path, default=Path("data/seq_lit_dag_swissprot_2k/nodes.jsonl"))
    parser.add_argument(
        "--protein-bpe",
        type=Path,
        default=Path("/autodl-fs/data/omnigene_v2/scripts/vocab/trained_bpe/protein_bpe_8k.json"),
    )
    parser.add_argument(
        "--runtime-tokenizer",
        type=Path,
        default=Path(
            "/root/autodl-tmp/huggingface/models--dnagpt--OmniGene-4-CPT-v2-merged/"
            "snapshots/332ed9582f41547beb2a2b6de228c9e53aae5500"
        ),
    )
    parser.add_argument("--min-token-df", type=int, default=10)
    parser.add_argument("--min-go-df", type=int, default=10)
    parser.add_argument("--max-df-fraction", type=float, default=0.5)
    parser.add_argument("--min-overlap", type=int, default=3)
    parser.add_argument("--fdr", type=float, default=0.05)
    parser.add_argument("--permutations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-json", type=Path, default=Path("reports/results/sequence_token_semantics_pilot.json"))
    parser.add_argument("--output-report", type=Path, default=Path("reports/sequence_token_semantics_pilot.md"))
    parser.add_argument("--graph-output", type=Path, default=Path("data/seq_token_semantics_pilot"))
    args = parser.parse_args()

    records = load_seq_lit_proteins(args.documents)
    go_names = load_go_names(args.nodes)
    methods: dict[str, Callable[[str], Sequence[str]]] = {
        "intended_protein_bpe": bpe_tokenizer(args.protein_bpe),
        "current_runtime_tokens": runtime_tokenizer(args.runtime_tokenizer),
        "overlapping_fixed_3mer": lambda sequence: fixed_kmers(sequence, 3),
    }
    result: dict[str, Any] = {
        "scope": "exploratory parent-level token-to-GO association",
        "records": len(records),
        "parameters": {
            "min_token_df": args.min_token_df,
            "min_go_df": args.min_go_df,
            "max_df_fraction": args.max_df_fraction,
            "min_overlap": args.min_overlap,
            "fdr": args.fdr,
            "permutations": args.permutations,
            "seed": args.seed,
        },
        "methods": {},
    }
    intended_counts: list[Counter[str]] | None = None
    intended_rows: list[dict[str, Any]] | None = None
    for name, tokenizer in methods.items():
        print(f"Analyzing {name}...", flush=True)
        token_lists, token_counts = tokenize_records(records, tokenizer)
        summary, associations = enrichment_analysis(
            records,
            token_lists,
            min_token_df=args.min_token_df,
            min_label_df=args.min_go_df,
            max_df_fraction=args.max_df_fraction,
            min_overlap=args.min_overlap,
            fdr=args.fdr,
            permutations=args.permutations,
            seed=args.seed,
        )
        summary["total_tokens"] = sum(map(len, token_lists))
        summary["unique_tokens"] = len({token for tokens in token_lists for token in tokens})
        summary["residues_per_token"] = sum(len(record.sequence) for record in records) / summary["total_tokens"]
        result["methods"][name] = {"summary": summary, "associations": associations}
        if name == "intended_protein_bpe":
            intended_counts = token_counts
            intended_rows = associations

    tokenizer_hash = file_sha256(args.protein_bpe)
    graph_counts = write_graph(
        args.graph_output,
        records,
        intended_counts or [],
        intended_rows or [],
        go_names,
        tokenizer_hash,
    )
    result["graph"] = {"path": str(args.graph_output), **graph_counts}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.output_report.write_text(render_report(result, go_names), encoding="utf-8")
    print(json.dumps({"json": str(args.output_json), "report": str(args.output_report), "graph": str(args.graph_output)}, indent=2))


if __name__ == "__main__":
    main()

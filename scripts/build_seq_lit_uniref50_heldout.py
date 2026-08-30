#!/usr/bin/env python3
"""Build a UniRef50-cluster-held-out sequence-to-function-to-paper split."""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_seq_lit_function_heldout import (
    invert_go,
    load_go_evidence,
    make_function_ground_truth,
)
from scripts.build_seq_lit_heldout import load_proteins, write_index_documents, write_index_fasta
from scripts.build_seq_lit_identity_heldout import (
    build_index_blast_database,
    file_sha256,
    middle_fragment,
    select_query_clusters,
    write_clusters,
)


UNIPROT_ACCESSION_COLUMN = 0
UNIREF50_COLUMN = 9


def open_mapping(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open(encoding="utf-8", errors="replace")


def extract_uniref50_mapping(
    path: Path,
    wanted_accessions: set[str],
    *,
    progress_every: int = 5_000_000,
) -> tuple[dict[str, str], dict[str, int]]:
    mapping: dict[str, str] = {}
    scanned = 0
    malformed = 0
    with open_mapping(path) as handle:
        for line in handle:
            scanned += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= UNIREF50_COLUMN:
                malformed += 1
                continue
            accession = parts[UNIPROT_ACCESSION_COLUMN]
            if accession in wanted_accessions and parts[UNIREF50_COLUMN]:
                mapping[accession] = parts[UNIREF50_COLUMN]
                if len(mapping) == len(wanted_accessions):
                    break
            if progress_every and scanned % progress_every == 0:
                print(
                    json.dumps(
                        {
                            "idmapping_rows": scanned,
                            "mapped_accessions": len(mapping),
                            "wanted_accessions": len(wanted_accessions),
                        }
                    ),
                    flush=True,
                )
    return mapping, {
        "idmapping_rows_scanned": scanned,
        "idmapping_malformed_rows": malformed,
        "mapped_accessions": len(mapping),
        "missing_accessions": len(wanted_accessions - set(mapping)),
    }


def clusters_from_uniref50(
    accessions: set[str],
    mapping: dict[str, str],
) -> tuple[dict[str, tuple[str, ...]], dict[str, str], dict[str, int]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for accession in sorted(accessions):
        cluster_id = mapping.get(accession) or f"UniRef50_UNMAPPED_{accession}"
        grouped[cluster_id].append(accession)
    clusters = {cluster_id: tuple(items) for cluster_id, items in sorted(grouped.items())}
    accession_cluster = {
        accession: cluster_id
        for cluster_id, members in clusters.items()
        for accession in members
    }
    sizes = [len(items) for items in clusters.values()]
    return clusters, accession_cluster, {
        "clusters": len(clusters),
        "singleton_clusters": sum(size == 1 for size in sizes),
        "largest_cluster": max(sizes, default=0),
        "mean_cluster_size": sum(sizes) / len(sizes) if sizes else 0.0,
    }


def write_mapping(path: Path, mapping: dict[str, str], accessions: set[str]) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for accession in sorted(accessions):
            row = {"accession": accession, "uniref50": mapping.get(accession)}
            handle.write(json.dumps(row) + "\n")


def write_queries(
    path: Path,
    query_accessions: list[str],
    proteins: dict[str, dict[str, Any]],
    truth: dict[str, dict[str, list[str]]],
    accession_cluster: dict[str, str],
    clusters: dict[str, tuple[str, ...]],
) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for accession in query_accessions:
            sequence = str(proteins[accession]["sequence"])
            cluster_id = accession_cluster[accession]
            row = {
                "id": f"seq_lit_uniref50_heldout:{accession}",
                "query": middle_fragment(sequence),
                "query_type": "uniref50_cluster_heldout_parent_middle_fragment",
                "heldout_accession": accession,
                "heldout_cluster_id": cluster_id,
                "heldout_cluster_size": len(clusters[cluster_id]),
                "expected_go_ids": truth[accession]["go_ids"],
                "expected_pmids": truth[accession]["pmids"],
                "relevant_index_accessions": truth[accession]["candidate_accessions"],
                "label_source": "shared low-frequency GO term plus index-side GOA paper evidence",
                "task": "uniref50_cluster_heldout_sequence_to_function_to_literature",
                "split_control": {
                    "cluster_source": "UniProt idmapping_selected UniRef50 column",
                    "entire_observed_uniref50_cluster_removed": True,
                },
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_manifest(
    *,
    source: Path,
    idmapping: Path,
    mapping_output: Path,
    proteins: dict[str, dict[str, Any]],
    mapping_stats: dict[str, int],
    cluster_stats: dict[str, int | float],
    clusters: dict[str, tuple[str, ...]],
    accession_cluster: dict[str, str],
    query_accessions: list[str],
    excluded: set[str],
    truth: dict[str, dict[str, list[str]]],
    index_documents: int,
    index_proteins: int,
    target_queries: int,
    min_go_df: int,
    max_go_df: int,
    seed: int,
) -> dict[str, Any]:
    query_set = set(query_accessions)
    index_accessions = set(proteins) - excluded
    selected_cluster_ids = {accession_cluster[accession] for accession in query_accessions}
    selected_sizes = [len(clusters[cluster_id]) for cluster_id in selected_cluster_ids]
    expected_go = [go_id for accession in query_accessions for go_id in truth[accession]["go_ids"]]
    expected_pmids = [pmid for accession in query_accessions for pmid in truth[accession]["pmids"]]
    substring_leaks = [
        accession
        for accession in query_accessions
        if any(str(proteins[accession]["sequence"]) in str(proteins[item]["sequence"]) for item in index_accessions)
    ]
    fragment_leaks = [
        accession
        for accession in query_accessions
        if any(
            middle_fragment(str(proteins[accession]["sequence"])) in str(proteins[item]["sequence"])
            for item in index_accessions
        )
    ]
    return {
        "dataset": "BioRAG-SeqLit-DAG UniRef50-cluster-held-out sequence-to-function-to-paper split",
        "claim_scope": (
            "All proteins sharing an observed UniRef50 cluster with a query are absent from the 2k index. "
            "This controls same-cluster leakage but is not a Pfam-clan, species, temporal, or remote-homology benchmark."
        ),
        "source": str(source),
        "seed": seed,
        "thresholds": {"go_df_range": [min_go_df, max_go_df]},
        "counts": {
            "source_proteins": len(proteins),
            "target_queries": target_queries,
            "heldout_queries": len(query_accessions),
            "selected_query_clusters": len(selected_cluster_ids),
            "excluded_cluster_proteins": len(excluded),
            "excluded_nonquery_proteins": len(excluded - query_set),
            "index_proteins": index_proteins,
            "index_documents": index_documents,
            "unique_expected_go_ids": len(set(expected_go)),
            "unique_expected_pmids": len(set(expected_pmids)),
            "query_go_pairs": len(expected_go),
            "query_pmid_pairs": len(expected_pmids),
        },
        "mapping": {
            **mapping_stats,
            **cluster_stats,
            "selected_non_singleton_clusters": sum(
                len(clusters[cluster_id]) > 1 for cluster_id in selected_cluster_ids
            ),
            "selected_cluster_mean_size": sum(selected_sizes) / len(selected_sizes) if selected_sizes else 0.0,
            "selected_cluster_max_size": max(selected_sizes, default=0),
        },
        "leakage": {
            "exact_accession_overlap": len(excluded & index_accessions),
            "query_cluster_overlap": sum(
                bool(set(clusters[accession_cluster[accession]]) & index_accessions)
                for accession in query_accessions
            ),
            "full_sequence_substring_overlap": len(substring_leaks),
            "substring_accessions": substring_leaks,
            "query_fragment_substring_overlap": len(fragment_leaks),
            "query_fragment_substring_accessions": fragment_leaks,
        },
        "reachability": {
            "queries_with_index_candidate": sum(bool(truth[a]["candidate_accessions"]) for a in query_accessions),
            "min_relevant_candidates": min((len(truth[a]["candidate_accessions"]) for a in query_accessions), default=0),
            "max_relevant_candidates": max((len(truth[a]["candidate_accessions"]) for a in query_accessions), default=0),
        },
        "files": {
            "idmapping_source": str(idmapping),
            "idmapping_source_size": idmapping.stat().st_size,
            "uniref50_mapping": mapping_output.name,
            "uniref50_mapping_sha256": file_sha256(mapping_output),
            "clusters": "clusters.jsonl",
            "queries": "queries.jsonl",
            "index_documents": "index_documents.jsonl",
            "index_fasta": "index.fasta",
            "index_blast_db": "blast/index",
        },
    }


def render_report(manifest: dict[str, Any]) -> str:
    counts = manifest["counts"]
    mapping = manifest["mapping"]
    leakage = manifest["leakage"]
    return "\n".join(
        [
            "# SeqLit-DAG UniRef50-Cluster-Held-Out Split",
            "",
            manifest["claim_scope"],
            "",
            f"- Queries: `{counts['heldout_queries']}` / target `{counts['target_queries']}`",
            f"- Index proteins: `{counts['index_proteins']}`",
            f"- UniRef50 mapping coverage: `{mapping['mapped_accessions']}/{counts['source_proteins']}`",
            f"- Excluded cluster proteins: `{counts['excluded_cluster_proteins']}`",
            f"- Excluded non-query proteins: `{counts['excluded_nonquery_proteins']}`",
            f"- Total clusters / singleton clusters: `{mapping['clusters']}` / `{mapping['singleton_clusters']}`",
            f"- Selected non-singleton clusters: `{mapping['selected_non_singleton_clusters']}`",
            f"- Selected cluster mean/max size: `{mapping['selected_cluster_mean_size']:.2f}` / `{mapping['selected_cluster_max_size']}`",
            f"- Query clusters represented in index: `{leakage['query_cluster_overlap']}`",
            f"- Full-sequence substring overlap: `{leakage['full_sequence_substring_overlap']}`",
            f"- Query-fragment exact substring overlap: `{leakage['query_fragment_substring_overlap']}`",
            f"- Unique expected GO IDs / PMIDs: `{counts['unique_expected_go_ids']}` / `{counts['unique_expected_pmids']}`",
            "",
            "Relevance is low-frequency shared GO plus index-side GOA citations. Retrieval models never generate labels. The split controls observed UniRef50 cluster leakage, while Pfam-clan and temporal controls remain future work.",
            "",
        ]
    )


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)
    idmapping = Path(args.idmapping)
    output.mkdir(parents=True, exist_ok=True)
    proteins = load_proteins(source / "documents.jsonl")
    evidence = load_go_evidence(source / "graph.sqlite")
    proteins_by_go = invert_go(evidence)

    mapping, mapping_stats = extract_uniref50_mapping(
        idmapping,
        set(proteins),
        progress_every=args.progress_every,
    )
    mapping_output = output / "uniref50_mapping.jsonl"
    write_mapping(mapping_output, mapping, set(proteins))
    clusters, accession_cluster, cluster_stats = clusters_from_uniref50(set(proteins), mapping)
    query_accessions, excluded = select_query_clusters(
        clusters,
        evidence,
        proteins_by_go,
        target=args.queries,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
        seed=args.seed,
        prioritize_non_singleton=True,
    )
    if len(query_accessions) != args.queries:
        raise RuntimeError(
            f"Only {len(query_accessions)} UniRef50-cluster queries remain reachable; requested {args.queries}"
        )
    truth = make_function_ground_truth(
        query_accessions,
        evidence,
        proteins_by_go,
        heldout_set=excluded,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
    )
    if len(truth) != len(query_accessions):
        raise RuntimeError("Final UniRef50 cluster exclusion invalidated one or more query labels")

    write_queries(output / "queries.jsonl", query_accessions, proteins, truth, accession_cluster, clusters)
    write_clusters(output / "clusters.jsonl", clusters, set(query_accessions), excluded)
    document_count = write_index_documents(
        source / "documents.jsonl", output / "index_documents.jsonl", excluded
    )
    fasta_count = write_index_fasta(output / "index.fasta", proteins, excluded)
    build_index_blast_database(output / "index.fasta", output / "blast" / "index")
    manifest = make_manifest(
        source=source,
        idmapping=idmapping,
        mapping_output=mapping_output,
        proteins=proteins,
        mapping_stats=mapping_stats,
        cluster_stats=cluster_stats,
        clusters=clusters,
        accession_cluster=accession_cluster,
        query_accessions=query_accessions,
        excluded=excluded,
        truth=truth,
        index_documents=document_count,
        index_proteins=fasta_count,
        target_queries=args.queries,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
        seed=args.seed,
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "REPORT.md").write_text(render_report(manifest), encoding="utf-8")
    print(json.dumps({"output": str(output), **manifest["counts"], "leakage": manifest["leakage"]}, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/seq_lit_dag_swissprot_2k")
    parser.add_argument("--output", default="data/seq_lit_dag_uniref50_heldout_2k")
    parser.add_argument(
        "--idmapping",
        default="/autodl-fs/data/open-rosalind-kb/standard/raw/uniprot/idmapping_selected.tab.gz",
    )
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--min-go-df", type=int, default=2)
    parser.add_argument("--max-go-df", type=int, default=20)
    parser.add_argument("--progress-every", type=int, default=5_000_000)
    parser.add_argument("--seed", type=int, default=20260831)
    return parser.parse_args()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build an identity-cluster-held-out sequence-to-function-to-paper split."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_seq_lit_function_heldout import (
    invert_go,
    load_go_evidence,
    make_function_ground_truth,
)
from scripts.build_seq_lit_heldout import load_proteins, write_index_documents, write_index_fasta


@dataclass(frozen=True, slots=True)
class SimilarityPair:
    left: str
    right: str
    identity: float
    shorter_coverage: float


class UnionFind:
    def __init__(self, items: Iterable[str]):
        self.parent = {item: item for item in items}
        self.size = {item: 1 for item in items}

    def find(self, item: str) -> str:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.size[left_root] < self.size[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.size[left_root] += self.size[right_root]


def normalize_blast_id(raw: str) -> str:
    parts = raw.split("|")
    return parts[1] if len(parts) >= 3 and parts[0] in {"sp", "tr"} else raw


def cluster_from_blast(
    path: Path,
    accessions: Sequence[str],
    *,
    min_identity: float,
    min_shorter_coverage: float,
) -> tuple[dict[str, tuple[str, ...]], dict[str, str], set[tuple[str, str]], dict[str, int]]:
    valid = set(accessions)
    union_find = UnionFind(valid)
    qualifying_pairs: set[tuple[str, str]] = set()
    stats: Counter[str] = Counter()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stats["alignment_rows"] += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                stats["malformed_rows"] += 1
                continue
            left = normalize_blast_id(parts[0])
            right = normalize_blast_id(parts[1])
            if left not in valid or right not in valid:
                stats["unknown_accession_rows"] += 1
                continue
            if left == right:
                stats["self_rows"] += 1
                continue
            identity = float(parts[2])
            alignment_length = float(parts[3])
            shorter_length = min(float(parts[4]), float(parts[5]))
            coverage = alignment_length / shorter_length if shorter_length else 0.0
            if identity < min_identity or coverage < min_shorter_coverage:
                continue
            pair = tuple(sorted((left, right)))
            qualifying_pairs.add(pair)
            union_find.union(left, right)

    grouped: dict[str, list[str]] = defaultdict(list)
    for accession in sorted(valid):
        grouped[union_find.find(accession)].append(accession)
    ordered_groups = sorted((tuple(items) for items in grouped.values()), key=lambda items: items[0])
    clusters = {f"identity_cluster:{index:05d}": items for index, items in enumerate(ordered_groups, start=1)}
    accession_cluster = {
        accession: cluster_id
        for cluster_id, members in clusters.items()
        for accession in members
    }
    stats["qualifying_pairs"] = len(qualifying_pairs)
    stats["clusters"] = len(clusters)
    stats["singleton_clusters"] = sum(len(items) == 1 for items in clusters.values())
    stats["largest_cluster"] = max(map(len, clusters.values()), default=0)
    return clusters, accession_cluster, qualifying_pairs, dict(stats)


def select_query_clusters(
    clusters: dict[str, tuple[str, ...]],
    evidence: dict[str, dict[str, set[str]]],
    proteins_by_go: dict[str, set[str]],
    *,
    target: int,
    min_go_df: int,
    max_go_df: int,
    seed: int,
    prioritize_non_singleton: bool = False,
) -> tuple[list[str], set[str]]:
    rng = random.Random(seed)
    cluster_ids = sorted(clusters)
    rng.shuffle(cluster_ids)
    if prioritize_non_singleton:
        cluster_ids.sort(key=lambda cluster_id: len(clusters[cluster_id]) == 1)
    selected_queries: list[str] = []
    excluded: set[str] = set()

    for cluster_id in cluster_ids:
        members = clusters[cluster_id]
        proposed_excluded = excluded | set(members)
        candidates = list(members)
        rng.shuffle(candidates)
        scored: list[tuple[tuple[int, int, int], str]] = []
        for accession in candidates:
            truth = make_function_ground_truth(
                [accession],
                evidence,
                proteins_by_go,
                heldout_set=proposed_excluded,
                min_go_df=min_go_df,
                max_go_df=max_go_df,
            ).get(accession)
            if truth:
                score = (
                    len(truth["go_ids"]),
                    len(truth["candidate_accessions"]),
                    len(truth["pmids"]),
                )
                scored.append((score, accession))
        if not scored:
            continue
        _score, accession = max(scored, key=lambda item: (item[0], item[1]))
        proposed_queries = [*selected_queries, accession]
        retained_truth = make_function_ground_truth(
            proposed_queries,
            evidence,
            proteins_by_go,
            heldout_set=proposed_excluded,
            min_go_df=min_go_df,
            max_go_df=max_go_df,
        )
        if len(retained_truth) != len(proposed_queries):
            continue
        selected_queries = proposed_queries
        excluded = proposed_excluded
        if len(selected_queries) >= target:
            break
    return selected_queries, excluded


def write_queries(
    path: Path,
    query_accessions: Sequence[str],
    proteins: dict[str, dict[str, Any]],
    truth: dict[str, dict[str, list[str]]],
    accession_cluster: dict[str, str],
    clusters: dict[str, tuple[str, ...]],
    *,
    min_identity: float,
    min_shorter_coverage: float,
) -> None:
    identity_tag = f"{min_identity:g}".replace(".", "p")
    with path.open("wt", encoding="utf-8") as handle:
        for accession in query_accessions:
            sequence = str(proteins[accession]["sequence"])
            cluster_id = accession_cluster[accession]
            row = {
                "id": f"seq_lit_identity{identity_tag}_heldout:{accession}",
                "query": middle_fragment(sequence),
                "query_type": "identity_cluster_heldout_parent_middle_fragment",
                "heldout_accession": accession,
                "heldout_cluster_id": cluster_id,
                "heldout_cluster_size": len(clusters[cluster_id]),
                "expected_go_ids": truth[accession]["go_ids"],
                "expected_pmids": truth[accession]["pmids"],
                "relevant_index_accessions": truth[accession]["candidate_accessions"],
                "label_source": "shared low-frequency GO term plus index-side GOA paper evidence",
                "task": "identity_cluster_heldout_sequence_to_function_to_literature",
                "split_control": {
                    "min_pair_identity": min_identity,
                    "min_shorter_sequence_coverage": min_shorter_coverage,
                    "entire_cluster_removed": True,
                },
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def middle_fragment(sequence: str, length: int = 160) -> str:
    start = max((len(sequence) - length) // 2, 0)
    return sequence[start : start + min(length, len(sequence))]


def write_clusters(
    path: Path,
    clusters: dict[str, tuple[str, ...]],
    query_accessions: set[str],
    excluded: set[str],
) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for cluster_id, members in clusters.items():
            for accession in members:
                row = {
                    "cluster_id": cluster_id,
                    "accession": accession,
                    "cluster_size": len(members),
                    "split": "heldout_excluded" if accession in excluded else "index",
                    "is_query": accession in query_accessions,
                }
                handle.write(json.dumps(row) + "\n")


def write_source_fasta(path: Path, proteins: dict[str, dict[str, Any]]) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for accession in sorted(proteins):
            row = proteins[accession]
            handle.write(f">sp|{accession}|{row.get('name') or accession}\n{row['sequence']}\n")


def run_all_vs_all(
    source_fasta: Path,
    database: Path,
    output: Path,
    *,
    threads: int,
    force: bool,
) -> None:
    if output.exists() and not force:
        return
    makeblastdb = shutil.which("makeblastdb")
    blastp = shutil.which("blastp")
    if not makeblastdb or not blastp:
        raise RuntimeError("BLAST+ makeblastdb and blastp are required")
    subprocess.run(
        [makeblastdb, "-in", str(source_fasta), "-dbtype", "prot", "-parse_seqids", "-out", str(database)],
        check=True,
    )
    subprocess.run(
        [
            blastp,
            "-query",
            str(source_fasta),
            "-db",
            str(database),
            "-out",
            str(output),
            "-outfmt",
            "6 qseqid sseqid pident length qlen slen evalue bitscore",
            "-evalue",
            "1e-3",
            "-max_target_seqs",
            "10000",
            "-num_threads",
            str(max(threads, 1)),
        ],
        check=True,
    )


def build_index_blast_database(index_fasta: Path, database: Path) -> None:
    makeblastdb = shutil.which("makeblastdb")
    if not makeblastdb:
        raise RuntimeError("BLAST+ makeblastdb is required")
    database.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [makeblastdb, "-in", str(index_fasta), "-dbtype", "prot", "-parse_seqids", "-out", str(database)],
        check=True,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_manifest(
    *,
    source: Path,
    proteins: dict[str, dict[str, Any]],
    query_accessions: Sequence[str],
    excluded: set[str],
    truth: dict[str, dict[str, list[str]]],
    clusters: dict[str, tuple[str, ...]],
    accession_cluster: dict[str, str],
    qualifying_pairs: set[tuple[str, str]],
    blast_stats: dict[str, int],
    index_documents: int,
    index_proteins: int,
    min_identity: float,
    min_shorter_coverage: float,
    min_go_df: int,
    max_go_df: int,
    seed: int,
    target_queries: int,
    blast_pairs_path: Path,
) -> dict[str, Any]:
    query_set = set(query_accessions)
    index_accessions = set(proteins) - excluded
    cross_split_pairs = [
        pair for pair in qualifying_pairs if (pair[0] in excluded) != (pair[1] in excluded)
    ]
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
    expected_go = [go_id for accession in query_accessions for go_id in truth[accession]["go_ids"]]
    expected_pmids = [pmid for accession in query_accessions for pmid in truth[accession]["pmids"]]
    selected_cluster_ids = {accession_cluster[accession] for accession in query_accessions}
    selected_sizes = [len(clusters[cluster_id]) for cluster_id in selected_cluster_ids]
    cluster_sizes = [len(items) for items in clusters.values()]
    return {
        "dataset": "BioRAG-SeqLit-DAG identity-cluster-held-out sequence-to-function-to-paper split",
        "claim_scope": (
            "Query clusters are removed from the index using BLASTP identity and shorter-sequence coverage. "
            "This is an identity-cluster control, not a Pfam-clan or remote-homology benchmark."
        ),
        "source": str(source),
        "seed": seed,
        "thresholds": {
            "min_pair_identity": min_identity,
            "min_shorter_sequence_coverage": min_shorter_coverage,
            "go_df_range": [min_go_df, max_go_df],
        },
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
        "clustering": {
            **blast_stats,
            "mean_cluster_size": sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else 0.0,
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
            "threshold_cross_split_pairs": len(cross_split_pairs),
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
            "blast_pairs": str(blast_pairs_path),
            "blast_pairs_sha256": file_sha256(blast_pairs_path),
            "clusters": "clusters.jsonl",
            "queries": "queries.jsonl",
            "index_documents": "index_documents.jsonl",
            "index_fasta": "index.fasta",
            "index_blast_db": "blast/index",
        },
    }


def render_report(manifest: dict[str, Any]) -> str:
    counts = manifest["counts"]
    clustering = manifest["clustering"]
    leakage = manifest["leakage"]
    thresholds = manifest["thresholds"]
    return "\n".join(
        [
            "# SeqLit-DAG Identity-Cluster-Held-Out Split",
            "",
            manifest["claim_scope"],
            "",
            f"- Queries: `{counts['heldout_queries']}` / target `{counts['target_queries']}`",
            f"- Index proteins: `{counts['index_proteins']}`",
            f"- Excluded cluster proteins: `{counts['excluded_cluster_proteins']}`",
            f"- Excluded non-query proteins: `{counts['excluded_nonquery_proteins']}`",
            f"- BLASTP identity threshold: `{thresholds['min_pair_identity']:.1f}%`",
            f"- Shorter-sequence coverage threshold: `{thresholds['min_shorter_sequence_coverage']:.2f}`",
            f"- Total clusters / singleton clusters: `{clustering['clusters']}` / `{clustering['singleton_clusters']}`",
            f"- Selected non-singleton clusters: `{clustering['selected_non_singleton_clusters']}`",
            f"- Selected cluster mean/max size: `{clustering['selected_cluster_mean_size']:.2f}` / `{clustering['selected_cluster_max_size']}`",
            f"- Threshold cross-split pairs: `{leakage['threshold_cross_split_pairs']}`",
            f"- Query clusters represented in index: `{leakage['query_cluster_overlap']}`",
            f"- Full-sequence substring overlap: `{leakage['full_sequence_substring_overlap']}`",
            f"- Query-fragment exact substring overlap: `{leakage['query_fragment_substring_overlap']}`",
            f"- Unique expected GO IDs / PMIDs: `{counts['unique_expected_go_ids']}` / `{counts['unique_expected_pmids']}`",
            "",
            "Relevance remains low-frequency shared GO plus index-side GOA citations. Model outputs never define labels. The control removes close identity clusters but does not establish Pfam-clan independence.",
            "",
        ]
    )


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    proteins = load_proteins(source / "documents.jsonl")
    evidence = load_go_evidence(source / "graph.sqlite")
    proteins_by_go = invert_go(evidence)

    source_fasta = output / "source.fasta"
    all_vs_all_db = output / "all_vs_all"
    blast_pairs = Path(args.blast_pairs) if args.blast_pairs else output / "all_vs_all.tsv"
    write_source_fasta(source_fasta, proteins)
    run_all_vs_all(
        source_fasta,
        all_vs_all_db,
        blast_pairs,
        threads=args.threads,
        force=args.force_blast,
    )
    clusters, accession_cluster, qualifying_pairs, blast_stats = cluster_from_blast(
        blast_pairs,
        list(proteins),
        min_identity=args.min_identity,
        min_shorter_coverage=args.min_shorter_coverage,
    )
    query_accessions, excluded = select_query_clusters(
        clusters,
        evidence,
        proteins_by_go,
        target=args.queries,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
        seed=args.seed,
        prioritize_non_singleton=args.prioritize_non_singleton,
    )
    if len(query_accessions) != args.queries:
        raise RuntimeError(
            f"Only {len(query_accessions)} identity-cluster queries remain reachable; requested {args.queries}"
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
        raise RuntimeError("Final identity-cluster exclusion invalidated one or more query labels")

    write_queries(
        output / "queries.jsonl",
        query_accessions,
        proteins,
        truth,
        accession_cluster,
        clusters,
        min_identity=args.min_identity,
        min_shorter_coverage=args.min_shorter_coverage,
    )
    write_clusters(output / "clusters.jsonl", clusters, set(query_accessions), excluded)
    document_count = write_index_documents(
        source / "documents.jsonl", output / "index_documents.jsonl", excluded
    )
    fasta_count = write_index_fasta(output / "index.fasta", proteins, excluded)
    build_index_blast_database(output / "index.fasta", output / "blast" / "index")
    manifest = make_manifest(
        source=source,
        proteins=proteins,
        query_accessions=query_accessions,
        excluded=excluded,
        truth=truth,
        clusters=clusters,
        accession_cluster=accession_cluster,
        qualifying_pairs=qualifying_pairs,
        blast_stats=blast_stats,
        index_documents=document_count,
        index_proteins=fasta_count,
        min_identity=args.min_identity,
        min_shorter_coverage=args.min_shorter_coverage,
        min_go_df=args.min_go_df,
        max_go_df=args.max_go_df,
        seed=args.seed,
        target_queries=args.queries,
        blast_pairs_path=blast_pairs,
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "REPORT.md").write_text(render_report(manifest), encoding="utf-8")
    print(json.dumps({"output": str(output), **manifest["counts"], "leakage": manifest["leakage"]}, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/seq_lit_dag_swissprot_2k")
    parser.add_argument("--output", default="data/seq_lit_dag_identity50_heldout_2k")
    parser.add_argument("--blast-pairs", default=None)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--min-identity", type=float, default=50.0)
    parser.add_argument("--min-shorter-coverage", type=float, default=0.8)
    parser.add_argument("--min-go-df", type=int, default=2)
    parser.add_argument("--max-go-df", type=int, default=20)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--force-blast", action="store_true")
    parser.add_argument("--prioritize-non-singleton", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

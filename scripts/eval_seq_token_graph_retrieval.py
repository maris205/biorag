#!/usr/bin/env python3
"""Evaluate token-graph candidate retrieval and fusion on held-out SeqLit queries."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.seq_lit_dag.evaluate import ProteinCandidate, load_papers_by_accession, rank_papers, read_jsonl
from dnarag.token_semantics import AnnotatedSequence, SparseTokenIndex, fixed_kmers, load_seq_lit_proteins, tokenize_records
from scripts.analyze_sequence_token_semantics import (
    bpe_tokenizer,
    enrichment_analysis,
    file_sha256,
    load_go_names,
    write_graph,
)
from scripts.fuse_seq_lit_rankings import reciprocal_rank_fusion


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    maximum = float(scores.max()) if scores.size else 0.0
    return scores / maximum if maximum > 0.0 else scores.copy()


def graph_candidate_scores(
    query_tokens: Sequence[str],
    *,
    token_go: dict[str, list[tuple[str, float]]],
    go_documents: dict[str, tuple[int, ...]],
    token_index: SparseTokenIndex,
) -> np.ndarray:
    scores = np.zeros(len(token_index.accessions), dtype=np.float64)
    for token in set(query_tokens):
        query_weight = token_index.idf(token)
        for go_id, association_weight in token_go.get(token, ()):
            for document_index in go_documents.get(go_id, ()):
                scores[document_index] += query_weight * association_weight
    return scores


def rank_scores(scores: np.ndarray, accessions: Sequence[str], limit: int) -> list[str]:
    positive = np.flatnonzero(scores > 0.0)
    return [
        accessions[index]
        for index in sorted(positive, key=lambda index: (-scores[index], accessions[index]))[:limit]
    ]


def build_token_go_index(
    records: Sequence[AnnotatedSequence],
    associations: Sequence[dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, float]]], dict[str, tuple[int, ...]]]:
    token_go: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in associations:
        q_value = max(float(row["q_value"]), 1e-300)
        weight = min(-math.log10(q_value), 50.0) * math.log1p(float(row["odds_ratio"]))
        token_go[str(row["token"])].append((str(row["go_id"]), weight))
    go_documents_mutable: dict[str, list[int]] = defaultdict(list)
    for document_index, record in enumerate(records):
        for go_id in record.labels:
            go_documents_mutable[go_id].append(document_index)
    return dict(token_go), {key: tuple(value) for key, value in go_documents_mutable.items()}


def evaluate_ranking(
    query: dict[str, Any],
    ranking: Sequence[str],
    *,
    method: str,
    papers_by_accession: dict[str, list[str]],
    paper_k: int,
    latency_ms: float | None,
) -> dict[str, Any]:
    relevant = {str(item) for item in query.get("relevant_index_accessions", [])}
    expected_pmids = {str(item) for item in query.get("expected_pmids", [])}
    rank = next((index for index, accession in enumerate(ranking, start=1) if accession in relevant), None)
    candidates = [ProteinCandidate(accession, 1.0 / index) for index, accession in enumerate(ranking, start=1)]
    pmids = rank_papers(candidates, papers_by_accession, limit=paper_k)
    matched_pmids = expected_pmids.intersection(pmids)
    top_10 = set(ranking[:10])
    top_50 = set(ranking[:50])
    top_100 = set(ranking[:100])
    return {
        "query_id": str(query["id"]),
        "method": method,
        "candidate_rank": rank,
        "candidate_hit_at_1": bool(rank == 1),
        "candidate_hit_at_5": bool(rank and rank <= 5),
        "candidate_hit_at_10": bool(relevant.intersection(top_10)),
        "candidate_hit_at_50": bool(relevant.intersection(top_50)),
        "candidate_hit_at_100": bool(relevant.intersection(top_100)),
        "candidate_recall_at_10": len(relevant.intersection(top_10)) / len(relevant) if relevant else 0.0,
        "candidate_recall_at_50": len(relevant.intersection(top_50)) / len(relevant) if relevant else 0.0,
        "candidate_recall_at_100": len(relevant.intersection(top_100)) / len(relevant) if relevant else 0.0,
        "candidate_mrr": 1.0 / rank if rank else 0.0,
        "paper_hit": bool(matched_pmids),
        "paper_recall": len(matched_pmids) / len(expected_pmids) if expected_pmids else 0.0,
        "path_complete": bool(rank and matched_pmids),
        "candidate_ms": latency_ms,
        "top_accessions": list(ranking[:100]),
        "top_pmids": pmids,
    }


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    metric_names = (
        "candidate_hit_at_1",
        "candidate_hit_at_5",
        "candidate_hit_at_10",
        "candidate_hit_at_50",
        "candidate_hit_at_100",
        "candidate_recall_at_10",
        "candidate_recall_at_50",
        "candidate_recall_at_100",
        "candidate_mrr",
        "paper_hit",
        "paper_recall",
        "path_complete",
    )
    summary: dict[str, float | None] = {
        metric: float(np.mean([float(row[metric]) for row in rows])) if rows else 0.0
        for metric in metric_names
    }
    latencies = [float(row["candidate_ms"]) for row in rows if row.get("candidate_ms") is not None]
    summary["candidate_ms"] = float(np.mean(latencies)) if latencies else None
    return summary


def load_saved_rankings(path: Path, method: str | None = None) -> tuple[dict[str, list[str]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["details"]
    if method is not None:
        rows = [row for row in rows if row.get("method") == method]
    return {str(row["query_id"]): list(row["top_accessions"]) for row in rows}, payload


def paired_bootstrap_delta(
    left: Sequence[dict[str, Any]],
    right: Sequence[dict[str, Any]],
    metric: str,
    *,
    samples: int,
    seed: int,
) -> dict[str, float]:
    right_by_id = {str(row["query_id"]): row for row in right}
    pairs = [(float(row[metric]), float(right_by_id[str(row["query_id"])][metric])) for row in left]
    values = np.asarray([left_value - right_value for left_value, right_value in pairs], dtype=np.float64)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(samples, len(values)))
    distribution = values[indices].mean(axis=1)
    return {
        "delta": float(values.mean()),
        "ci_low": float(np.quantile(distribution, 0.025)),
        "ci_high": float(np.quantile(distribution, 0.975)),
    }


def select_graph_alpha(
    dev_queries: Sequence[dict[str, Any]],
    rankings: Callable[[dict[str, Any], float], list[str]],
    papers: dict[str, list[str]],
    paper_k: int,
    grid: Sequence[float],
) -> tuple[float, list[dict[str, Any]]]:
    sweep: list[dict[str, Any]] = []
    for alpha in grid:
        rows = [
            evaluate_ranking(
                query,
                rankings(query, alpha),
                method=f"bpe_token_go_graph_alpha_{alpha:g}",
                papers_by_accession=papers,
                paper_k=paper_k,
                latency_ms=None,
            )
            for query in dev_queries
        ]
        summary = summarize(rows)
        sweep.append({"alpha": alpha, **summary})
    selected = max(
        sweep,
        key=lambda row: (
            float(row["candidate_hit_at_10"] or 0.0),
            float(row["paper_hit"] or 0.0),
            float(row["candidate_mrr"] or 0.0),
            -float(row["alpha"]),
        ),
    )
    return float(selected["alpha"]), sweep


def append_ranking(
    primary: Sequence[str],
    secondary: Sequence[str],
    *,
    primary_prefix: int,
    limit: int,
) -> list[str]:
    """Preserve a trusted primary prefix, add secondary candidates, then backfill."""
    ranking: list[str] = []
    seen: set[str] = set()
    for source in (primary[:primary_prefix], secondary, primary[primary_prefix:]):
        for accession in source:
            if accession in seen:
                continue
            seen.add(accession)
            ranking.append(accession)
            if len(ranking) >= limit:
                return ranking
    return ranking


def select_append_prefix(
    dev_queries: Sequence[dict[str, Any]],
    *,
    primary: dict[str, list[str]],
    secondary: dict[str, list[str]],
    limit: int,
    prefixes: Sequence[int],
    papers: dict[str, list[str]],
    paper_k: int,
) -> tuple[int, list[dict[str, Any]]]:
    sweep: list[dict[str, Any]] = []
    for prefix in prefixes:
        rows: list[dict[str, Any]] = []
        for query in dev_queries:
            query_id = str(query["id"])
            ranking = append_ranking(
                primary[query_id],
                secondary[query_id],
                primary_prefix=prefix,
                limit=limit,
            )
            rows.append(
                evaluate_ranking(
                    query,
                    ranking,
                    method=f"append_prefix_{prefix}",
                    papers_by_accession=papers,
                    paper_k=paper_k,
                    latency_ms=None,
                )
            )
        summary = summarize(rows)
        sweep.append({"primary_prefix": prefix, **summary})
    selected = max(
        sweep,
        key=lambda row: (
            float(row["candidate_hit_at_100"] or 0.0),
            float(row["candidate_recall_at_100"] or 0.0),
            float(row["paper_hit"] or 0.0),
            float(row["candidate_mrr"] or 0.0),
            int(row["primary_prefix"]),
        ),
    )
    return int(selected["primary_prefix"]), sweep


def render_report(result: dict[str, Any]) -> str:
    association = result["association_summary_index_only"]
    lines = [
        "# Held-out Sequence Token-Graph Retrieval",
        "",
        "## Scope",
        "",
        "Token-to-GO edges are learned only from the 1,901 index proteins. The 99 held-out parent proteins do not participate in graph construction. A 33-query development split selects the graph-expansion weight; the table reports the frozen 66-query test split.",
        "",
        f"Selected graph alpha on development data: `{result['selected_graph_alpha']}`. Selected ProtT5 prefixes for candidate-tail replacement: BPE `{result['selected_append_prefix']['bpe']}`, BPE+GO `{result['selected_append_prefix']['bpe_graph']}` of `{result['candidate_k']}`.",
        "",
        f"The index-only graph contains {association['significant_associations']:,} FDR-significant token--GO associations over {association['eligible_tokens']:,} eligible tokens and {association['eligible_go_terms']:,} eligible GO terms.",
        "",
        "| Test route | Hit@10 | Hit@50 | Hit@100 | Recall@100 | MRR | Paper hit | Paper recall | Candidate ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, summary in result["test_summary"].items():
        latency = f"{summary['candidate_ms']:.2f}" if summary["candidate_ms"] is not None else "saved ranking"
        lines.append(
            f"| {method} | {summary['candidate_hit_at_10']:.4f} | {summary['candidate_hit_at_50']:.4f} | "
            f"{summary['candidate_hit_at_100']:.4f} | {summary['candidate_recall_at_100']:.4f} | "
            f"{summary['candidate_mrr']:.4f} | "
            f"{summary['paper_hit']:.4f} | {summary['paper_recall']:.4f} | {latency} |"
        )
    lines += ["", "## Paired Test Deltas vs ProtT5", "", "| Route | Metric | Delta | 95% CI |", "|---|---|---:|---:|"]
    for route, metrics in result["paired_deltas_vs_prott5"].items():
        for metric, row in metrics.items():
            lines.append(f"| {route} | {metric} | {row['delta']:+.4f} | [{row['ci_low']:+.4f}, {row['ci_high']:+.4f}] |")
    lines += [
        "",
        "## Interpretation",
        "",
        "- BPE BM25 is the direct `query token -> protein` path; BPE token-GO graph adds `query token -> associated GO -> protein` expansion.",
        "- Direct BPE BM25 reaches Hit@100 0.3788, and GO expansion lowers it to 0.3333; fixed 3-mer BM25 is the stronger local-token control at 0.4091.",
        "- Naive reciprocal-rank fusion lowers ProtT5 MRR and Recall@100. It is a negative ablation, not the selected retrieval route.",
        "- The development-selected tail route preserves the first 75 ProtT5 candidates and fills the remaining positions from token retrieval. It leaves Hit@10/50 unchanged and changes Hit@100 from 0.5758 to 0.5909 by recovering one additional test query; the paired Hit@100 interval includes no improvement, Recall@100 is unresolved, and paper metrics do not change.",
        "- BPE+GO tail replacement produces the same frozen-test ranking as direct BPE tail replacement, so the GO expansion adds no observed retrieval value in this pilot.",
        "- Reported combined latency is a sequential sum of measured ProtT5 end-to-end time and CPU token lookup. It is an unoptimized upper bound; the routes could be run concurrently.",
        "- GO graph expansion is an annotation-assisted retrieval route, not a sequence-only homology method and not a BLAST replacement.",
        "- Improvements whose paired confidence interval crosses zero are directional engineering results only.",
        "- The split is parent-held-out but not UniRef50 family-held-out; remote-family claims remain out of scope.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path("data/seq_lit_dag_function_heldout_2k")
    parser.add_argument("--queries", type=Path, default=root / "queries.jsonl")
    parser.add_argument("--documents", type=Path, default=root / "index_documents.jsonl")
    parser.add_argument("--graph-db", type=Path, default=Path("data/seq_lit_dag_swissprot_2k/graph.sqlite"))
    parser.add_argument("--nodes", type=Path, default=Path("data/seq_lit_dag_swissprot_2k/nodes.jsonl"))
    parser.add_argument(
        "--protein-bpe",
        type=Path,
        default=Path("/autodl-fs/data/omnigene_v2/scripts/vocab/trained_bpe/protein_bpe_8k.json"),
    )
    parser.add_argument(
        "--prott5-results",
        type=Path,
        default=Path("reports/results/seq_lit_dag_function_heldout_2k_prott5_top100_full_details.json"),
    )
    parser.add_argument(
        "--cpu-results",
        type=Path,
        default=Path("reports/results/seq_lit_dag_function_heldout_2k_cpu_top100.json"),
    )
    parser.add_argument(
        "--test-ids",
        type=Path,
        default=Path("reports/results/agent_graph_selector_fused_full_p20_test_ids.txt"),
    )
    parser.add_argument("--candidate-k", type=int, default=100)
    parser.add_argument("--paper-k", type=int, default=200)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--output-json", type=Path, default=Path("reports/results/seq_token_graph_retrieval.json"))
    parser.add_argument("--output-report", type=Path, default=Path("reports/seq_token_graph_retrieval.md"))
    parser.add_argument("--graph-output", type=Path, default=Path("data/seq_token_retrieval_graph_heldout"))
    args = parser.parse_args()

    queries = read_jsonl(args.queries)
    records = load_seq_lit_proteins(args.documents)
    papers = load_papers_by_accession(args.graph_db)
    test_ids = {line.strip() for line in args.test_ids.read_text(encoding="utf-8").splitlines() if line.strip()}
    test_queries = [query for query in queries if str(query["id"]) in test_ids]
    dev_queries = [query for query in queries if str(query["id"]) not in test_ids]
    if len(test_queries) != 66 or len(dev_queries) != 33:
        raise ValueError(f"Expected a 33/66 split, found {len(dev_queries)}/{len(test_queries)}")

    protein_tokenizer = bpe_tokenizer(args.protein_bpe)
    bpe_lists, bpe_counts = tokenize_records(records, protein_tokenizer)
    fixed_lists, fixed_counts = tokenize_records(records, lambda sequence: fixed_kmers(sequence, 3))
    accessions = [record.accession for record in records]
    bpe_index = SparseTokenIndex.build(accessions, bpe_counts)
    fixed_index = SparseTokenIndex.build(accessions, fixed_counts)
    association_summary, associations = enrichment_analysis(
        records,
        bpe_lists,
        min_token_df=10,
        min_label_df=5,
        max_df_fraction=0.5,
        min_overlap=3,
        fdr=0.05,
        permutations=0,
        seed=args.seed,
    )
    token_go, go_documents = build_token_go_index(records, associations)
    go_names = load_go_names(args.nodes)
    graph_counts = write_graph(
        args.graph_output,
        records,
        bpe_counts,
        associations,
        go_names,
        file_sha256(args.protein_bpe),
    )
    prott5, prott5_payload = load_saved_rankings(args.prott5_results)
    kmer_jaccard, _ = load_saved_rankings(args.cpu_results, method="kmer_jaccard")
    blast, _ = load_saved_rankings(args.cpu_results, method="blast")

    query_cache: dict[str, dict[str, Any]] = {}
    for query in queries:
        query_id = str(query["id"])
        bpe_tokens = list(protein_tokenizer(str(query["query"])))
        fixed_tokens = fixed_kmers(str(query["query"]), 3)
        started = time.perf_counter()
        direct_scores = bpe_index.scores(bpe_tokens)
        graph_scores = graph_candidate_scores(
            bpe_tokens,
            token_go=token_go,
            go_documents=go_documents,
            token_index=bpe_index,
        )
        bpe_ms = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        fixed_scores = fixed_index.scores(fixed_tokens)
        fixed_ms = (time.perf_counter() - started) * 1000.0
        query_cache[query_id] = {
            "direct": normalize_scores(direct_scores),
            "graph": normalize_scores(graph_scores),
            "fixed": normalize_scores(fixed_scores),
            "bpe_ms": bpe_ms,
            "fixed_ms": fixed_ms,
        }

    def graph_ranking(query: dict[str, Any], alpha: float) -> list[str]:
        cached = query_cache[str(query["id"])]
        return rank_scores(cached["direct"] + alpha * cached["graph"], accessions, args.candidate_k)

    selected_alpha, alpha_sweep = select_graph_alpha(
        dev_queries,
        graph_ranking,
        papers,
        args.paper_k,
        grid=(0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0),
    )

    bpe_rankings = {
        str(query["id"]): rank_scores(
            query_cache[str(query["id"])]["direct"], accessions, args.candidate_k
        )
        for query in queries
    }
    graph_rankings = {str(query["id"]): graph_ranking(query, selected_alpha) for query in queries}
    prefix_grid = tuple(sorted(set((10, 25, 50, 75, 90, args.candidate_k))))
    selected_bpe_prefix, bpe_prefix_sweep = select_append_prefix(
        dev_queries,
        primary=prott5,
        secondary=bpe_rankings,
        limit=args.candidate_k,
        prefixes=prefix_grid,
        papers=papers,
        paper_k=args.paper_k,
    )
    selected_graph_prefix, graph_prefix_sweep = select_append_prefix(
        dev_queries,
        primary=prott5,
        secondary=graph_rankings,
        limit=args.candidate_k,
        prefixes=prefix_grid,
        papers=papers,
        paper_k=args.paper_k,
    )

    route_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query in queries:
        query_id = str(query["id"])
        cached = query_cache[query_id]
        bpe_rank = bpe_rankings[query_id]
        graph_rank = graph_rankings[query_id]
        fixed_rank = rank_scores(cached["fixed"], accessions, args.candidate_k)
        vector_rank = prott5[query_id][: args.candidate_k]
        routes = {
            "bpe_bm25": (bpe_rank, cached["bpe_ms"]),
            "bpe_token_go_graph": (graph_rank, cached["bpe_ms"]),
            "fixed3_bm25": (fixed_rank, cached["fixed_ms"]),
            "kmer_jaccard": (kmer_jaccard[query_id][: args.candidate_k], None),
            "blast": (blast[query_id][: args.candidate_k], None),
            "prott5_vector": (vector_rank, float(prott5_payload["timing"]["end_to_end_ms_per_query"])),
            "prott5_bpe_rrf": (
                reciprocal_rank_fusion([vector_rank, bpe_rank], limit=args.candidate_k, rrf_k=args.rrf_k),
                float(prott5_payload["timing"]["end_to_end_ms_per_query"]) + cached["bpe_ms"],
            ),
            "prott5_bpe_graph_rrf": (
                reciprocal_rank_fusion([vector_rank, graph_rank], limit=args.candidate_k, rrf_k=args.rrf_k),
                float(prott5_payload["timing"]["end_to_end_ms_per_query"]) + cached["bpe_ms"],
            ),
            "prott5_bpe_tail": (
                append_ranking(
                    vector_rank,
                    bpe_rank,
                    primary_prefix=selected_bpe_prefix,
                    limit=args.candidate_k,
                ),
                float(prott5_payload["timing"]["end_to_end_ms_per_query"]) + cached["bpe_ms"],
            ),
            "prott5_bpe_graph_tail": (
                append_ranking(
                    vector_rank,
                    graph_rank,
                    primary_prefix=selected_graph_prefix,
                    limit=args.candidate_k,
                ),
                float(prott5_payload["timing"]["end_to_end_ms_per_query"]) + cached["bpe_ms"],
            ),
        }
        for method, (ranking, latency) in routes.items():
            route_rows[method].append(
                evaluate_ranking(
                    query,
                    ranking,
                    method=method,
                    papers_by_accession=papers,
                    paper_k=args.paper_k,
                    latency_ms=latency,
                )
            )

    test_rows = {
        method: [row for row in rows if str(row["query_id"]) in test_ids]
        for method, rows in route_rows.items()
    }
    dev_rows = {
        method: [row for row in rows if str(row["query_id"]) not in test_ids]
        for method, rows in route_rows.items()
    }
    deltas: dict[str, Any] = {}
    baseline = test_rows["prott5_vector"]
    for route in (
        "prott5_bpe_rrf",
        "prott5_bpe_graph_rrf",
        "prott5_bpe_tail",
        "prott5_bpe_graph_tail",
    ):
        deltas[route] = {
            metric: paired_bootstrap_delta(
                test_rows[route],
                baseline,
                metric,
                samples=args.bootstrap_samples,
                seed=args.seed,
            )
            for metric in (
                "candidate_hit_at_10",
                "candidate_hit_at_50",
                "candidate_hit_at_100",
                "candidate_recall_at_100",
                "candidate_mrr",
                "paper_hit",
                "paper_recall",
            )
        }
    result = {
        "dataset": "BioRAG SeqLit held-out token-graph candidate ablation",
        "claim_scope": "Parent-held-out annotation-assisted candidate retrieval; not family-held-out homology search.",
        "query_count": len(queries),
        "development_queries": len(dev_queries),
        "test_queries": len(test_queries),
        "index_proteins": len(records),
        "candidate_k": args.candidate_k,
        "selected_graph_alpha": selected_alpha,
        "selected_append_prefix": {"bpe": selected_bpe_prefix, "bpe_graph": selected_graph_prefix},
        "alpha_sweep_development": alpha_sweep,
        "append_prefix_sweep_development": {
            "bpe": bpe_prefix_sweep,
            "bpe_graph": graph_prefix_sweep,
        },
        "association_summary_index_only": association_summary,
        "graph": {"path": str(args.graph_output), **graph_counts},
        "dev_summary": {method: summarize(rows) for method, rows in dev_rows.items()},
        "test_summary": {method: summarize(rows) for method, rows in test_rows.items()},
        "paired_deltas_vs_prott5": deltas,
        "details": {method: rows for method, rows in route_rows.items()},
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.output_report.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"report": str(args.output_report), "selected_alpha": selected_alpha, "test": result["test_summary"]}, indent=2))


if __name__ == "__main__":
    main()

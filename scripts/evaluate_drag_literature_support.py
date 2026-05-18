#!/usr/bin/env python3
"""Evaluate PubMed literature support inside DRAG sequence graph communities.

This is a biological-meaning ablation for the paper. It asks whether sequence
DRAG communities contain non-random shared literature evidence after mapping
graph nodes to NCBI Gene IDs and then to PubMed IDs through local gene2pubmed.

The result should be interpreted as evidence-structure support, not as proof of
mechanism. PubMed IDs are used as local evidence anchors; title/abstract
resolution can be added later for human-readable case studies.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from scripts.analyze_view_graph import enrich_labels_from_chroma, read_graph
from scripts.evaluate_drag_functional_enrichment import (
    DEFAULT_GRAPHS,
    add_bh_q_values,
    build_graph,
    detect_communities,
    expand_node_xrefs,
    hypergeom_tail,
    initial_node_xrefs,
    load_graph_xrefs,
    parse_graphs,
)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    graph_specs = parse_graphs(args.graphs)
    started = time.perf_counter()
    graphs: dict[str, dict[str, Any]] = {}
    needed = {"uniprot": set(), "ncbi": set(), "ensembl": set()}

    for name, graph_path in graph_specs.items():
        if args.progress:
            print(f"[drag-literature] read {name}: {graph_path}", flush=True)
        graph_data = read_graph(Path(graph_path))
        if not args.no_chroma_labels:
            enrich_labels_from_chroma(graph_data, config_path=args.config)
        graph = build_graph(graph_data)
        communities = detect_communities(graph)
        for community_id, members in enumerate(communities):
            for node_id in members:
                graph.nodes[node_id]["community"] = community_id
        node_ids = sorted(str(node_id) for node_id in graph.nodes())
        node_xrefs = initial_node_xrefs(graph, node_ids)
        for values in node_xrefs.values():
            needed["uniprot"].update(values["uniprot"])
            needed["ncbi"].update(values["ncbi"])
            needed["ensembl"].update(values["ensembl"])
        graphs[name] = {
            "path": str(graph_path),
            "graph_data": graph_data,
            "graph": graph,
            "communities": communities,
            "node_xrefs": node_xrefs,
        }

    xref_index = load_graph_xrefs(
        Path(args.graph_db),
        needed_ensembl=needed["ensembl"],
        needed_uniprot=needed["uniprot"],
        needed_ncbi=needed["ncbi"],
    )
    all_ncbi: set[str] = set()
    for payload in graphs.values():
        expand_node_xrefs(payload["node_xrefs"], xref_index)
        for values in payload["node_xrefs"].values():
            all_ncbi.update(values["ncbi"])

    if args.progress:
        print(f"[drag-literature] load gene2pubmed for {len(all_ncbi)} NCBI Gene IDs", flush=True)
    gene_pmids = load_gene2pubmed(
        config.root / "raw" / "ncbi_gene" / "gene2pubmed.gz",
        wanted_ncbi=all_ncbi,
        max_pmids_per_gene=args.max_pmids_per_gene,
    )

    results: dict[str, Any] = {}
    for name, payload in graphs.items():
        if args.progress:
            print(f"[drag-literature] analyze {name}", flush=True)
        results[name] = analyze_literature_support(
            payload,
            gene_pmids=gene_pmids,
            min_community_size=args.min_community_size,
            min_observed=args.min_observed,
            max_global_rate=args.max_global_rate,
            top_n=args.top_n,
        )

    result = {
        "dataset": "dnarag_drag_literature_support",
        "config": args.config,
        "graph_db": args.graph_db,
        "scope": {
            "source": "NCBI gene2pubmed.gz",
            "background": "PubMed-annotated nodes within each analyzed graph",
            "multiple_testing": "Benjamini-Hochberg within each graph",
            "claim_boundary": "Shared literature evidence is a community-level support signal, not proof of mechanism.",
        },
        "parameters": {
            "min_community_size": args.min_community_size,
            "min_observed": args.min_observed,
            "max_global_rate": args.max_global_rate,
            "top_n": args.top_n,
            "max_pmids_per_gene": args.max_pmids_per_gene,
        },
        "annotation_summary": {
            "needed_ncbi_gene_ids": len(all_ncbi),
            "gene2pubmed_mapped_genes": len(gene_pmids),
            "gene2pubmed_unique_pmids": len({pmid for pmids in gene_pmids.values() for pmid in pmids}),
        },
        "graphs": results,
        "comparison": comparison_rows(results),
        "elapsed_s": round(time.perf_counter() - started, 3),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "graphs"}, indent=2, ensure_ascii=False))


def load_gene2pubmed(
    path: Path,
    *,
    wanted_ncbi: set[str],
    max_pmids_per_gene: int,
) -> dict[str, set[str]]:
    if not path.exists() or not wanted_ncbi:
        return {}
    result: dict[str, set[str]] = defaultdict(set)
    cap = max(int(max_pmids_per_gene or 0), 0)
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            _tax_id, gene_id, pmid = parts[:3]
            if gene_id not in wanted_ncbi:
                continue
            if cap and len(result[gene_id]) >= cap:
                continue
            result[gene_id].add(pmid)
    return dict(result)


def analyze_literature_support(
    payload: dict[str, Any],
    *,
    gene_pmids: dict[str, set[str]],
    min_community_size: int,
    min_observed: int,
    max_global_rate: float,
    top_n: int,
) -> dict[str, Any]:
    graph: nx.Graph = payload["graph"]
    node_xrefs = payload["node_xrefs"]
    node_pmids = build_node_pmids(node_xrefs, gene_pmids)
    pmid_enrichment = enrich_pmids(
        graph,
        payload["communities"],
        node_pmids=node_pmids,
        min_community_size=min_community_size,
        min_observed=min_observed,
        max_global_rate=max_global_rate,
        top_n=top_n,
    )
    community_support = community_literature_support(
        payload["communities"],
        node_pmids=node_pmids,
        min_community_size=min_community_size,
    )
    components = sorted((len(item) for item in nx.connected_components(graph)), reverse=True)
    mapped_ncbi_nodes = sum(1 for values in node_xrefs.values() if values["ncbi"])
    pmid_nodes = sum(1 for values in node_pmids.values() if values)
    return {
        "summary": {
            "graph": payload["path"],
            "target": payload["graph_data"].get("meta", {}).get("target"),
            "recipe": payload["graph_data"].get("meta", {}).get("recipe"),
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "components": len(components),
            "communities": len(payload["communities"]),
            "mapped_ncbi_nodes": mapped_ncbi_nodes,
            "pubmed_annotated_nodes": pmid_nodes,
            "unique_pmids": len({pmid for values in node_pmids.values() for pmid in values}),
            "communities_with_shared_pmids": sum(1 for row in community_support if row["shared_pmid_count"] > 0),
            "top_shared_pmids": pmid_enrichment["top_pmids"][:3],
        },
        "pubmed": pmid_enrichment,
        "community_support": community_support[:top_n],
    }


def build_node_pmids(
    node_xrefs: dict[str, dict[str, set[str]]],
    gene_pmids: dict[str, set[str]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for node_id, values in node_xrefs.items():
        pmids: set[str] = set()
        for ncbi in values["ncbi"]:
            pmids.update(gene_pmids.get(ncbi, set()))
        result[node_id] = pmids
    return result


def enrich_pmids(
    graph: nx.Graph,
    communities: list[set[str]],
    *,
    node_pmids: dict[str, set[str]],
    min_community_size: int,
    min_observed: int,
    max_global_rate: float,
    top_n: int,
) -> dict[str, Any]:
    annotated_nodes = {node_id for node_id, values in node_pmids.items() if values}
    population = len(annotated_nodes)
    global_counts: Counter[str] = Counter()
    for node_id in annotated_nodes:
        global_counts.update(node_pmids.get(node_id) or set())
    rows: list[dict[str, Any]] = []
    for community_id, members in enumerate(communities):
        if len(members) < min_community_size:
            continue
        annotated_members = sorted(member for member in members if member in annotated_nodes)
        if not annotated_members:
            continue
        local_counts: Counter[str] = Counter()
        for node_id in annotated_members:
            local_counts.update(node_pmids.get(node_id) or set())
        for pmid, observed in local_counts.items():
            if observed < min_observed:
                continue
            global_count = global_counts[pmid]
            if global_count <= 0:
                continue
            global_rate = global_count / max(population, 1)
            if max_global_rate > 0 and global_rate > max_global_rate:
                continue
            local_rate = observed / max(len(annotated_members), 1)
            rows.append(
                {
                    "community": community_id,
                    "community_size": len(members),
                    "annotated_community_nodes": len(annotated_members),
                    "pmid": pmid,
                    "observed": observed,
                    "global_count": global_count,
                    "population": population,
                    "local_rate": round(local_rate, 4),
                    "global_rate": round(global_rate, 4),
                    "enrichment": enrichment(local_rate, global_rate),
                    "p_value": hypergeom_tail(
                        population=population,
                        successes=global_count,
                        draws=len(annotated_members),
                        observed=observed,
                    ),
                }
            )
    add_bh_q_values(rows)
    rows.sort(key=lambda row: (float(row.get("q_value") or 1.0), float(row.get("p_value") or 1.0), -int(row["observed"])))
    return {
        "annotated_nodes": population,
        "unique_pmids": len(global_counts),
        "tested_pmids": len(rows),
        "top_pmids": rows[:top_n],
        "community_top_pmids": top_pmids_by_community(rows, top_n=3),
    }


def community_literature_support(
    communities: list[set[str]],
    *,
    node_pmids: dict[str, set[str]],
    min_community_size: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for community_id, members in enumerate(communities):
        if len(members) < min_community_size:
            continue
        annotated_members = [member for member in members if node_pmids.get(member)]
        local_counts: Counter[str] = Counter()
        link_count = 0
        for node_id in annotated_members:
            values = node_pmids.get(node_id) or set()
            link_count += len(values)
            local_counts.update(values)
        shared = {pmid: count for pmid, count in local_counts.items() if count >= 2}
        rows.append(
            {
                "community": community_id,
                "community_size": len(members),
                "pubmed_annotated_nodes": len(annotated_members),
                "coverage": round(len(annotated_members) / max(len(members), 1), 4),
                "node_pmid_links": link_count,
                "unique_pmids": len(local_counts),
                "shared_pmid_count": len(shared),
                "top_shared_pmids": [
                    {"pmid": pmid, "nodes": count}
                    for pmid, count in sorted(shared.items(), key=lambda item: (-item[1], item[0]))[:5]
                ],
            }
        )
    rows.sort(key=lambda row: (-(row["shared_pmid_count"]), -row["pubmed_annotated_nodes"], -row["community_size"]))
    return rows


def top_pmids_by_community(rows: list[dict[str, Any]], *, top_n: int) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["community"])].append(row)
    return {key: value[:top_n] for key, value in sorted(grouped.items(), key=lambda item: int(item[0]))}


def comparison_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, payload in results.items():
        summary = payload["summary"]
        top = (summary.get("top_shared_pmids") or [None])[0]
        rows.append(
            {
                "graph": name,
                "target": summary.get("target"),
                "recipe": summary.get("recipe"),
                "nodes": summary.get("nodes"),
                "mapped_ncbi_nodes": summary.get("mapped_ncbi_nodes"),
                "pubmed_annotated_nodes": summary.get("pubmed_annotated_nodes"),
                "unique_pmids": summary.get("unique_pmids"),
                "communities_with_shared_pmids": summary.get("communities_with_shared_pmids"),
                "top_shared_pmid": compact_pmid(top),
            }
        )
    return rows


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# DRAG Literature Support",
        "",
        "This report maps DRAG graph communities to PubMed evidence through local NCBI Gene IDs and `gene2pubmed.gz`. It reports community-level shared literature structure, not proof of mechanism.",
        "",
        "## Coverage and Top Shared Evidence",
        "",
        "| Graph | Nodes | NCBI-mapped nodes | PubMed nodes | Unique PMIDs | Communities with shared PMIDs | Top shared PMID |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["comparison"]:
        lines.append(
            f"| {row['graph']} | {row['nodes']} | {row['mapped_ncbi_nodes']} | "
            f"{row['pubmed_annotated_nodes']} | {row['unique_pmids']} | "
            f"{row['communities_with_shared_pmids']} | {row['top_shared_pmid']} |"
        )
    lines.extend(["", "## Top Shared PMIDs By Graph", ""])
    for name, payload in result["graphs"].items():
        rows = payload["pubmed"]["top_pmids"][:8]
        lines.extend(
            [
                f"### {name}",
                "",
                "| Community | PMID | Observed | Global | Enrichment | p | q |",
                "|---:|---|---:|---:|---:|---:|---:|",
            ]
        )
        if not rows:
            lines.append("| - | no shared PMID enrichment | 0 | 0 | 0 | 1 | 1 |")
        for row in rows:
            lines.append(
                f"| {row['community']} | PMID:{row['pmid']} | "
                f"{row['observed']}/{row['annotated_community_nodes']} | {row['global_count']}/{row['population']} | "
                f"{row['enrichment']} | {row['p_value']} | {row['q_value']} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "- Shared PubMed IDs are evidence anchors for community-level literature support, not causal biological proof.",
            "- Coverage depends on HGNC/NCBI mappings; non-human protein entries may have limited NCBI Gene mapping through the current local graph.",
            "- This layer complements GO/Reactome enrichment by showing that some graph communities also share literature evidence.",
            "- Title/abstract resolution for top PMIDs is a useful next case-study step.",
            "",
        ]
    )
    return "\n".join(lines)


def compact_pmid(row: dict[str, Any] | None) -> str:
    if not row:
        return "-"
    return (
        f"PMID:{row.get('pmid')} "
        f"({row.get('observed')}/{row.get('annotated_community_nodes')}, "
        f"x{row.get('enrichment')}, q={row.get('q_value')})"
    )


def enrichment(value: float, baseline: float) -> float | str:
    if baseline == 0:
        return "inf" if value > 0 else 0.0
    return round(value / baseline, 4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate PubMed literature support for DRAG graph communities")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--graph-db", default="indexes/standard/graph/graph.sqlite")
    parser.add_argument("--graphs", default="default", help="default or comma-separated name=path entries")
    parser.add_argument("--output", default="reports/drag_literature_support_10k.json")
    parser.add_argument("--markdown", default="reports/drag_literature_support_10k.md")
    parser.add_argument("--min-community-size", type=int, default=3)
    parser.add_argument("--min-observed", type=int, default=2)
    parser.add_argument("--max-global-rate", type=float, default=0.5)
    parser.add_argument("--top-n", type=int, default=25)
    parser.add_argument("--max-pmids-per-gene", type=int, default=0)
    parser.add_argument("--no-chroma-labels", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

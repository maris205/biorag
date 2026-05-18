#!/usr/bin/env python3
"""Evaluate GO and Reactome enrichment in DRAG sequence graph communities."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from scripts.analyze_view_graph import enrich_labels_from_chroma, label_values, read_graph


DEFAULT_GRAPHS = {
    "dna_vector": "indexes/standard/graph/views/dna_sequence_window_10k.sqlite",
    "dna_blast": "indexes/standard/graph/views/dna_sequence_window_blast_10k.sqlite",
    "dna_hybrid": "indexes/standard/graph/views/dna_sequence_window_hybrid_10k.sqlite",
    "protein_vector": "indexes/standard/graph/views/protein_sequence_window_10k.sqlite",
    "protein_blast": "indexes/standard/graph/views/protein_sequence_window_blast_10k.sqlite",
    "protein_hybrid": "indexes/standard/graph/views/protein_sequence_window_hybrid_10k.sqlite",
}


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    started = time.perf_counter()
    graph_specs = parse_graphs(args.graphs)
    graphs: dict[str, dict[str, Any]] = {}
    needed = {"uniprot": set(), "ncbi": set(), "ensembl": set()}

    for name, graph_path in graph_specs.items():
        if args.progress:
            print(f"[drag-functional] read {name}: {graph_path}", flush=True)
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
    all_uniprot: set[str] = set()
    all_ncbi: set[str] = set()
    for payload in graphs.values():
        expand_node_xrefs(payload["node_xrefs"], xref_index)
        for values in payload["node_xrefs"].values():
            all_uniprot.update(values["uniprot"])
            all_ncbi.update(values["ncbi"])

    if args.progress:
        print(
            f"[drag-functional] annotation IDs: uniprot={len(all_uniprot)} ncbi={len(all_ncbi)}",
            flush=True,
        )
    annotations = load_annotations(
        root=config.root,
        uniprot_ids=all_uniprot,
        ncbi_gene_ids=all_ncbi,
        include_gene2go=not args.skip_gene2go,
        progress=args.progress,
    )

    results: dict[str, Any] = {}
    for name, payload in graphs.items():
        if args.progress:
            print(f"[drag-functional] enrich {name}", flush=True)
        results[name] = analyze_enrichment(
            payload,
            annotations=annotations,
            min_community_size=args.min_community_size,
            min_observed=args.min_observed,
            max_global_rate=args.max_global_rate,
            top_n=args.top_n,
        )

    result = {
        "dataset": "dnarag_drag_functional_enrichment",
        "config": args.config,
        "graph_db": args.graph_db,
        "scope": {
            "sources": ["Reactome UniProt2Reactome", "Reactome NCBI2Reactome", "GOA human GAF", "NCBI gene2go"],
            "background": "annotated nodes within each analyzed graph and source",
            "multiple_testing": "Benjamini-Hochberg within each graph/source",
            "claim_boundary": "Functional enrichment is a community-level annotation signal, not proof of mechanism.",
        },
        "parameters": {
            "min_community_size": args.min_community_size,
            "min_observed": args.min_observed,
            "max_global_rate": args.max_global_rate,
            "top_n": args.top_n,
            "skip_gene2go": args.skip_gene2go,
        },
        "annotation_summary": annotation_summary(annotations),
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


def build_graph(graph_data: dict[str, Any]) -> nx.Graph:
    graph = nx.Graph()
    for entity_id, node in graph_data["nodes"].items():
        graph.add_node(entity_id, **node)
    for edge in graph_data["edges"]:
        source = str(edge["source"])
        target = str(edge["target"])
        weight = float(edge.get("confidence") or 0.0)
        existing = graph.get_edge_data(source, target)
        if existing is None or weight > float(existing.get("weight") or 0.0):
            graph.add_edge(source, target, weight=weight)
    return graph


def detect_communities(graph: nx.Graph) -> list[set[str]]:
    if graph.number_of_nodes() == 0:
        return []
    if graph.number_of_edges() == 0:
        return [{str(node)} for node in graph.nodes()]
    communities = list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
    return [set(str(node) for node in community) for community in sorted(communities, key=len, reverse=True)]


def initial_node_xrefs(graph: nx.Graph, node_ids: list[str]) -> dict[str, dict[str, set[str]]]:
    result: dict[str, dict[str, set[str]]] = {}
    for node_id in node_ids:
        values = {"uniprot": set(), "ncbi": set(), "ensembl": set()}
        if node_id.startswith("protein_sequence:"):
            values["uniprot"].add(node_id.split(":", 1)[1])
        labels = graph.nodes[node_id].get("labels") or {}
        for gene_id in label_values(labels, "gene_id"):
            gene = strip_ensembl_version(str(gene_id))
            if gene.startswith("ENSG"):
                values["ensembl"].add(gene)
        result[node_id] = values
    return result


def load_graph_xrefs(
    graph_db: Path,
    *,
    needed_ensembl: set[str],
    needed_uniprot: set[str],
    needed_ncbi: set[str],
) -> dict[str, dict[str, set[str]]]:
    """Load HGNC-mediated xrefs for needed Ensembl, UniProt, and NCBI IDs."""
    index: dict[str, dict[str, set[str]]] = {
        "ensembl_to_hgnc": defaultdict(set),
        "uniprot_to_hgnc": defaultdict(set),
        "ncbi_to_hgnc": defaultdict(set),
        "hgnc_to_ensembl": defaultdict(set),
        "hgnc_to_uniprot": defaultdict(set),
        "hgnc_to_ncbi": defaultdict(set),
    }
    if not graph_db.exists():
        return index
    with sqlite3.connect(f"file:{graph_db}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT source_entity_id, relation_type, target_entity_id
            FROM edges
            WHERE relation_type IN ('has_ensembl_xref', 'has_uniprot_xref', 'has_ncbi_gene_xref')
            """
        )
        for row in rows:
            source = str(row["source_entity_id"])
            relation = str(row["relation_type"])
            target = str(row["target_entity_id"])
            if relation == "has_ensembl_xref" and target.startswith("ensembl_gene:"):
                ensembl = strip_ensembl_version(target.split(":", 1)[1])
                if not needed_ensembl or ensembl in needed_ensembl:
                    index["ensembl_to_hgnc"][ensembl].add(source)
                index["hgnc_to_ensembl"][source].add(ensembl)
            elif relation == "has_uniprot_xref" and target.startswith("protein:"):
                uniprot = target.split(":", 1)[1]
                if not needed_uniprot or uniprot in needed_uniprot:
                    index["uniprot_to_hgnc"][uniprot].add(source)
                index["hgnc_to_uniprot"][source].add(uniprot)
            elif relation == "has_ncbi_gene_xref" and target.startswith("ncbi_gene:"):
                ncbi = target.split(":", 1)[1]
                if not needed_ncbi or ncbi in needed_ncbi:
                    index["ncbi_to_hgnc"][ncbi].add(source)
                index["hgnc_to_ncbi"][source].add(ncbi)
    return index


def expand_node_xrefs(node_xrefs: dict[str, dict[str, set[str]]], xref_index: dict[str, dict[str, set[str]]]) -> None:
    for values in node_xrefs.values():
        hgnc_ids: set[str] = set()
        for ensembl in list(values["ensembl"]):
            hgnc_ids.update(xref_index["ensembl_to_hgnc"].get(ensembl, set()))
        for uniprot in list(values["uniprot"]):
            hgnc_ids.update(xref_index["uniprot_to_hgnc"].get(uniprot, set()))
        for ncbi in list(values["ncbi"]):
            hgnc_ids.update(xref_index["ncbi_to_hgnc"].get(ncbi, set()))
        for hgnc in hgnc_ids:
            values["ensembl"].update(xref_index["hgnc_to_ensembl"].get(hgnc, set()))
            values["uniprot"].update(xref_index["hgnc_to_uniprot"].get(hgnc, set()))
            values["ncbi"].update(xref_index["hgnc_to_ncbi"].get(hgnc, set()))


def load_annotations(
    *,
    root: Path,
    uniprot_ids: set[str],
    ncbi_gene_ids: set[str],
    include_gene2go: bool,
    progress: bool,
) -> dict[str, Any]:
    raw = root / "raw"
    go_terms = load_go_terms(raw / "go" / "go-basic.obo")
    annotations = {
        "go_by_uniprot": defaultdict(dict),
        "go_by_ncbi": defaultdict(dict),
        "reactome_by_uniprot": defaultdict(dict),
        "reactome_by_ncbi": defaultdict(dict),
        "terms": {},
    }
    if progress:
        print("[drag-functional] load Reactome UniProt mappings", flush=True)
    load_reactome(
        raw / "reactome" / "UniProt2Reactome_All_Levels.txt",
        wanted=uniprot_ids,
        output=annotations["reactome_by_uniprot"],
        terms=annotations["terms"],
    )
    if progress:
        print("[drag-functional] load Reactome NCBI mappings", flush=True)
    load_reactome(
        raw / "reactome" / "NCBI2Reactome_All_Levels.txt",
        wanted=ncbi_gene_ids,
        output=annotations["reactome_by_ncbi"],
        terms=annotations["terms"],
    )
    if progress:
        print("[drag-functional] load GOA human mappings", flush=True)
    load_goa_human(
        raw / "go" / "goa_human.gaf.gz",
        wanted_uniprot=uniprot_ids,
        output=annotations["go_by_uniprot"],
        terms=annotations["terms"],
        go_terms=go_terms,
    )
    if include_gene2go:
        if progress:
            print("[drag-functional] load NCBI gene2go mappings", flush=True)
        load_gene2go(
            raw / "ncbi_gene" / "gene2go.gz",
            wanted_ncbi=ncbi_gene_ids,
            output=annotations["go_by_ncbi"],
            terms=annotations["terms"],
            go_terms=go_terms,
        )
    return annotations


def load_go_terms(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    terms: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    with path.open("rt", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line == "[Term]":
                if current and current.get("id"):
                    terms[str(current["id"])] = current
                current = {}
                continue
            if line.startswith("["):
                if current and current.get("id"):
                    terms[str(current["id"])] = current
                current = None
                continue
            if current is None or not line or ": " not in line:
                continue
            key, value = line.split(": ", 1)
            if key in {"id", "name", "namespace"}:
                current[key] = value
            elif key == "is_obsolete" and value == "true":
                current["obsolete"] = True
    if current and current.get("id"):
        terms[str(current["id"])] = current
    return terms


def load_reactome(
    path: Path,
    *,
    wanted: set[str],
    output: dict[str, dict[str, dict[str, Any]]],
    terms: dict[str, dict[str, Any]],
) -> None:
    if not path.exists() or not wanted:
        return
    with path.open("rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            source_id, pathway_id, url, name, evidence, organism = parts[:6]
            if source_id not in wanted:
                continue
            term = {
                "id": pathway_id,
                "name": name,
                "source": "reactome",
                "url": url,
                "evidence": evidence,
                "organism": organism,
            }
            output[source_id][pathway_id] = term
            terms[f"reactome:{pathway_id}"] = term


def load_goa_human(
    path: Path,
    *,
    wanted_uniprot: set[str],
    output: dict[str, dict[str, dict[str, Any]]],
    terms: dict[str, dict[str, Any]],
    go_terms: dict[str, dict[str, Any]],
) -> None:
    if not path.exists() or not wanted_uniprot:
        return
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.startswith("!"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 15:
                continue
            uniprot = parts[1]
            if uniprot not in wanted_uniprot:
                continue
            qualifier = parts[3]
            go_id = parts[4]
            evidence = parts[6]
            aspect = parts[8]
            ontology = go_terms.get(go_id) or {}
            name = ontology.get("name") or go_id
            term = {
                "id": go_id,
                "name": name,
                "source": "go",
                "evidence": evidence,
                "qualifier": qualifier,
                "aspect": aspect,
                "namespace": ontology.get("namespace"),
                "organism": "Homo sapiens",
            }
            output[uniprot][go_id] = term
            terms[f"go:{go_id}"] = term


def load_gene2go(
    path: Path,
    *,
    wanted_ncbi: set[str],
    output: dict[str, dict[str, dict[str, Any]]],
    terms: dict[str, dict[str, Any]],
    go_terms: dict[str, dict[str, Any]],
) -> None:
    if not path.exists() or not wanted_ncbi:
        return
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                continue
            _tax_id, gene_id, go_id, evidence, qualifier, go_term, pubmed, category = parts[:8]
            if gene_id not in wanted_ncbi:
                continue
            ontology = go_terms.get(go_id) or {}
            term = {
                "id": go_id,
                "name": ontology.get("name") or go_term,
                "source": "go",
                "evidence": evidence,
                "qualifier": qualifier,
                "aspect": category,
                "namespace": ontology.get("namespace"),
                "pubmed": pubmed,
            }
            output[gene_id][go_id] = term
            terms[f"go:{go_id}"] = term


def analyze_enrichment(
    payload: dict[str, Any],
    *,
    annotations: dict[str, Any],
    min_community_size: int,
    min_observed: int,
    max_global_rate: float,
    top_n: int,
) -> dict[str, Any]:
    graph: nx.Graph = payload["graph"]
    node_xrefs = payload["node_xrefs"]
    node_terms = build_node_terms(node_xrefs, annotations)
    source_results = {
        "go": enrich_source(
            graph,
            payload["communities"],
            node_terms=node_terms["go"],
            terms=annotations["terms"],
            source="go",
            min_community_size=min_community_size,
            min_observed=min_observed,
            max_global_rate=max_global_rate,
            top_n=top_n,
        ),
        "reactome": enrich_source(
            graph,
            payload["communities"],
            node_terms=node_terms["reactome"],
            terms=annotations["terms"],
            source="reactome",
            min_community_size=min_community_size,
            min_observed=min_observed,
            max_global_rate=max_global_rate,
            top_n=top_n,
        ),
    }
    components = sorted((len(item) for item in nx.connected_components(graph)), reverse=True)
    return {
        "summary": {
            "graph": payload["path"],
            "target": payload["graph_data"].get("meta", {}).get("target"),
            "recipe": payload["graph_data"].get("meta", {}).get("recipe"),
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "components": len(components),
            "communities": len(payload["communities"]),
            "annotated_nodes": {
                "go": source_results["go"]["annotated_nodes"],
                "reactome": source_results["reactome"]["annotated_nodes"],
            },
            "top_go": source_results["go"]["top_terms"][:3],
            "top_reactome": source_results["reactome"]["top_terms"][:3],
        },
        "go": source_results["go"],
        "reactome": source_results["reactome"],
    }


def build_node_terms(node_xrefs: dict[str, dict[str, set[str]]], annotations: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    result = {"go": {}, "reactome": {}}
    for node_id, values in node_xrefs.items():
        go_terms: set[str] = set()
        reactome_terms: set[str] = set()
        for uniprot in values["uniprot"]:
            go_terms.update(annotations["go_by_uniprot"].get(uniprot, {}).keys())
            reactome_terms.update(annotations["reactome_by_uniprot"].get(uniprot, {}).keys())
        for ncbi in values["ncbi"]:
            go_terms.update(annotations["go_by_ncbi"].get(ncbi, {}).keys())
            reactome_terms.update(annotations["reactome_by_ncbi"].get(ncbi, {}).keys())
        result["go"][node_id] = go_terms
        result["reactome"][node_id] = reactome_terms
    return result


def enrich_source(
    graph: nx.Graph,
    communities: list[set[str]],
    *,
    node_terms: dict[str, set[str]],
    terms: dict[str, dict[str, Any]],
    source: str,
    min_community_size: int,
    min_observed: int,
    max_global_rate: float,
    top_n: int,
) -> dict[str, Any]:
    annotated_nodes = {node_id for node_id, values in node_terms.items() if values}
    population = len(annotated_nodes)
    global_counts: Counter[str] = Counter()
    for node_id in annotated_nodes:
        global_counts.update(node_terms.get(node_id) or set())
    rows: list[dict[str, Any]] = []
    for community_id, members in enumerate(communities):
        if len(members) < min_community_size:
            continue
        annotated_members = sorted(member for member in members if member in annotated_nodes)
        if not annotated_members:
            continue
        local_counts: Counter[str] = Counter()
        for node_id in annotated_members:
            local_counts.update(node_terms.get(node_id) or set())
        for term_id, observed in local_counts.items():
            if observed < min_observed:
                continue
            global_count = global_counts[term_id]
            if global_count <= 0:
                continue
            global_rate = global_count / max(population, 1)
            if max_global_rate > 0 and global_rate > max_global_rate:
                continue
            local_rate = observed / max(len(annotated_members), 1)
            term = terms.get(f"{source}:{term_id}") or {"id": term_id, "name": term_id, "source": source}
            rows.append(
                {
                    "community": community_id,
                    "community_size": len(members),
                    "annotated_community_nodes": len(annotated_members),
                    "term_id": term_id,
                    "term_name": term.get("name") or term_id,
                    "source": source,
                    "aspect": term.get("aspect"),
                    "organism": term.get("organism"),
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
        "term_count": len(global_counts),
        "tested_terms": len(rows),
        "top_terms": rows[:top_n],
        "community_top_terms": top_terms_by_community(rows, top_n=3),
    }


def add_bh_q_values(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    ordered = sorted(enumerate(rows), key=lambda item: float(item[1].get("p_value") or 1.0))
    m = len(ordered)
    q_by_index: dict[int, float] = {}
    previous = 1.0
    for rank_from_end, (original_index, row) in enumerate(reversed(ordered), start=1):
        rank = m - rank_from_end + 1
        p_value = float(row.get("p_value") or 1.0)
        q_value = min(previous, p_value * m / max(rank, 1), 1.0)
        previous = q_value
        q_by_index[original_index] = q_value
    for index, row in enumerate(rows):
        row["q_value"] = round(q_by_index.get(index, 1.0), 6)


def top_terms_by_community(rows: list[dict[str, Any]], *, top_n: int) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["community"])].append(row)
    return {key: value[:top_n] for key, value in sorted(grouped.items(), key=lambda item: int(item[0]))}


def comparison_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, payload in results.items():
        summary = payload["summary"]
        rows.append(
            {
                "graph": name,
                "target": summary.get("target"),
                "recipe": summary.get("recipe"),
                "nodes": summary.get("nodes"),
                "communities": summary.get("communities"),
                "go_annotated_nodes": summary.get("annotated_nodes", {}).get("go"),
                "reactome_annotated_nodes": summary.get("annotated_nodes", {}).get("reactome"),
                "top_go": compact_term((summary.get("top_go") or [None])[0]),
                "top_reactome": compact_term((summary.get("top_reactome") or [None])[0]),
            }
        )
    return rows


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# DRAG Functional Enrichment",
        "",
        "This report maps DRAG graph communities to GO and Reactome annotations through local UniProt, NCBI Gene, and HGNC cross-references. Enrichment is tested against annotated nodes within each graph/source, with Benjamini-Hochberg correction.",
        "",
        "## Coverage and Top Signals",
        "",
        "| Graph | Nodes | GO annotated | Reactome annotated | Top GO signal | Top Reactome signal |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in result["comparison"]:
        lines.append(
            f"| {row['graph']} | {row['nodes']} | {row['go_annotated_nodes']} | "
            f"{row['reactome_annotated_nodes']} | {row['top_go']} | {row['top_reactome']} |"
        )
    lines.extend(["", "## Top Terms By Graph", ""])
    for name, payload in result["graphs"].items():
        lines.extend([f"### {name}", ""])
        for source in ("go", "reactome"):
            rows = payload[source]["top_terms"][:8]
            lines.extend(
                [
                    f"#### {source.upper()}",
                    "",
                    "| Community | Term | Observed | Global | Enrichment | p | q |",
                    "|---:|---|---:|---:|---:|---:|---:|",
                ]
            )
            if not rows:
                lines.append("| - | no mapped enrichment | 0 | 0 | 0 | 1 | 1 |")
            for term in rows:
                lines.append(
                    f"| {term['community']} | {term['term_id']} {term['term_name']} | "
                    f"{term['observed']}/{term['annotated_community_nodes']} | {term['global_count']}/{term['population']} | "
                    f"{term['enrichment']} | {term['p_value']} | {term['q_value']} |"
                )
            lines.append("")
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "- These are community-level functional annotation signals, not proof of mechanism.",
            "- Reactome mappings use local UniProt2Reactome and NCBI2Reactome files.",
            "- GO mappings use local GOA human and NCBI gene2go files; coverage depends on whether graph nodes map to UniProt or NCBI Gene IDs.",
            "- The strongest paper claim is that DRAG communities can be connected to curated biological vocabularies, enabling hypothesis-generating analysis for agents.",
            "",
        ]
    )
    return "\n".join(lines)


def compact_term(row: dict[str, Any] | None) -> str:
    if not row:
        return "-"
    return (
        f"{row.get('term_id')} {row.get('term_name')} "
        f"({row.get('observed')}/{row.get('annotated_community_nodes')}, "
        f"x{row.get('enrichment')}, q={row.get('q_value')})"
    )


def annotation_summary(annotations: dict[str, Any]) -> dict[str, Any]:
    return {
        "go_by_uniprot_ids": len(annotations["go_by_uniprot"]),
        "go_by_ncbi_ids": len(annotations["go_by_ncbi"]),
        "reactome_by_uniprot_ids": len(annotations["reactome_by_uniprot"]),
        "reactome_by_ncbi_ids": len(annotations["reactome_by_ncbi"]),
        "term_records": len(annotations["terms"]),
    }


def hypergeom_tail(*, population: int, successes: int, draws: int, observed: int) -> float:
    if population <= 0 or successes <= 0 or draws <= 0 or observed <= 0:
        return 1.0
    max_k = min(successes, draws)
    denom = log_comb(population, draws)
    values = []
    for k in range(observed, max_k + 1):
        failures = draws - k
        if failures > population - successes:
            continue
        values.append(math.exp(log_comb(successes, k) + log_comb(population - successes, failures) - denom))
    return round(min(sum(values), 1.0), 6)


def log_comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def enrichment(value: float, baseline: float) -> float | str:
    if baseline == 0:
        return "inf" if value > 0 else 0.0
    return round(value / baseline, 4)


def strip_ensembl_version(value: str) -> str:
    return str(value).split(".", 1)[0]


def parse_graphs(value: str) -> dict[str, Path]:
    if value.strip().lower() == "default":
        return {name: Path(path) for name, path in DEFAULT_GRAPHS.items()}
    result: dict[str, Path] = {}
    for item in value.split(","):
        if not item.strip():
            continue
        if "=" in item:
            name, path = item.split("=", 1)
            result[name.strip()] = Path(path.strip())
        else:
            path = Path(item.strip())
            result[path.stem] = path
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate GO and Reactome enrichment for DRAG graph communities")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--graph-db", default="indexes/standard/graph/graph.sqlite")
    parser.add_argument("--graphs", default="default", help="default or comma-separated name=path entries")
    parser.add_argument("--output", default="reports/drag_functional_enrichment_10k.json")
    parser.add_argument("--markdown", default="reports/drag_functional_enrichment_10k.md")
    parser.add_argument("--min-community-size", type=int, default=3)
    parser.add_argument("--min-observed", type=int, default=2)
    parser.add_argument("--max-global-rate", type=float, default=0.5)
    parser.add_argument("--top-n", type=int, default=25)
    parser.add_argument("--skip-gene2go", action="store_true")
    parser.add_argument("--no-chroma-labels", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

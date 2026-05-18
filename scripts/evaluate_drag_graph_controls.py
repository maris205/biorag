#!/usr/bin/env python3
"""Evaluate DRAG graph biology controls.

The controls are deliberately simple and auditable:

* parent-collapsed: report whether the analyzed view graph already collapses
  sequence windows to parent sequence nodes.
* k-mer/Jaccard NN: rebuild an independent neighbor graph from sequence strings,
  using no learned vectors and no BLAST alignment.
* degree-preserving null: rewire the observed graph while preserving degree
  sequence, then compare biological community purity.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from scripts.analyze_view_graph import extract_biological_labels, gene_family


LABEL_TYPES = ("gene_id", "gene_symbol", "gene_family", "biotype")


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    config = load_config(args.config)
    graph_specs = parse_graphs(args.graphs)
    rng = random.Random(args.seed)
    results: dict[str, Any] = {}
    for name, path in graph_specs.items():
        if args.progress:
            print(f"[drag-controls] {name}: {path}", flush=True)
        graph_data = read_graph(path)
        enrich_labels_from_fasta(graph_data["nodes"], config=config)
        observed = build_graph(graph_data["nodes"], graph_data["edges"])
        kmer = build_kmer_graph(graph_data["nodes"], k=args.kmer, neighbors=args.neighbors)
        null_rows = [
            analyze_graph(
                degree_preserving_null(observed, rng=rng, swaps_per_edge=args.null_swaps_per_edge),
                node_payload=graph_data["nodes"],
                min_community_size=args.min_community_size,
            )
            for _ in range(args.null_replicates)
        ]
        results[name] = {
            "path": str(path),
            "meta": graph_data["meta"],
            "parent_collapse": parent_collapse_summary(graph_data),
            "observed": analyze_graph(
                observed,
                node_payload=graph_data["nodes"],
                min_community_size=args.min_community_size,
            ),
            "kmer_jaccard": analyze_graph(
                kmer,
                node_payload=graph_data["nodes"],
                min_community_size=args.min_community_size,
            ),
            "degree_preserving_null": summarize_null(null_rows),
        }
    result = {
        "dataset": "dnarag_drag_graph_controls",
        "scope": {
            "claim_boundary": (
                "These controls test whether DRAG communities retain biological-label structure beyond "
                "parent-window duplication and simple k-mer/Jaccard neighborhoods. They are exploratory "
                "controls, not proof of biological mechanism."
            ),
            "node_labels": "labels are parsed from existing FASTA headers stored in graph node metadata",
        },
        "parameters": {
            "graphs": {name: str(path) for name, path in graph_specs.items()},
            "kmer": args.kmer,
            "neighbors": args.neighbors,
            "min_community_size": args.min_community_size,
            "null_replicates": args.null_replicates,
            "null_swaps_per_edge": args.null_swaps_per_edge,
            "seed": args.seed,
            "config": args.config,
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


def read_graph(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        meta = {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM graph_meta")
        } if table_exists(conn, "graph_meta") else {}
        node_rows = conn.execute(
            """
            SELECT entity_id, entity_type, canonical_id, name, source, description, metadata_json
            FROM nodes
            ORDER BY entity_id
            """
        ).fetchall()
        edge_rows = conn.execute(
            """
            SELECT source_entity_id, relation_type, target_entity_id, confidence, metadata_json
            FROM edges
            ORDER BY source_entity_id, target_entity_id
            """
        ).fetchall()
    nodes: dict[str, dict[str, Any]] = {}
    for row in node_rows:
        metadata = load_json(row["metadata_json"])
        labels = extract_biological_labels(metadata)
        if not labels:
            labels = labels_from_headerish_text(str(row["name"] or "") + " " + str(row["description"] or ""))
        nodes[str(row["entity_id"])] = {
            "entity_id": str(row["entity_id"]),
            "entity_type": str(row["entity_type"]),
            "canonical_id": row["canonical_id"],
            "name": row["name"],
            "source": row["source"],
            "sequence": clean_sequence(row["description"]),
            "metadata": metadata,
            "labels": labels,
        }
    edges = [
        {
            "source": str(row["source_entity_id"]),
            "target": str(row["target_entity_id"]),
            "relation_type": str(row["relation_type"]),
            "confidence": float(row["confidence"] or 0.0),
            "metadata": load_json(row["metadata_json"]),
        }
        for row in edge_rows
        if str(row["source_entity_id"]) in nodes and str(row["target_entity_id"]) in nodes
    ]
    return {"path": str(path), "meta": meta, "nodes": nodes, "edges": edges}


def enrich_labels_from_fasta(nodes: dict[str, dict[str, Any]], *, config: Any) -> None:
    needed_dna = {
        accession_from_entity_id(node_id)
        for node_id, node in nodes.items()
        if node.get("entity_type") == "dna_sequence"
    }
    needed_protein = {
        accession_from_entity_id(node_id)
        for node_id, node in nodes.items()
        if node.get("entity_type") == "protein_sequence"
    }
    labels_by_accession = {}
    labels_by_accession.update(
        load_fasta_labels(
            first_existing(
                config.blastn_fasta,
                config.raw_dir / "ensembl" / "Homo_sapiens.GRCh38.cdna.all.fa.gz",
                config.raw_dir / "ensembl" / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz",
            ),
            needed_dna,
        )
    )
    labels_by_accession.update(
        load_fasta_labels(
            first_existing(
                config.blast_fasta,
                config.raw_dir / "uniprot" / "uniprot_sprot.fasta.gz",
            ),
            needed_protein,
        )
    )
    for node_id, node in nodes.items():
        labels = labels_by_accession.get(accession_from_entity_id(node_id))
        if labels:
            node["labels"] = labels


def load_fasta_labels(path: Path | None, needed: set[str]) -> dict[str, dict[str, list[str]]]:
    if path is None or not needed:
        return {}
    labels: dict[str, dict[str, list[str]]] = {}
    for header in iter_fasta_headers(path):
        accession = accession_from_header(header)
        if accession not in needed:
            continue
        parsed = extract_biological_labels({"header": header})
        if parsed:
            labels[accession] = parsed
        if len(labels) >= len(needed):
            break
    return labels


def iter_fasta_headers(path: Path) -> Any:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith(">"):
                yield line[1:].strip()


def first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def accession_from_entity_id(entity_id: str) -> str:
    text = str(entity_id or "")
    return text.split(":", 1)[1] if ":" in text else text


def accession_from_header(header: str) -> str:
    accession = str(header or "").split()[0]
    if "|" in accession:
        parts = accession.split("|")
        accession = parts[1] if len(parts) > 1 else accession
    return accession


def build_graph(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> nx.Graph:
    graph = nx.Graph()
    for node_id, node in nodes.items():
        graph.add_node(node_id, **node)
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source == target:
            continue
        weight = float(edge.get("confidence") or 0.0)
        existing = graph.get_edge_data(source, target)
        if existing is None or weight > float(existing.get("weight") or 0.0):
            graph.add_edge(source, target, weight=weight, relation_type=edge.get("relation_type"))
    return graph


def build_kmer_graph(nodes: dict[str, dict[str, Any]], *, k: int, neighbors: int) -> nx.Graph:
    graph = nx.Graph()
    for node_id, node in nodes.items():
        graph.add_node(node_id, **node)
    signatures = {node_id: kmers(node["sequence"], k=k) for node_id, node in nodes.items()}
    ids = list(nodes)
    for index, source in enumerate(ids):
        source_sig = signatures[source]
        scored: list[tuple[float, str]] = []
        if not source_sig:
            continue
        for target in ids:
            if target == source:
                continue
            score = jaccard(source_sig, signatures[target])
            if score > 0:
                scored.append((score, target))
        for rank, (score, target) in enumerate(sorted(scored, reverse=True)[:neighbors], start=1):
            existing = graph.get_edge_data(source, target)
            if existing is None or score > float(existing.get("weight") or 0.0):
                graph.add_edge(source, target, weight=score, relation_type="kmer_jaccard_neighbor", rank=rank)
    return graph


def degree_preserving_null(graph: nx.Graph, *, rng: random.Random, swaps_per_edge: int) -> nx.Graph:
    null = graph.copy()
    if null.number_of_edges() < 4:
        return null
    swaps = max(int(swaps_per_edge) * null.number_of_edges(), null.number_of_edges())
    try:
        nx.double_edge_swap(null, nswap=swaps, max_tries=swaps * 20, seed=rng)
    except nx.NetworkXError:
        try:
            nx.connected_double_edge_swap(null, nswap=min(swaps, null.number_of_edges() * 2), seed=rng)
        except Exception:
            return null
    for source, target in null.edges():
        null[source][target]["weight"] = 1.0
        null[source][target]["relation_type"] = "degree_preserving_null"
    return null


def analyze_graph(
    graph: nx.Graph,
    *,
    node_payload: dict[str, dict[str, Any]],
    min_community_size: int,
) -> dict[str, Any]:
    for node_id, payload in node_payload.items():
        if node_id in graph:
            graph.nodes[node_id].update(payload)
    communities = detect_communities(graph)
    rows = [
        analyze_community(graph, community_id, members)
        for community_id, members in enumerate(communities)
        if len(members) >= min_community_size
    ]
    components = sorted((len(item) for item in nx.connected_components(graph)), reverse=True)
    summary = {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "connected_components": len(components),
        "largest_component": components[0] if components else 0,
        "communities": len(communities),
        "modularity": graph_modularity(graph, communities),
        "labeled_nodes": labeled_node_counts(graph),
        "purity": purity_summary(rows),
        "top_signal": top_signal(rows),
    }
    return {"summary": summary, "top_communities": sorted(rows, key=community_sort_key)[:12]}


def detect_communities(graph: nx.Graph) -> list[set[str]]:
    if graph.number_of_nodes() == 0:
        return []
    if graph.number_of_edges() == 0:
        return [{str(node)} for node in graph.nodes()]
    communities = nx.algorithms.community.greedy_modularity_communities(graph, weight="weight")
    return [set(str(node) for node in community) for community in sorted(communities, key=len, reverse=True)]


def analyze_community(graph: nx.Graph, community_id: int, members: set[str]) -> dict[str, Any]:
    subgraph = graph.subgraph(members)
    labels = {}
    for label_type in LABEL_TYPES:
        row = dominant_label(graph, members, label_type)
        if row:
            labels[label_type] = row
    return {
        "community": community_id,
        "size": len(members),
        "edge_count": subgraph.number_of_edges(),
        "density": round(nx.density(subgraph), 6) if len(members) > 1 else 0.0,
        "dominant_labels": labels,
    }


def dominant_label(graph: nx.Graph, members: set[str], label_type: str) -> dict[str, Any] | None:
    counter: Counter[str] = Counter()
    labeled_nodes = 0
    for node_id in members:
        values = label_values(graph.nodes[node_id].get("labels") or {}, label_type)
        if values:
            labeled_nodes += 1
        for value in set(values):
            counter[str(value)] += 1
    if not counter:
        return None
    label, count = counter.most_common(1)[0]
    return {
        "label": label,
        "count": count,
        "labeled_nodes": labeled_nodes,
        "community_rate": round(count / max(len(members), 1), 4),
        "labeled_purity": round(count / max(labeled_nodes, 1), 4),
    }


def parent_collapse_summary(graph_data: dict[str, Any]) -> dict[str, Any]:
    nodes = graph_data["nodes"]
    parent_prefixes = ("dna_sequence:", "protein_sequence:")
    node_ids = list(nodes)
    collapsed_like = sum(1 for node_id in node_ids if str(node_id).startswith(parent_prefixes))
    window_like = sum(1 for node_id in node_ids if "_window:" in str(node_id))
    chroma_ids = [
        str(node.get("metadata", {}).get("chroma_id") or "")
        for node in nodes.values()
        if node.get("metadata", {}).get("chroma_id")
    ]
    row_indices = {
        node.get("metadata", {}).get("row_idx")
        for node in nodes.values()
        if node.get("metadata", {}).get("row_idx") is not None
    }
    return {
        "node_count": len(node_ids),
        "parent_style_node_count": collapsed_like,
        "window_style_node_count": window_like,
        "distinct_chroma_ids": len(set(chroma_ids)),
        "distinct_row_indices": len(row_indices),
        "already_parent_collapsed": bool(collapsed_like == len(node_ids) and window_like == 0),
        "note": (
            "The current view-graph builder uses parent sequence record_id as graph node ID; "
            "multiple windows from the same parent collapse into one parent node."
        ),
    }


def summarize_null(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"replicates": 0}
    return {
        "replicates": len(rows),
        "summary_mean": mean_summary(rows),
        "top_signal_examples": [row["summary"].get("top_signal") or {} for row in rows[:5]],
    }


def mean_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ("nodes", "edges", "connected_components", "largest_component", "communities", "modularity")
    result: dict[str, Any] = {}
    for key in keys:
        values = [float(row["summary"].get(key) or 0.0) for row in rows]
        result[key] = round(sum(values) / len(values), 4)
    result["purity"] = {}
    for label_type in LABEL_TYPES:
        values = [
            float((row["summary"].get("purity", {}).get(label_type) or {}).get("max_labeled_purity") or 0.0)
            for row in rows
        ]
        result["purity"][label_type] = {"max_labeled_purity": round(sum(values) / len(values), 4)}
    return result


def comparison_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, payload in results.items():
        for condition in ("observed", "kmer_jaccard"):
            summary = payload[condition]["summary"]
            rows.append(comparison_row(name, condition, summary))
        rows.append(comparison_row(name, "degree_preserving_null_mean", payload["degree_preserving_null"]["summary_mean"]))
    return rows


def comparison_row(name: str, condition: str, summary: dict[str, Any]) -> dict[str, Any]:
    signal = summary.get("top_signal") or {}
    return {
        "graph": name,
        "condition": condition,
        "nodes": summary.get("nodes"),
        "edges": summary.get("edges"),
        "communities": summary.get("communities"),
        "modularity": summary.get("modularity"),
        "top_label_type": signal.get("label_type"),
        "top_label": signal.get("label"),
        "top_label_count": signal.get("count"),
        "top_label_purity": signal.get("labeled_purity"),
    }


def purity_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for label_type in LABEL_TYPES:
        label_rows = [
            row["dominant_labels"][label_type]
            for row in rows
            if label_type in row.get("dominant_labels", {})
        ]
        if not label_rows:
            continue
        summary[label_type] = {
            "communities_with_label": len(label_rows),
            "max_count": max(int(row["count"]) for row in label_rows),
            "max_labeled_purity": round(max(float(row["labeled_purity"]) for row in label_rows), 4),
        }
    return summary


def top_signal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    for row in rows:
        for label_type, label_row in row.get("dominant_labels", {}).items():
            if int(label_row.get("count") or 0) < 2:
                continue
            candidates.append({"community": row["community"], "size": row["size"], "label_type": label_type, **label_row})
    if not candidates:
        return {}
    return sorted(candidates, key=lambda item: (-float(item.get("labeled_purity") or 0.0), -int(item.get("count") or 0)))[0]


def community_sort_key(row: dict[str, Any]) -> tuple[float, int]:
    signal = top_signal([row])
    return (-float(signal.get("labeled_purity") or 0.0), -int(row.get("size") or 0))


def graph_modularity(graph: nx.Graph, communities: list[set[str]]) -> float:
    if graph.number_of_edges() == 0 or len(communities) <= 1:
        return 0.0
    return round(float(nx.algorithms.community.quality.modularity(graph, communities, weight="weight")), 4)


def labeled_node_counts(graph: nx.Graph) -> dict[str, int]:
    counts = {label_type: 0 for label_type in LABEL_TYPES}
    for _, data in graph.nodes(data=True):
        labels = data.get("labels") or {}
        for label_type in LABEL_TYPES:
            if label_values(labels, label_type):
                counts[label_type] += 1
    return counts


def label_values(labels: dict[str, list[str]], label_type: str) -> list[str]:
    if label_type == "gene_id":
        return sorted(set(labels.get("gene_ids", [])))
    if label_type == "gene_symbol":
        return sorted(set([*labels.get("gene_symbols", []), *labels.get("protein_gene_names", [])]))
    if label_type == "gene_family":
        return sorted(set(labels.get("gene_families", [])))
    if label_type == "biotype":
        return sorted(set([*labels.get("gene_biotypes", []), *labels.get("transcript_biotypes", [])]))
    return []


def labels_from_headerish_text(text: str) -> dict[str, list[str]]:
    labels = extract_biological_labels({"header": text})
    if not labels:
        family = gene_family(text)
        if family:
            labels["gene_families"] = [family]
    return labels


def kmers(sequence: str, *, k: int) -> set[str]:
    clean = clean_sequence(sequence)
    if len(clean) < k:
        return {clean} if clean else set()
    return {clean[index : index + k] for index in range(0, len(clean) - k + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    inter = len(left & right)
    if inter == 0:
        return 0.0
    return inter / len(left | right)


def clean_sequence(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalpha() or ch == "*")


def load_json(value: Any) -> dict[str, Any]:
    if value in {None, ""}:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# DRAG Graph Controls",
        "",
        "This report adds explicit controls for the exploratory biological interpretation of DRAG sequence graphs.",
        "",
        "| Graph | Condition | Nodes | Edges | Communities | Modularity | Top Signal |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in result["comparison"]:
        signal = (
            f"{row.get('top_label_type')}:{row.get('top_label')} "
            f"({row.get('top_label_count')}, purity {row.get('top_label_purity')})"
            if row.get("top_label")
            else "-"
        )
        lines.append(
            f"| {row['graph']} | {row['condition']} | {row.get('nodes')} | {row.get('edges')} | "
            f"{row.get('communities')} | {float(row.get('modularity') or 0):.4f} | {signal} |"
        )
    lines.extend(["", "## Parent Collapse", ""])
    for name, payload in result["graphs"].items():
        collapse = payload["parent_collapse"]
        lines.extend(
            [
                f"### {name}",
                "",
                f"- Already parent-collapsed: `{str(collapse['already_parent_collapsed']).lower()}`",
                f"- Parent-style nodes: `{collapse['parent_style_node_count']}/{collapse['node_count']}`",
                f"- Distinct source Chroma rows represented: `{collapse['distinct_row_indices']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "- Passing these controls would support a stronger exploratory biology claim.",
            "- Failing them means DRAG should remain an evidence-packaging and visualization module in the main paper.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_graphs(value: str) -> dict[str, Path]:
    result = {}
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


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate DRAG graph biology controls")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument(
        "--graphs",
        default=(
            "dna=indexes/standard/graph/views/dna_sequence_window_10k.sqlite,"
            "protein=indexes/standard/graph/views/protein_sequence_window_10k.sqlite"
        ),
        help="Comma-separated name=graph.sqlite entries",
    )
    parser.add_argument("--output", default="reports/drag_graph_controls_10k.json")
    parser.add_argument("--markdown", default="reports/drag_graph_controls_10k.md")
    parser.add_argument("--kmer", type=int, default=5)
    parser.add_argument("--neighbors", type=int, default=5)
    parser.add_argument("--min-community-size", type=int, default=3)
    parser.add_argument("--null-replicates", type=int, default=5)
    parser.add_argument("--null-swaps-per-edge", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260517)
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

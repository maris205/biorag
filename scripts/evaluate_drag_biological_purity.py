#!/usr/bin/env python3
"""Summarize biological label purity in DRAG sequence view graphs."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.retrieval.vector_db import ChromaVectorDB


DEFAULT_GRAPHS = {
    "dna_vector": "indexes/standard/graph/views/dna_sequence_window_10k.sqlite",
    "dna_blast": "indexes/standard/graph/views/dna_sequence_window_blast_10k.sqlite",
    "dna_hybrid": "indexes/standard/graph/views/dna_sequence_window_hybrid_10k.sqlite",
    "protein_vector": "indexes/standard/graph/views/protein_sequence_window_10k.sqlite",
    "protein_blast": "indexes/standard/graph/views/protein_sequence_window_blast_10k.sqlite",
    "protein_hybrid": "indexes/standard/graph/views/protein_sequence_window_hybrid_10k.sqlite",
}

LABEL_TYPES = ("gene_id", "gene_symbol", "gene_family", "biotype")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    started = time.perf_counter()
    graph_specs = parse_graphs(args.graphs)
    results: dict[str, Any] = {}
    for name, graph_path in graph_specs.items():
        if args.progress:
            print(f"[drag-purity] {name} {graph_path}", flush=True)
        results[name] = analyze_graph(
            graph_path,
            config_vector_dir=config.vector_dir,
            min_community_size=args.min_community_size,
        )
    result = {
        "dataset": "dnarag_drag_biological_purity",
        "config": args.config,
        "min_community_size": args.min_community_size,
        "graphs": results,
        "comparison": compare_graphs(results),
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


def analyze_graph(graph_path: Path, *, config_vector_dir: Path, min_community_size: int) -> dict[str, Any]:
    graph_data = read_view_graph(graph_path)
    enrich_labels_from_chroma(graph_data, vector_dir=config_vector_dir)
    graph = build_networkx_graph(graph_data)
    communities = detect_communities(graph)
    annotate_communities(graph, communities)
    global_counts = global_label_counts(graph)
    community_rows = [
        analyze_community(graph, community_id, members, global_counts)
        for community_id, members in enumerate(communities)
        if len(members) >= min_community_size
    ]
    components = sorted((len(item) for item in nx.connected_components(graph)), reverse=True)
    summary = {
        "graph": str(graph_path),
        "target": graph_data.get("meta", {}).get("target"),
        "recipe": graph_data.get("meta", {}).get("recipe"),
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "directed_edge_rows": len(graph_data["edges"]),
        "connected_components": len(components),
        "largest_component": components[0] if components else 0,
        "community_count": len(communities),
        "modularity": graph_modularity(graph, communities),
        "relation_edge_rows": relation_edge_rows(graph_data["edges"]),
        "labeled_nodes": labeled_node_counts(graph),
        "top_signal": top_signal(community_rows),
        "purity_summary": purity_summary(community_rows),
    }
    return {
        "summary": summary,
        "top_communities": sorted(community_rows, key=community_sort_key)[:20],
    }


def read_view_graph(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        meta = {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM graph_meta")
        } if table_exists(conn, "graph_meta") else {}
        nodes = {
            str(row["entity_id"]): {
                "entity_id": str(row["entity_id"]),
                "entity_type": str(row["entity_type"]),
                "canonical_id": row["canonical_id"],
                "name": row["name"],
                "source": row["source"],
                "description": row["description"],
                "metadata": load_json(row["metadata_json"]),
                "labels": {},
            }
            for row in conn.execute(
                """
                SELECT entity_id, entity_type, canonical_id, name, source, description, metadata_json
                FROM nodes
                ORDER BY entity_id
                """
            )
        }
        edges = []
        for row in conn.execute(
            """
            SELECT source_entity_id, relation_type, target_entity_id, source, confidence, metadata_json
            FROM edges
            ORDER BY source_entity_id, target_entity_id
            """
        ):
            source = str(row["source_entity_id"])
            target = str(row["target_entity_id"])
            if source not in nodes or target not in nodes:
                continue
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation_type": str(row["relation_type"]),
                    "edge_source": row["source"],
                    "confidence": float(row["confidence"] or 0.0),
                    "metadata": load_json(row["metadata_json"]),
                }
            )
    return {"path": str(path), "meta": meta, "nodes": nodes, "edges": edges}


def enrich_labels_from_chroma(graph_data: dict[str, Any], *, vector_dir: Path) -> None:
    target = graph_data.get("meta", {}).get("target")
    if not target:
        return
    ids = [
        str(node.get("metadata", {}).get("chroma_id") or "")
        for node in graph_data["nodes"].values()
        if node.get("metadata", {}).get("chroma_id")
    ]
    if not ids:
        return
    db = ChromaVectorDB(vector_dir)
    collection = db._collection(str(target))
    records: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 500):
        result = collection.get(ids=ids[start : start + 500], include=["metadatas", "documents"])
        for record in records_from_chroma_get(result):
            records[str(record["id"])] = record
    for node in graph_data["nodes"].values():
        chroma_id = str(node.get("metadata", {}).get("chroma_id") or "")
        record = records.get(chroma_id)
        if record:
            node["labels"] = extract_biological_labels(record["metadata"])


def build_networkx_graph(graph_data: dict[str, Any]) -> nx.Graph:
    graph = nx.Graph()
    for entity_id, node in graph_data["nodes"].items():
        graph.add_node(entity_id, **node)
    for edge in graph_data["edges"]:
        source = edge["source"]
        target = edge["target"]
        weight = float(edge.get("confidence") or 0.0)
        existing = graph.get_edge_data(source, target)
        if existing is None or weight > float(existing.get("weight") or 0.0):
            graph.add_edge(source, target, weight=weight, **edge)
    return graph


def detect_communities(graph: nx.Graph) -> list[set[str]]:
    if graph.number_of_nodes() == 0:
        return []
    if graph.number_of_edges() == 0:
        return [{str(node)} for node in graph.nodes()]
    communities = list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
    return [set(str(node) for node in community) for community in sorted(communities, key=len, reverse=True)]


def annotate_communities(graph: nx.Graph, communities: list[set[str]]) -> None:
    for community_id, members in enumerate(communities):
        for node_id in members:
            graph.nodes[node_id]["community"] = community_id


def analyze_community(
    graph: nx.Graph,
    community_id: int,
    members: set[str],
    global_counts: dict[str, Counter[str]],
) -> dict[str, Any]:
    subgraph = graph.subgraph(members)
    label_rows = {
        label_type: dominant_label(graph, members, label_type, global_counts[label_type])
        for label_type in LABEL_TYPES
    }
    label_rows = {key: value for key, value in label_rows.items() if value}
    return {
        "community": community_id,
        "size": len(members),
        "edge_count": subgraph.number_of_edges(),
        "density": round(nx.density(subgraph), 6) if len(members) > 1 else 0.0,
        "avg_degree": round(sum(dict(subgraph.degree()).values()) / max(len(members), 1), 4),
        "dominant_labels": label_rows,
        "representative_nodes": representative_nodes(graph, members),
    }


def dominant_label(
    graph: nx.Graph,
    members: set[str],
    label_type: str,
    global_counter: Counter[str],
) -> dict[str, Any] | None:
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
    global_count = global_counter[label]
    population = graph.number_of_nodes()
    community_rate = count / max(len(members), 1)
    labeled_rate = count / max(labeled_nodes, 1)
    global_rate = global_count / max(population, 1)
    return {
        "label": label,
        "count": count,
        "labeled_nodes": labeled_nodes,
        "community_rate": round(community_rate, 4),
        "labeled_purity": round(labeled_rate, 4),
        "global_count": global_count,
        "global_rate": round(global_rate, 4),
        "enrichment": enrichment(community_rate, global_rate),
        "hypergeom_p": hypergeom_tail(
            population=population,
            successes=global_count,
            draws=len(members),
            observed=count,
        ),
    }


def global_label_counts(graph: nx.Graph) -> dict[str, Counter[str]]:
    counters = {label_type: Counter() for label_type in LABEL_TYPES}
    for _, data in graph.nodes(data=True):
        labels = data.get("labels") or {}
        for label_type in LABEL_TYPES:
            for value in set(label_values(labels, label_type)):
                counters[label_type][str(value)] += 1
    return counters


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


def top_signal(community_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for row in community_rows:
        for label_type, label_row in (row.get("dominant_labels") or {}).items():
            if label_row.get("count", 0) < 2:
                continue
            candidates.append(
                {
                    "community": row["community"],
                    "size": row["size"],
                    "label_type": label_type,
                    **label_row,
                }
            )
    if not candidates:
        return {}
    return sorted(candidates, key=signal_sort_key)[0]


def purity_summary(community_rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label_type in LABEL_TYPES:
        rows = [
            row["dominant_labels"][label_type]
            for row in community_rows
            if label_type in row.get("dominant_labels", {})
        ]
        if not rows:
            continue
        result[label_type] = {
            "communities_with_label": len(rows),
            "max_count": max(int(row.get("count") or 0) for row in rows),
            "max_labeled_purity": round(max(float(row.get("labeled_purity") or 0.0) for row in rows), 4),
            "max_enrichment": max_enrichment(rows),
            "min_hypergeom_p": min(float(row.get("hypergeom_p") or 1.0) for row in rows),
        }
    return result


def compare_graphs(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, payload in results.items():
        summary = payload["summary"]
        signal = summary.get("top_signal") or {}
        rows.append(
            {
                "graph": name,
                "target": summary.get("target"),
                "recipe": summary.get("recipe"),
                "nodes": summary.get("node_count"),
                "edges": summary.get("edge_count"),
                "components": summary.get("connected_components"),
                "communities": summary.get("community_count"),
                "modularity": summary.get("modularity"),
                "top_label_type": signal.get("label_type"),
                "top_label": signal.get("label"),
                "top_label_count": signal.get("count"),
                "top_label_enrichment": signal.get("enrichment"),
                "top_label_p": signal.get("hypergeom_p"),
            }
        )
    return rows


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# DRAG Biological Purity Analysis",
        "",
        "This report summarizes community-level biological label purity for sequence-derived DRAG view graphs. It treats vector edges as representation evidence and BLAST edges as alignment evidence.",
        "",
        "## Graph Comparison",
        "",
        "| Graph | Nodes | Edges | Components | Communities | Modularity | Top biological signal |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["comparison"]:
        signal = format_signal(row)
        lines.append(
            f"| {row['graph']} | {row['nodes']} | {row['edges']} | {row['components']} | "
            f"{row['communities']} | {float(row['modularity'] or 0):.4f} | {signal} |"
        )
    lines.extend(["", "## Top Communities", ""])
    for name, payload in result["graphs"].items():
        summary = payload["summary"]
        lines.extend(
            [
                f"### {name}",
                "",
                f"- Target: `{summary.get('target')}`",
                f"- Recipe: `{summary.get('recipe')}`",
                f"- Relation rows: `{summary.get('relation_edge_rows')}`",
                "",
                "| Community | Size | Density | Dominant labels |",
                "|---:|---:|---:|---|",
            ]
        )
        for community in payload["top_communities"][:8]:
            labels = "; ".join(
                format_label(label_type, label_row)
                for label_type, label_row in community.get("dominant_labels", {}).items()
            ) or "-"
            lines.append(
                f"| {community['community']} | {community['size']} | {community['density']:.4f} | {labels} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "- A high-purity vector community is evidence of non-random biological structure in the representation graph, not proof of homology or mechanism.",
            "- A BLAST community supplies alignment-grounded local evidence, but can fragment the global graph.",
            "- Hybrid DRAG is useful because it keeps broad vector reachability while preserving typed BLAST evidence for agents.",
            "",
        ]
    )
    return "\n".join(lines)


def format_signal(row: dict[str, Any]) -> str:
    if not row.get("top_label"):
        return "-"
    return (
        f"{row.get('top_label_type')}:{row.get('top_label')} "
        f"({row.get('top_label_count')}, x{row.get('top_label_enrichment')}, p={row.get('top_label_p')})"
    )


def format_label(label_type: str, row: dict[str, Any]) -> str:
    return (
        f"{label_type}:{row['label']} "
        f"({row['count']}/{row['labeled_nodes']}, purity {row['labeled_purity']:.4f}, "
        f"x{row['enrichment']}, p={row['hypergeom_p']})"
    )


def community_sort_key(row: dict[str, Any]) -> tuple[float, int, int]:
    labels = list((row.get("dominant_labels") or {}).values())
    best_p = min((float(item.get("hypergeom_p") or 1.0) for item in labels), default=1.0)
    best_count = max((int(item.get("count") or 0) for item in labels), default=0)
    return (best_p, -best_count, -int(row.get("size") or 0))


def signal_sort_key(row: dict[str, Any]) -> tuple[float, float, int]:
    p_value = float(row.get("hypergeom_p") or 1.0)
    enrich_value = row.get("enrichment")
    enrichment_score = 1e12 if enrich_value == "inf" else float(enrich_value or 0.0)
    return (p_value, -enrichment_score, -int(row.get("count") or 0))


def max_enrichment(rows: list[dict[str, Any]]) -> float | str:
    values = [row.get("enrichment") for row in rows]
    if "inf" in values:
        return "inf"
    return max(float(value or 0.0) for value in values)


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


def relation_edge_rows(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter(str(edge.get("relation_type") or "") for edge in edges)
    return dict(sorted(counts.items()))


def representative_nodes(graph: nx.Graph, members: set[str], limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node_id in sorted(members, key=lambda item: graph.degree(item), reverse=True)[:limit]:
        node = graph.nodes[node_id]
        rows.append(
            {
                "entity_id": node_id,
                "name": node.get("name"),
                "degree": graph.degree(node_id),
                "labels": node.get("labels") or {},
            }
        )
    return rows


def records_from_chroma_get(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []
    rows: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        raw = dict(metadata or {})
        try:
            nested = json.loads(str(raw.get("metadata_json") or "{}"))
        except json.JSONDecodeError:
            nested = {}
        raw.update(nested if isinstance(nested, dict) else {})
        rows.append(
            {
                "id": ids[index] if index < len(ids) else "",
                "metadata": raw,
                "document": documents[index] if index < len(documents) else None,
            }
        )
    return rows


def extract_biological_labels(metadata: dict[str, Any]) -> dict[str, list[str]]:
    import re

    header = str(metadata.get("header") or "")
    result: dict[str, list[str]] = {}
    for key, pattern in [
        ("gene_ids", r"\bgene:([A-Za-z0-9_.-]+)"),
        ("gene_symbols", r"\bgene_symbol:([^\s\]]+)"),
        ("gene_biotypes", r"\bgene_biotype:([^\s\]]+)"),
        ("transcript_biotypes", r"\btranscript_biotype:([^\s\]]+)"),
        ("protein_gene_names", r"\bGN=([^\s]+)"),
    ]:
        values = sorted({match.group(1).strip(";,") for match in re.finditer(pattern, header)})
        if values:
            result[key] = values
    family_sources = result.get("gene_symbols", []) + result.get("protein_gene_names", [])
    families = sorted({gene_family(value) for value in family_sources if gene_family(value)})
    if families:
        result["gene_families"] = families
    return result


def gene_family(symbol: str) -> str | None:
    import re

    text = str(symbol or "").upper()
    if text.startswith(("IGHV", "IGKV", "IGLV", "TRAV", "TRBV", "TRGV", "TRDV")):
        match = re.match(r"^([A-Z]+)", text)
        if match:
            return match.group(1)
    return None


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


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
    )


def load_json(value: Any) -> dict[str, Any]:
    if value in {None, ""}:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
    parser = argparse.ArgumentParser(description="Evaluate biological label purity in DRAG view graphs")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--graphs", default="default", help="default or comma-separated name=path entries")
    parser.add_argument("--output", default="reports/drag_gene_family_purity_10k.json")
    parser.add_argument("--markdown", default="reports/drag_gene_family_purity_10k.md")
    parser.add_argument("--min-community-size", type=int, default=3)
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

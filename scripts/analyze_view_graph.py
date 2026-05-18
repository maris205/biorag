#!/usr/bin/env python3
"""Analyze and visualize text-style DRAG view graphs."""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.retrieval.vector_db import ChromaVectorDB


PALETTE = [
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#be123c",
    "#4f46e5",
    "#65a30d",
    "#c026d3",
    "#0f766e",
    "#b45309",
]


def main() -> None:
    args = parse_args()
    graph_path = Path(args.graph)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or graph_path.stem
    graph_data = read_graph(graph_path)
    if not args.no_chroma_labels:
        enrich_labels_from_chroma(graph_data, config_path=args.config)
    analysis = analyze_graph(graph_data, min_community_size=args.min_community_size)
    json_path = output_dir / f"{prefix}_analysis.json"
    md_path = output_dir / f"{prefix}_analysis.md"
    html_path = output_dir / f"{prefix}_graph.html"
    svg_path = output_dir / f"{prefix}_graph.svg"
    json_path.write_text(json.dumps(jsonable_analysis(analysis), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(graph_path, analysis), encoding="utf-8")
    if not args.analysis_only:
        layout = nx.spring_layout(analysis["graph"], seed=args.seed, weight="weight", iterations=args.layout_iterations)
        svg_body = render_svg(graph_path, analysis, layout)
        html_path.write_text(render_html(graph_path, analysis, svg_body), encoding="utf-8")
        svg_path.write_text(svg_body, encoding="utf-8")
    print(
        json.dumps(
            {
                "graph": str(graph_path),
                "json": str(json_path),
                "markdown": str(md_path),
                "html": None if args.analysis_only else str(html_path),
                "svg": None if args.analysis_only else str(svg_path),
                "node_count": analysis["summary"]["node_count"],
                "edge_count": analysis["summary"]["edge_count"],
                "community_count": analysis["summary"]["community_count"],
                "modularity": analysis["summary"]["modularity"],
            },
            indent=2,
        )
    )


def read_graph(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with sqlite3.connect(path) as conn:
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
            SELECT source_entity_id, relation_type, target_entity_id, source, confidence, metadata_json
            FROM edges
            ORDER BY source_entity_id, target_entity_id
            """
        ).fetchall()
    nodes: dict[str, dict[str, Any]] = {}
    for row in node_rows:
        metadata = load_json(row["metadata_json"])
        nodes[str(row["entity_id"])] = {
            "entity_id": str(row["entity_id"]),
            "entity_type": str(row["entity_type"]),
            "canonical_id": row["canonical_id"],
            "name": row["name"],
            "source": row["source"],
            "description": row["description"],
            "metadata": metadata,
            "labels": {},
        }
    edges: list[dict[str, Any]] = []
    for row in edge_rows:
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


def enrich_labels_from_chroma(graph_data: dict[str, Any], *, config_path: str) -> None:
    target = graph_data.get("meta", {}).get("target")
    if not target:
        return
    config = load_config(config_path)
    db = ChromaVectorDB(config.vector_dir)
    ids = [
        str(node.get("metadata", {}).get("chroma_id") or "")
        for node in graph_data["nodes"].values()
        if node.get("metadata", {}).get("chroma_id")
    ]
    if not ids:
        return
    collection = db._collection(target)
    record_by_id: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 500):
        result = collection.get(ids=ids[start : start + 500], include=["metadatas", "documents"])
        for record in records_from_chroma_get(result):
            record_by_id[str(record["id"])] = record
    for node in graph_data["nodes"].values():
        chroma_id = str(node.get("metadata", {}).get("chroma_id") or "")
        record = record_by_id.get(chroma_id)
        if not record:
            continue
        node["labels"] = extract_biological_labels(record["metadata"])
        node["header"] = record["metadata"].get("header")


def analyze_graph(graph_data: dict[str, Any], *, min_community_size: int) -> dict[str, Any]:
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
    communities = detect_communities(graph)
    community_id_by_node: dict[str, int] = {}
    for community_id, members in enumerate(communities):
        for node_id in members:
            community_id_by_node[str(node_id)] = community_id
            graph.nodes[str(node_id)]["community"] = community_id
    community_rows = analyze_communities(graph, communities, min_community_size=min_community_size)
    components = sorted((len(item) for item in nx.connected_components(graph)), reverse=True)
    modularity = (
        nx.algorithms.community.quality.modularity(graph, communities, weight="weight")
        if graph.number_of_edges() and len(communities) > 1
        else 0.0
    )
    summary = {
        "target": graph_data.get("meta", {}).get("target"),
        "recipe": graph_data.get("meta", {}).get("recipe"),
        "biological_rules_used": any(
            bool(edge.get("metadata", {}).get("biological_rules_used")) for edge in graph_data["edges"]
        ),
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "directed_edge_rows": len(graph_data["edges"]),
        "connected_components": len(components),
        "largest_component": components[0] if components else 0,
        "density": round(nx.density(graph), 6) if graph.number_of_nodes() > 1 else 0.0,
        "avg_degree": round(sum(dict(graph.degree()).values()) / max(graph.number_of_nodes(), 1), 4),
        "community_count": len(communities),
        "modularity": round(float(modularity), 4),
        "labeled_nodes": count_labeled_nodes(graph),
        "relation_edge_rows": relation_edge_rows(graph_data["edges"]),
    }
    return {
        "graph": graph,
        "summary": summary,
        "communities": community_rows,
        "community_id_by_node": community_id_by_node,
        "meta": graph_data["meta"],
    }


def detect_communities(graph: nx.Graph) -> list[set[str]]:
    if graph.number_of_nodes() == 0:
        return []
    if graph.number_of_edges() == 0:
        return [{str(node)} for node in graph.nodes()]
    communities = list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
    return [set(str(node) for node in community) for community in sorted(communities, key=len, reverse=True)]


def analyze_communities(
    graph: nx.Graph,
    communities: list[set[str]],
    *,
    min_community_size: int,
) -> list[dict[str, Any]]:
    global_counts = global_label_counts(graph)
    rows: list[dict[str, Any]] = []
    for community_id, members in enumerate(communities):
        if len(members) < min_community_size:
            continue
        subgraph = graph.subgraph(members)
        labels = community_label_summary(graph, members, global_counts)
        rows.append(
            {
                "community": community_id,
                "size": len(members),
                "edge_count": subgraph.number_of_edges(),
                "density": round(nx.density(subgraph), 6) if len(members) > 1 else 0.0,
                "avg_degree": round(sum(dict(subgraph.degree()).values()) / max(len(members), 1), 4),
                "top_labels": labels,
                "example_nodes": example_nodes(graph, members),
            }
        )
    return rows


def community_label_summary(
    graph: nx.Graph,
    members: set[str],
    global_counts: dict[str, Counter[str]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for label_type in ("gene_id", "gene_symbol", "gene_family", "biotype"):
        counter: Counter[str] = Counter()
        for node_id in members:
            labels = graph.nodes[node_id].get("labels") or {}
            for value in label_values(labels, label_type):
                counter[str(value)] += 1
        if not counter:
            continue
        value, count = counter.most_common(1)[0]
        global_count = global_counts[label_type][value]
        global_rate = global_count / max(graph.number_of_nodes(), 1)
        community_rate = count / max(len(members), 1)
        result[label_type] = {
            "label": value,
            "count": count,
            "community_rate": round(community_rate, 4),
            "global_count": global_count,
            "global_rate": round(global_rate, 4),
            "enrichment": enrichment(community_rate, global_rate),
            "hypergeom_p": hypergeom_tail(
                population=graph.number_of_nodes(),
                successes=global_count,
                draws=len(members),
                observed=count,
            ),
        }
    return result


def global_label_counts(graph: nx.Graph) -> dict[str, Counter[str]]:
    counters: dict[str, Counter[str]] = {key: Counter() for key in ("gene_id", "gene_symbol", "gene_family", "biotype")}
    for _, data in graph.nodes(data=True):
        labels = data.get("labels") or {}
        for label_type, counter in counters.items():
            for value in set(label_values(labels, label_type)):
                counter[str(value)] += 1
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


def example_nodes(graph: nx.Graph, members: set[str], limit: int = 8) -> list[dict[str, Any]]:
    ranked = sorted(members, key=lambda node_id: graph.degree(node_id), reverse=True)[:limit]
    rows: list[dict[str, Any]] = []
    for node_id in ranked:
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


def count_labeled_nodes(graph: nx.Graph) -> dict[str, int]:
    result = {key: 0 for key in ("gene_id", "gene_symbol", "gene_family", "biotype")}
    for _, data in graph.nodes(data=True):
        labels = data.get("labels") or {}
        for label_type in result:
            if label_values(labels, label_type):
                result[label_type] += 1
    return result


def relation_edge_rows(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for edge in edges:
        counts[str(edge.get("relation_type") or "")] += 1
    return dict(sorted(counts.items()))


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
        raw.update(nested)
        rows.append(
            {
                "id": ids[index] if index < len(ids) else "",
                "metadata": raw,
                "document": documents[index] if index < len(documents) else None,
            }
        )
    return rows


def extract_biological_labels(metadata: dict[str, Any]) -> dict[str, list[str]]:
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
    text = str(symbol or "").upper()
    if text.startswith(("IGHV", "IGKV", "IGLV", "TRAV", "TRBV", "TRGV", "TRDV")):
        match = re.match(r"^([A-Z]+)", text)
        if match:
            return match.group(1)
    return None


def render_markdown(graph_path: Path, analysis: dict[str, Any]) -> str:
    summary = analysis["summary"]
    lines = [
        f"# DRAG View Graph Analysis: {graph_path.name}",
        "",
        "## Summary",
        "",
        f"- Target: `{summary.get('target')}`",
        f"- Recipe: `{summary.get('recipe')}`",
        f"- Biological rules used: `{str(summary.get('biological_rules_used')).lower()}`",
        f"- Nodes: `{summary['node_count']}`",
        f"- Edges: `{summary['edge_count']}` undirected from `{summary['directed_edge_rows']}` edge rows",
        f"- Connected components: `{summary['connected_components']}`",
        f"- Largest component: `{summary['largest_component']}`",
        f"- Communities: `{summary['community_count']}`",
        f"- Modularity: `{summary['modularity']}`",
        "",
        "## Top Communities",
        "",
        "| Community | Size | Density | Top gene/symbol/family/biotype labels |",
        "| ---: | ---: | ---: | --- |",
    ]
    for row in analysis["communities"][:12]:
        labels = compact_label_summary(row.get("top_labels") or {})
        lines.append(f"| {row['community']} | {row['size']} | {row['density']:.4f} | {labels} |")
    lines.extend(["", *interpretation_lines(summary), ""])
    return "\n".join(lines)


def interpretation_lines(summary: dict[str, Any]) -> list[str]:
    recipe = str(summary.get("recipe") or "")
    if recipe == "blast_sequence_neighbors":
        return [
            "Interpretation: this graph is an alignment-derived BLAST-neighbor DRAG",
            "view over the same sequence entities. It is a biological-rule baseline",
            "for comparison with the pure vector-neighbor graph, not a text-style",
            "embedding-only graph.",
        ]
    if recipe == "hybrid_vector_blast_neighbors":
        return [
            "Interpretation: this graph is a hybrid DRAG view combining vector",
            "neighbors with BLAST-derived sequence-similarity edges over the same",
            "sequence entities. It tests whether biological-rule edges sharpen local",
            "modules while preserving vector-graph connectivity for RAG expansion.",
        ]
    return [
        "Interpretation: this graph is a text-style vector-neighbor DRAG view.",
        "Edges are not BLAST/domain/pathway biological rules. Community labels are",
        "therefore evidence of neighborhood structure that emerges from the vector",
        "representation and graph recipe, not proof of a biological mechanism.",
    ]


def render_html(graph_path: Path, analysis: dict[str, Any], svg_body: str) -> str:
    summary = analysis["summary"]
    community_rows = "\n".join(
        f"<tr><td>{row['community']}</td><td>{row['size']}</td><td>{row['density']:.3f}</td>"
        f"<td>{html.escape(compact_label_summary(row.get('top_labels') or {}))}</td></tr>"
        for row in analysis["communities"][:12]
    )
    legend_items = "\n".join(
        f'<span class="legend-item"><span style="background:{PALETTE[i % len(PALETTE)]}"></span>C{i}</span>'
        for i in range(min(int(summary["community_count"]), 12))
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>DRAG View Graph - {html.escape(graph_path.name)}</title>
<style>
body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #172033; background: #f8fafc; }}
.shell {{ display: grid; grid-template-columns: minmax(720px, 1fr) 360px; min-height: 100vh; }}
.viz {{ padding: 24px; }}
.panel {{ background: #ffffff; border-left: 1px solid #dbe3ef; padding: 24px; box-shadow: -12px 0 30px rgba(15, 23, 42, 0.05); }}
h1 {{ margin: 0 0 6px; font-size: 22px; }}
h2 {{ margin-top: 24px; font-size: 15px; }}
p {{ line-height: 1.5; }}
.meta {{ color: #526174; font-size: 13px; }}
.cards {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 18px 0; }}
.card {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #f8fafc; }}
.num {{ font-size: 21px; font-weight: 700; color: #0f172a; }}
.label {{ font-size: 12px; color: #64748b; }}
svg {{ width: 100%; height: calc(100vh - 48px); min-height: 680px; background: #ffffff; border: 1px solid #dbe3ef; border-radius: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
td, th {{ border-bottom: 1px solid #e5e7eb; padding: 7px 4px; vertical-align: top; }}
th {{ text-align: left; color: #475569; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }}
.legend-item {{ font-size: 12px; color: #334155; }}
.legend-item span {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: -1px; }}
.note {{ font-size: 12px; color: #64748b; }}
</style>
</head>
<body>
<div class="shell">
  <main class="viz">
    {svg_body}
  </main>
  <aside class="panel">
    <h1>DRAG View Graph</h1>
    <div class="meta">{html.escape(graph_path.name)}</div>
    <p class="note">Pure text-style vector-neighbor graph. Edges are not BLAST/domain/pathway biological rules.</p>
    <div class="cards">
      <div class="card"><div class="num">{summary['node_count']}</div><div class="label">nodes</div></div>
      <div class="card"><div class="num">{summary['edge_count']}</div><div class="label">edges</div></div>
      <div class="card"><div class="num">{summary['community_count']}</div><div class="label">communities</div></div>
      <div class="card"><div class="num">{summary['modularity']}</div><div class="label">modularity</div></div>
    </div>
    <h2>Communities</h2>
    <div class="legend">{legend_items}</div>
    <table>
      <thead><tr><th>C</th><th>Size</th><th>Density</th><th>Dominant labels</th></tr></thead>
      <tbody>{community_rows}</tbody>
    </table>
    <h2>Interpretation</h2>
    <p class="note">Community labels are a hypothesis-generating signal for biological structure in the vector representation. The next ablation should compare this graph against BLAST/domain/pathway rule-enriched graphs.</p>
  </aside>
</div>
</body>
</html>
"""


def render_svg(graph_path: Path, analysis: dict[str, Any], layout: dict[Any, Any]) -> str:
    graph: nx.Graph = analysis["graph"]
    width = 1200
    height = 820
    positions = scale_layout(layout, width=width, height=height, pad=50)
    edge_svg = []
    for source, target, data in graph.edges(data=True):
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        weight = float(data.get("weight") or 0.0)
        opacity = min(max((weight - 0.85) / 0.15, 0.08), 0.45)
        edge_svg.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="#64748b" stroke-opacity="{opacity:.3f}" stroke-width="1" />'
        )
    node_svg = []
    high_degree = set(node for node, _ in sorted(graph.degree(), key=lambda item: item[1], reverse=True)[:20])
    for node_id, data in graph.nodes(data=True):
        x, y = positions[node_id]
        community = int(data.get("community") or 0)
        color = PALETTE[community % len(PALETTE)]
        degree = graph.degree(node_id)
        radius = min(4 + math.sqrt(max(degree, 0)) * 1.2, 12)
        label = display_label(data)
        title = tooltip(node_id, data, degree)
        node_svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{color}" '
            f'stroke="#0f172a" stroke-opacity="0.35" stroke-width="0.8"><title>{title}</title></circle>'
        )
        if node_id in high_degree and label:
            node_svg.append(
                f'<text x="{x + radius + 3:.2f}" y="{y + 4:.2f}" font-size="10" '
                f'fill="#111827">{html.escape(label[:28])}</text>'
            )
    return f"""<svg viewBox="0 0 {width} {height}" role="img" aria-label="DRAG vector-neighbor graph" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
      {"".join(edge_svg)}
      {"".join(node_svg)}
    </svg>"""


def scale_layout(layout: dict[Any, Any], *, width: int, height: int, pad: int) -> dict[str, tuple[float, float]]:
    xs = [float(pos[0]) for pos in layout.values()] or [0.0]
    ys = [float(pos[1]) for pos in layout.values()] or [0.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scaled = {}
    for node, pos in layout.items():
        x = pad + ((float(pos[0]) - min_x) / span_x) * (width - 2 * pad)
        y = pad + ((float(pos[1]) - min_y) / span_y) * (height - 2 * pad)
        scaled[str(node)] = (x, y)
    return scaled


def display_label(node: dict[str, Any]) -> str:
    labels = node.get("labels") or {}
    for key in ("gene_symbols", "protein_gene_names", "gene_ids", "gene_families"):
        values = labels.get(key) or []
        if values:
            return str(values[0])
    return str(node.get("name") or "")


def tooltip(node_id: str, node: dict[str, Any], degree: int) -> str:
    labels = node.get("labels") or {}
    parts = [
        node_id,
        f"degree={degree}",
        f"community={node.get('community')}",
    ]
    for key in ("gene_ids", "gene_symbols", "protein_gene_names", "gene_families", "gene_biotypes"):
        if labels.get(key):
            parts.append(f"{key}={','.join(labels[key])}")
    return html.escape(" | ".join(parts))


def compact_label_summary(labels: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    for label_type in ("gene_id", "gene_symbol", "gene_family", "biotype"):
        row = labels.get(label_type)
        if not row:
            continue
        parts.append(
            f"{label_type}:{row['label']} ({row['count']}, x{row['enrichment']})"
        )
    return "; ".join(parts) if parts else "-"


def jsonable_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": analysis["summary"],
        "communities": analysis["communities"],
        "meta": analysis["meta"],
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze and render a DRAG view graph")
    parser.add_argument("--graph", required=True, help="Path to view graph SQLite file")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--output-dir", default="reports/figures")
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--min-community-size", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260515)
    parser.add_argument("--layout-iterations", type=int, default=200)
    parser.add_argument("--no-chroma-labels", action="store_true", help="Do not fetch biological labels from Chroma")
    parser.add_argument("--analysis-only", action="store_true", help="Write JSON/Markdown analysis without SVG/HTML layout")
    return parser.parse_args()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate a paper-ready DRAG evidence graph showcase from trace JSON files."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

from paper_plot_style import save_figure


ROOT = Path(__file__).resolve().parents[1]


PANELS = [
    {
        "label": "A",
        "title": "DNA/cDNA IGKV evidence subgraph",
        "path": ROOT / "reports/traces/dna_igkv2_40_hybrid_trace.json",
        "focus": "IGKV",
        "focus_key": "gene_families",
        "accent": "#2563eb",
        "secondary": "#14b8a6",
    },
    {
        "label": "B",
        "title": "Protein yfbR evidence subgraph",
        "path": ROOT / "reports/traces/protein_yfbr_hybrid_trace.json",
        "focus": "yfbR",
        "focus_key": "protein_gene_names",
        "accent": "#dc2626",
        "secondary": "#f59e0b",
    },
]


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Serif",
            "font.size": 9,
            "axes.linewidth": 0.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig = plt.figure(figsize=(11.2, 6.2), facecolor="#f8fafc")
    gs = fig.add_gridspec(2, 2, height_ratios=[0.12, 0.88], wspace=0.10, hspace=0.02)
    title_ax = fig.add_subplot(gs[0, :])
    title_ax.axis("off")
    title_ax.text(
        0.01,
        0.72,
        "DRAG evidence graphs expose typed biological neighborhoods",
        fontsize=15,
        fontweight="bold",
        color="#0f172a",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.01,
        0.23,
        "Real trace subgraphs: vector edges provide representation-neighbor context; BLAST edges attach alignment-supported evidence.",
        fontsize=9,
        color="#475569",
        transform=title_ax.transAxes,
    )

    for index, spec in enumerate(PANELS):
        ax = fig.add_subplot(gs[1, index])
        render_panel(ax, spec)

    out_dir = ROOT / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_figure(fig, "fig6_drag_knowledge_graph_showcase")
    fig.savefig(out_dir / "fig6_drag_knowledge_graph_showcase.png", dpi=300, bbox_inches="tight", pad_inches=0.03)
    summary_path = out_dir / "fig6_drag_knowledge_graph_showcase_summary.json"
    summary_path.write_text(
        json.dumps([summarize_trace(spec) for spec in PANELS], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def render_panel(ax: plt.Axes, spec: dict[str, Any]) -> None:
    graph, nodes, edges, trace = load_trace(spec["path"])
    focus = spec["focus"]
    focus_key = spec["focus_key"]
    accent = spec["accent"]
    secondary = spec["secondary"]

    ax.set_facecolor("#ffffff")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    card = FancyBboxPatch(
        (0.0, 0.0),
        1.0,
        1.0,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        transform=ax.transAxes,
        linewidth=0.9,
        edgecolor="#dbe3ef",
        facecolor="#ffffff",
        zorder=-10,
    )
    ax.add_patch(card)

    pos = nx.spring_layout(graph, seed=9, k=0.82 / math.sqrt(max(graph.number_of_nodes(), 1)), iterations=500, weight="weight")
    pos = normalize_positions(pos)

    edge_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for source, target, data in graph.edges(data=True):
        relation_types = set(data.get("relation_types") or [])
        if "blast_neighbor" in relation_types:
            edge_groups["blast"].append((source, target))
        if "vector_neighbor" in relation_types:
            edge_groups["vector"].append((source, target))

    nx.draw_networkx_edges(
        graph,
        pos,
        edgelist=edge_groups.get("vector", []),
        ax=ax,
        width=1.1,
        edge_color="#64748b",
        alpha=0.30,
        style="solid",
        connectionstyle="arc3,rad=0.04",
    )
    nx.draw_networkx_edges(
        graph,
        pos,
        edgelist=edge_groups.get("blast", []),
        ax=ax,
        width=1.9,
        edge_color=accent,
        alpha=0.78,
        style="dashed",
        connectionstyle="arc3,rad=-0.05",
    )

    categories = {"focus": [], "same_family": [], "other": []}
    for node_id, node in nodes.items():
        labels = node.get("labels") or {}
        values = [str(value) for value in labels.get(focus_key, [])]
        if node.get("has_focus_label") or focus in values:
            categories["focus"].append(node_id)
        elif focus_key == "gene_families" and any(str(v).startswith("IG") for v in labels.get("gene_families", [])):
            categories["same_family"].append(node_id)
        else:
            categories["other"].append(node_id)

    degrees = dict(graph.degree())
    sizes = {node_id: 80 + 42 * math.sqrt(degrees.get(node_id, 0) + 1) for node_id in graph.nodes}
    draw_nodes(ax, graph, pos, categories["other"], "#cbd5e1", "#64748b", sizes)
    draw_nodes(ax, graph, pos, categories["same_family"], secondary, "#0f766e", sizes)
    draw_nodes(ax, graph, pos, categories["focus"], accent, "#7f1d1d" if accent == "#dc2626" else "#1e3a8a", sizes)

    label_nodes = pick_label_nodes(graph, nodes, categories["focus"], categories["same_family"], limit=8)
    labels = {node_id: display_name(nodes[node_id]) for node_id in label_nodes}
    nx.draw_networkx_labels(graph, pos, labels=labels, ax=ax, font_size=7.2, font_color="#0f172a")

    relation_counts = Counter()
    for _, _, data in graph.edges(data=True):
        for relation in data.get("relation_types") or []:
            relation_counts[relation] += 1

    focus_hits = sum(1 for node_id in graph.nodes if node_id in categories["focus"])
    subtitle = (
        f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges | "
        f"{relation_counts.get('vector_neighbor', 0)} vector, {relation_counts.get('blast_neighbor', 0)} BLAST | "
        f"{focus_hits} focus-labeled nodes"
    )
    ax.text(0.035, 0.965, f"{spec['label']}. {spec['title']}", transform=ax.transAxes, va="top", fontsize=11.5, fontweight="bold", color="#0f172a")
    ax.text(0.035, 0.925, subtitle, transform=ax.transAxes, va="top", fontsize=8, color="#475569")

    metric_text = make_metric_text(trace, focus)
    ax.text(
        0.035,
        0.055,
        metric_text,
        transform=ax.transAxes,
        fontsize=8,
        color="#334155",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.35,rounding_size=0.12", facecolor="#f8fafc", edgecolor="#e2e8f0", alpha=0.96),
    )

    legend_items = [
        Line2D([0], [0], color="#64748b", lw=1.5, alpha=0.45, label="vector edge"),
        Line2D([0], [0], color=accent, lw=2.0, ls="--", alpha=0.9, label="BLAST edge"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=accent, markeredgecolor="#ffffff", markersize=8, label=f"{focus} focus"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=secondary, markeredgecolor="#ffffff", markersize=8, label="related label"),
    ]
    ax.legend(handles=legend_items, loc="lower right", frameon=False, fontsize=7.5, handlelength=2.4)
    ax.set_xlim(-1.13, 1.13)
    ax.set_ylim(-1.13, 1.13)


def draw_nodes(ax: plt.Axes, graph: nx.Graph, pos: dict[str, tuple[float, float]], node_ids: list[str], color: str, edge: str, sizes: dict[str, float]) -> None:
    if not node_ids:
        return
    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=node_ids,
        node_size=[sizes[n] for n in node_ids],
        node_color=color,
        edgecolors="#ffffff",
        linewidths=1.3,
        alpha=0.96,
        ax=ax,
    )


def load_trace(path: Path) -> tuple[nx.Graph, dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    trace = json.loads(path.read_text(encoding="utf-8"))
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for item in trace.get("traces", []):
        seed = item.get("seed") or {}
        if seed.get("entity_id"):
            nodes[str(seed["entity_id"])] = seed
        for node in item.get("nodes", []):
            nodes[str(node["entity_id"])] = node
        edges.extend(item.get("edges", []))

    graph = nx.Graph()
    for node_id, node in nodes.items():
        graph.add_node(node_id, **node)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target or source == target:
            continue
        relation = str(edge.get("relation_type") or "related")
        weight = relation_weight(edge)
        if graph.has_edge(source, target):
            data = graph[source][target]
            data["weight"] = max(float(data.get("weight") or 0.0), weight)
            data.setdefault("relation_types", set()).add(relation)
        else:
            graph.add_edge(source, target, weight=weight, relation_types={relation})
    for _, _, data in graph.edges(data=True):
        data["relation_types"] = sorted(data.get("relation_types") or [])
    return graph, nodes, edges, trace


def relation_weight(edge: dict[str, Any]) -> float:
    relation = str(edge.get("relation_type") or "")
    if relation == "blast_neighbor":
        return 2.0 + min(float(edge.get("pident") or 0.0) / 100.0, 1.0)
    return 1.0 + float(edge.get("confidence") or 0.0)


def normalize_positions(pos: dict[str, Any]) -> dict[str, tuple[float, float]]:
    xs = [float(value[0]) for value in pos.values()]
    ys = [float(value[1]) for value in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    scale = max(max_x - min_x, max_y - min_y, 1e-9)
    return {
        node: (
            (float(value[0]) - (min_x + max_x) / 2) / scale * 2.0,
            (float(value[1]) - (min_y + max_y) / 2) / scale * 2.0,
        )
        for node, value in pos.items()
    }


def pick_label_nodes(graph: nx.Graph, nodes: dict[str, dict[str, Any]], focus_nodes: list[str], related_nodes: list[str], *, limit: int) -> list[str]:
    ranked = sorted(focus_nodes, key=lambda node: graph.degree(node), reverse=True)
    ranked += sorted(related_nodes, key=lambda node: graph.degree(node), reverse=True)
    ranked += sorted(graph.nodes, key=lambda node: graph.degree(node), reverse=True)
    result: list[str] = []
    for node in ranked:
        if node in result:
            continue
        result.append(node)
        if len(result) >= limit:
            break
    return result


def display_name(node: dict[str, Any]) -> str:
    labels = node.get("display_labels") or node.get("labels") or {}
    for key in ("gene_symbols", "protein_gene_names", "gene_families"):
        values = labels.get(key) or []
        if values:
            return str(values[0])
    return str(node.get("name") or node.get("entity_id") or "")[-12:]


def make_metric_text(trace: dict[str, Any], focus: str) -> str:
    summary = trace.get("summary") or {}
    relation_counts = summary.get("relation_counts") or {}
    return (
        f"Trace seeds: {trace.get('seed_count', '-')}; avg nodes: {summary.get('avg_context_nodes', '-')}\n"
        f"Avg focus-neighbor hits: {summary.get('avg_focus_label_neighbor_hits', '-')} ({focus})\n"
        f"Evidence edge mix: vector {relation_counts.get('vector_neighbor', 0)}, BLAST {relation_counts.get('blast_neighbor', 0)}"
    )


def summarize_trace(spec: dict[str, Any]) -> dict[str, Any]:
    graph, nodes, edges, trace = load_trace(spec["path"])
    return {
        "panel": spec["label"],
        "title": spec["title"],
        "trace_file": str(spec["path"].relative_to(ROOT)),
        "focus": spec["focus"],
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "trace_summary": trace.get("summary") or {},
    }


if __name__ == "__main__":
    main()

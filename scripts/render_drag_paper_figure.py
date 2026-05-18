#!/usr/bin/env python3
"""Render a paper-style two-panel DRAG knowledge graph figure."""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import analyze_view_graph as view_graph


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
]


@dataclass(frozen=True, slots=True)
class Panel:
    title: str
    label: str
    graph_path: Path
    analysis: dict[str, Any]
    positions: dict[str, tuple[float, float]]
    shown_edges: set[tuple[str, str]]


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    panels = [
        load_panel(
            title="DNA/cDNA sequence DRAG view",
            label="A",
            graph_path=Path(args.dna_graph),
            config_path=args.config,
            seed=args.seed,
            layout_iterations=args.layout_iterations,
            edge_budget=args.edge_budget,
        ),
        load_panel(
            title="Protein sequence DRAG view",
            label="B",
            graph_path=Path(args.protein_graph),
            config_path=args.config,
            seed=args.seed + 1,
            layout_iterations=args.layout_iterations,
            edge_budget=args.edge_budget,
        ),
    ]

    prefix = args.prefix
    svg_path = output_dir / f"{prefix}.svg"
    html_path = output_dir / f"{prefix}.html"
    json_path = output_dir / f"{prefix}_summary.json"
    md_path = output_dir / f"{prefix}_analysis.md"

    summary = build_summary(panels)
    svg_body = render_svg(panels, summary)
    svg_path.write_text(svg_body, encoding="utf-8")
    html_path.write_text(render_html(svg_body, summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(summary, panels), encoding="utf-8")

    print(
        json.dumps(
            {
                "svg": str(svg_path),
                "html": str(html_path),
                "json": str(json_path),
                "markdown": str(md_path),
            },
            indent=2,
        )
    )


def load_panel(
    *,
    title: str,
    label: str,
    graph_path: Path,
    config_path: str,
    seed: int,
    layout_iterations: int,
    edge_budget: int,
) -> Panel:
    graph_data = view_graph.read_graph(graph_path)
    view_graph.enrich_labels_from_chroma(graph_data, config_path=config_path)
    analysis = view_graph.analyze_graph(graph_data, min_community_size=3)
    graph = analysis["graph"].copy()
    graph.remove_edges_from(nx.selfloop_edges(graph))
    layout = nx.spring_layout(graph, seed=seed, weight="weight", iterations=layout_iterations)
    positions = scale_layout(layout, width=700, height=570, pad=48)
    shown_edges = select_display_edges(graph, per_node=3, budget=edge_budget)
    return Panel(
        title=title,
        label=label,
        graph_path=graph_path,
        analysis=analysis,
        positions=positions,
        shown_edges=shown_edges,
    )


def select_display_edges(graph: nx.Graph, *, per_node: int, budget: int) -> set[tuple[str, str]]:
    selected: set[tuple[str, str]] = set()
    for node_id in graph.nodes:
        incident = []
        for neighbor in graph.neighbors(node_id):
            if neighbor == node_id:
                continue
            data = graph.get_edge_data(node_id, neighbor) or {}
            incident.append((float(data.get("weight") or 0.0), str(node_id), str(neighbor)))
        for _, source, target in sorted(incident, reverse=True)[:per_node]:
            selected.add(canonical_edge(source, target))
    all_edges = [
        (
            float(data.get("weight") or 0.0),
            canonical_edge(str(source), str(target)),
        )
        for source, target, data in graph.edges(data=True)
        if source != target
    ]
    for _, edge in sorted(all_edges, reverse=True):
        if len(selected) >= budget:
            break
        selected.add(edge)
    return selected


def render_svg(panels: list[Panel], summary: dict[str, Any]) -> str:
    width = 1680
    height = 1040
    panel_y = 176
    graph_w = 700
    graph_h = 570
    left_x = 72
    right_x = 870
    panel_chunks = [
        render_panel(panels[0], x=left_x, y=panel_y, width=graph_w, height=graph_h),
        render_panel(panels[1], x=right_x, y=panel_y, width=graph_w, height=graph_h),
    ]
    cards = render_summary_cards(summary, x=72, y=794)
    notes = render_notes(x=870, y=794)
    return f"""<svg viewBox="0 0 {width} {height}" role="img" aria-label="DRAG knowledge graph figure" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#0f172a" flood-opacity="0.10"/>
    </filter>
  </defs>
  <rect width="{width}" height="{height}" fill="#f8fafc"/>
  <text x="72" y="72" font-family="Inter, Arial, sans-serif" font-size="36" font-weight="750" fill="#0f172a">DRAG view graphs from biological sequence embeddings</text>
  <text x="72" y="110" font-family="Inter, Arial, sans-serif" font-size="18" fill="#475569">Pure vector-neighbor graph construction; no BLAST, domain, pathway, or curated biological-rule edges are used.</text>
  <text x="72" y="140" font-family="Inter, Arial, sans-serif" font-size="15" fill="#64748b">Layouts are computed on the full graph; rendered edges are a high-confidence visual backbone for readability.</text>
  {"".join(panel_chunks)}
  {cards}
  {notes}
</svg>
"""


def render_panel(panel: Panel, *, x: int, y: int, width: int, height: int) -> str:
    graph: nx.Graph = panel.analysis["graph"].copy()
    graph.remove_edges_from(nx.selfloop_edges(graph))
    summary = panel.analysis["summary"]
    hulls = render_hulls(panel, x=x, y=y)
    edges = render_edges(panel, x=x, y=y)
    nodes = render_nodes(panel, x=x, y=y)
    callouts = render_callouts(panel, x=x, y=y, width=width, height=height)
    legend = render_legend(panel, x=x + 20, y=y + height + 38)
    return f"""
  <g>
    <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#ffffff" stroke="#dbe3ef" filter="url(#shadow)"/>
    <text x="{x + 20}" y="{y + 34}" font-family="Inter, Arial, sans-serif" font-size="20" font-weight="700" fill="#0f172a">{panel.label}. {html.escape(panel.title)}</text>
    <text x="{x + 20}" y="{y + 60}" font-family="Inter, Arial, sans-serif" font-size="13" fill="#64748b">{summary["node_count"]} nodes, {summary["edge_count"]} undirected edges, {summary["community_count"]} communities, modularity {summary["modularity"]}</text>
    <g transform="translate({x},{y + 74})">
      {hulls}
      {edges}
      {nodes}
      {callouts}
    </g>
    {legend}
  </g>
"""


def render_hulls(panel: Panel, *, x: int, y: int) -> str:
    graph: nx.Graph = panel.analysis["graph"]
    chunks: list[str] = []
    for row in panel.analysis["communities"][:10]:
        community_id = int(row["community"])
        members = [
            str(node_id)
            for node_id, data in graph.nodes(data=True)
            if int(data.get("community") or 0) == community_id and str(node_id) in panel.positions
        ]
        if len(members) < 3:
            continue
        xs = [panel.positions[node_id][0] for node_id in members]
        ys = [panel.positions[node_id][1] for node_id in members]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        rx = max((max(xs) - min(xs)) / 2 + 34, 42)
        ry = max((max(ys) - min(ys)) / 2 + 34, 42)
        color = PALETTE[community_id % len(PALETTE)]
        chunks.append(
            f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" '
            f'fill="{color}" fill-opacity="0.070" stroke="{color}" stroke-opacity="0.22" stroke-width="1.4"/>'
        )
    return "\n      ".join(chunks)


def render_edges(panel: Panel, *, x: int, y: int) -> str:
    graph: nx.Graph = panel.analysis["graph"]
    chunks: list[str] = []
    for source, target, data in graph.edges(data=True):
        edge = canonical_edge(str(source), str(target))
        if edge not in panel.shown_edges or source == target:
            continue
        if str(source) not in panel.positions or str(target) not in panel.positions:
            continue
        x1, y1 = panel.positions[str(source)]
        x2, y2 = panel.positions[str(target)]
        weight = float(data.get("weight") or 0.0)
        opacity = min(max((weight - 0.93) / 0.07, 0.08), 0.42)
        chunks.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="#334155" stroke-opacity="{opacity:.3f}" stroke-width="0.85"/>'
        )
    return "\n      ".join(chunks)


def render_nodes(panel: Panel, *, x: int, y: int) -> str:
    graph: nx.Graph = panel.analysis["graph"]
    max_degree = max((degree for _, degree in graph.degree()), default=1)
    labeled_nodes = top_labeled_nodes(graph, limit=14)
    chunks: list[str] = []
    for node_id, data in graph.nodes(data=True):
        node_id = str(node_id)
        if node_id not in panel.positions:
            continue
        px, py = panel.positions[node_id]
        community = int(data.get("community") or 0)
        color = PALETTE[community % len(PALETTE)]
        degree = graph.degree(node_id)
        radius = 3.0 + 6.5 * math.sqrt(degree / max(max_degree, 1))
        chunks.append(
            f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{radius:.2f}" fill="{color}" '
            f'stroke="#ffffff" stroke-width="1.1"><title>{tooltip(node_id, data, degree)}</title></circle>'
        )
        label = display_label(data)
        if node_id in labeled_nodes and label:
            chunks.append(
                f'<text x="{px + radius + 4:.2f}" y="{py + 3.5:.2f}" '
                f'font-family="Inter, Arial, sans-serif" font-size="10.5" font-weight="650" '
                f'fill="#0f172a">{html.escape(label[:22])}</text>'
            )
    return "\n      ".join(chunks)


def render_callouts(panel: Panel, *, x: int, y: int, width: int, height: int) -> str:
    rows = [row for row in panel.analysis["communities"] if community_label_score(row) > 0]
    rows = sorted(rows, key=community_label_score, reverse=True)[:3]
    chunks: list[str] = []
    for index, row in enumerate(rows):
        community_id = int(row["community"])
        label = dominant_label(row)
        color = PALETTE[community_id % len(PALETTE)]
        chunks.append(
            f'<rect x="{width - 224}" y="{18 + index * 44}" width="194" height="33" rx="6" '
            f'fill="#ffffff" stroke="{color}" stroke-opacity="0.45"/>'
        )
        chunks.append(
            f'<circle cx="{width - 207}" cy="{35 + index * 44}" r="5" fill="{color}"/>'
        )
        chunks.append(
            f'<text x="{width - 196}" y="{31 + index * 44}" font-family="Inter, Arial, sans-serif" '
            f'font-size="11" font-weight="700" fill="#0f172a">C{community_id}: {html.escape(label[:22])}</text>'
        )
        chunks.append(
            f'<text x="{width - 196}" y="{45 + index * 44}" font-family="Inter, Arial, sans-serif" '
            f'font-size="10" fill="#64748b">{row["size"]} nodes, density {row["density"]:.2f}</text>'
        )
    return "\n      ".join(chunks)


def render_legend(panel: Panel, *, x: int, y: int) -> str:
    items = []
    for row in panel.analysis["communities"][:7]:
        community_id = int(row["community"])
        color = PALETTE[community_id % len(PALETTE)]
        label = dominant_label(row, prefer_family=True)
        items.append(
            f'<g transform="translate({len(items) * 94},0)">'
            f'<circle cx="0" cy="0" r="5" fill="{color}"/>'
            f'<text x="10" y="4" font-family="Inter, Arial, sans-serif" font-size="11" fill="#334155">C{community_id} {html.escape(label[:10])}</text>'
            f'</g>'
        )
    return f'<g transform="translate({x},{y})">{"".join(items)}</g>'


def render_summary_cards(summary: dict[str, Any], *, x: int, y: int) -> str:
    cards = [
        ("DNA dominant modules", summary["highlights"]["dna"]),
        ("Protein dominant module", summary["highlights"]["protein"]),
        ("Construction", "Text-style vector-neighbor DRAG; biological_rules_used=false."),
        ("Claim boundary", "Label-enriched neighborhoods, not proof of biological mechanism."),
    ]
    chunks = []
    for index, (title, text) in enumerate(cards):
        cx = x + (index % 2) * 392
        cy = y + (index // 2) * 94
        chunks.append(
            f'<rect x="{cx}" y="{cy}" width="360" height="74" rx="10" fill="#ffffff" stroke="#dbe3ef"/>'
        )
        chunks.append(
            f'<text x="{cx + 18}" y="{cy + 25}" font-family="Inter, Arial, sans-serif" font-size="13" font-weight="750" fill="#0f172a">{html.escape(title)}</text>'
        )
        chunks.append(
            f'<text x="{cx + 18}" y="{cy + 50}" font-family="Inter, Arial, sans-serif" font-size="12" fill="#475569">{html.escape(text[:88])}</text>'
        )
    return "\n  ".join(chunks)


def render_notes(*, x: int, y: int) -> str:
    lines = [
        "Interpretation",
        "The sequence embedding space supports graph modules that recover recognizable labels.",
        "DNA/cDNA gives the cleaner signal: immunoglobulin variable-family neighborhoods emerge.",
        "Protein is more heterogeneous but still yields enriched modules, including YWHAB.",
        "Next ablation: compare pure vector edges with BLAST/domain/pathway-enriched DRAG graphs.",
    ]
    chunks = [
        f'<rect x="{x}" y="{y}" width="700" height="168" rx="10" fill="#ffffff" stroke="#dbe3ef"/>',
        f'<text x="{x + 18}" y="{y + 29}" font-family="Inter, Arial, sans-serif" font-size="15" font-weight="750" fill="#0f172a">{lines[0]}</text>',
    ]
    for index, line in enumerate(lines[1:]):
        chunks.append(
            f'<text x="{x + 18}" y="{y + 58 + index * 25}" font-family="Inter, Arial, sans-serif" font-size="13" fill="#475569">{html.escape(line)}</text>'
        )
    return "\n  ".join(chunks)


def build_summary(panels: list[Panel]) -> dict[str, Any]:
    result = {
        "figure": "DRAG knowledge graph paper-style two-panel figure",
        "construction": "text_style_vector_neighbors",
        "biological_rules_used": False,
        "panels": [],
        "highlights": {},
    }
    for panel in panels:
        result["panels"].append(
            {
                "title": panel.title,
                "graph": str(panel.graph_path),
                "summary": panel.analysis["summary"],
                "communities": [
                    {
                        "community": row["community"],
                        "size": row["size"],
                        "density": row["density"],
                        "dominant_label": dominant_label(row),
                        "top_labels": row.get("top_labels") or {},
                    }
                    for row in panel.analysis["communities"][:8]
                ],
                "displayed_edge_count": len(panel.shown_edges),
            }
        )
    result["highlights"] = {
        "dna": summarize_panel_highlight(panels[0]),
        "protein": summarize_panel_highlight(panels[1]),
    }
    return result


def render_markdown(summary: dict[str, Any], panels: list[Panel]) -> str:
    lines = [
        "# DRAG Paper Figure Analysis",
        "",
        "This figure renders sequence-derived DRAG view graphs built with the",
        "`text_style_vector_neighbors` recipe. Edges are vector-neighbor links only;",
        "BLAST, domain, pathway, and curated biological-rule edges are not used.",
        "",
        "## Figure Outputs",
        "",
        "- SVG: `reports/figures/drag_paper_knowledge_graph.svg`",
        "- HTML: `reports/figures/drag_paper_knowledge_graph.html`",
        "- JSON: `reports/figures/drag_paper_knowledge_graph_summary.json`",
        "",
        "## Panel Summary",
        "",
        "| Panel | Nodes | Edges | Displayed edges | Communities | Modularity | Main signal |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for panel, row in zip(panels, summary["panels"], strict=True):
        panel_summary = row["summary"]
        lines.append(
            f"| {panel.title} | {panel_summary['node_count']} | {panel_summary['edge_count']} | "
            f"{row['displayed_edge_count']} | {panel_summary['community_count']} | "
            f"{panel_summary['modularity']} | {summarize_panel_highlight(panel)} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- DNA/cDNA is the strongest figure candidate: immunoglobulin variable-family neighborhoods are separated by a pure vector-neighbor graph recipe.",
            "- Protein is more heterogeneous, but label-enriched modules are still visible; the clearest current example is the YWHAB-enriched community.",
            "- The result supports DRAG as a hypothesis-generating biological representation layer for multimodal BioRAG, not as a replacement for BLAST.",
            "- The next paper-grade ablation should compare pure vector edges with BLAST, domain, GO, and pathway rule-enriched DRAG graphs.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(svg_body: str, summary: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>DRAG Paper Knowledge Graph</title>
<style>
body {{ margin: 0; background: #eef2f7; font-family: Inter, Arial, sans-serif; }}
.wrap {{ max-width: 1680px; margin: 0 auto; padding: 20px; }}
svg {{ width: 100%; height: auto; display: block; }}
</style>
</head>
<body>
<main class="wrap">
{svg_body}
</main>
</body>
</html>
"""


def summarize_panel_highlight(panel: Panel) -> str:
    labels = []
    rows = sorted(panel.analysis["communities"], key=community_label_score, reverse=True)
    for row in rows[:4]:
        label = dominant_label(row, prefer_family=True)
        if label and label != "-":
            labels.append(f"C{row['community']} {label}")
    return "; ".join(labels[:3]) if labels else "label-enriched vector modules"


def community_label_score(row: dict[str, Any]) -> float:
    best = 0.0
    for item in (row.get("top_labels") or {}).values():
        best = max(best, label_score(item))
    return best


def dominant_label(row: dict[str, Any], *, prefer_family: bool = False) -> str:
    labels = row.get("top_labels") or {}
    order = ("gene_family", "gene_symbol", "gene_id", "biotype") if prefer_family else (
        "gene_symbol",
        "gene_family",
        "gene_id",
        "biotype",
    )
    ranked = []
    for order_index, key in enumerate(order):
        item = labels.get(key)
        if item and item.get("label") and label_score(item) > 0:
            ranked.append((label_score(item) - order_index * 0.001, order_index, item))
    if ranked:
        item = sorted(ranked, key=lambda value: (value[0], -value[1]), reverse=True)[0][2]
        enrichment = item.get("enrichment")
        suffix = f" x{enrichment}" if isinstance(enrichment, (int, float, str)) else ""
        return f"{item['label']}{suffix}"
    return "-"


def label_score(item: dict[str, Any]) -> float:
    count = float(item.get("count") or 0.0)
    if count < 2:
        return 0.0
    enrichment = item.get("enrichment")
    enrichment_value = float(enrichment) if isinstance(enrichment, (int, float)) else 0.0
    if enrichment_value <= 1.05:
        return 0.0
    p_value = item.get("hypergeom_p")
    p_bonus = -math.log10(max(float(p_value), 1e-12)) if isinstance(p_value, (int, float)) else 0.0
    count_bonus = max(count - 1.0, 0.0) * 10.0
    return count_bonus + math.log1p(max(enrichment_value, 0.0)) + p_bonus


def top_labeled_nodes(graph: nx.Graph, *, limit: int) -> set[str]:
    candidates = []
    for node_id, data in graph.nodes(data=True):
        if display_label(data):
            candidates.append((graph.degree(node_id), str(node_id)))
    return {node_id for _, node_id in sorted(candidates, reverse=True)[:limit]}


def display_label(node: dict[str, Any]) -> str:
    labels = node.get("labels") or {}
    for key in ("gene_symbols", "protein_gene_names", "gene_families", "gene_ids"):
        values = labels.get(key) or []
        if values:
            return str(values[0])
    return ""


def tooltip(node_id: str, node: dict[str, Any], degree: int) -> str:
    labels = node.get("labels") or {}
    values = []
    for key in ("gene_symbols", "protein_gene_names", "gene_families", "gene_ids"):
        if labels.get(key):
            values.append(f"{key}={','.join(labels[key])}")
    text = f"{node_id} | degree={degree} | community={node.get('community')}"
    if values:
        text += " | " + " | ".join(values)
    return html.escape(text)


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


def canonical_edge(source: str, target: str) -> tuple[str, str]:
    return (source, target) if source <= target else (target, source)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a paper-style DRAG knowledge graph figure")
    parser.add_argument("--dna-graph", default="indexes/standard/graph/views/dna_sequence_window_1k.sqlite")
    parser.add_argument("--protein-graph", default="indexes/standard/graph/views/protein_sequence_window_1k.sqlite")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--output-dir", default="reports/figures")
    parser.add_argument("--prefix", default="drag_paper_knowledge_graph")
    parser.add_argument("--seed", type=int, default=20260515)
    parser.add_argument("--layout-iterations", type=int, default=240)
    parser.add_argument("--edge-budget", type=int, default=900)
    return parser.parse_args()


if __name__ == "__main__":
    main()

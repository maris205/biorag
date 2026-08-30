#!/usr/bin/env python3
"""Generate the BioRAG-SeqLit-DAG sequence-to-literature figure."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from paper_plot_style import COLORS, save_figure


ROOT = Path(__file__).resolve().parents[1]
DAG_DIR = ROOT / "data/seq_lit_dag_swissprot_2k"


def main() -> None:
    manifest = load_manifest()
    counts = manifest.get("counts") or {}

    fig, ax = plt.subplots(figsize=(10.2, 4.35))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(
        0.02,
        0.955,
        "BioRAG-SeqLit-DAG: sequence-first literature evidence",
        fontsize=11.8,
        fontweight="bold",
        color="#0f172a",
        ha="left",
        va="top",
    )
    ax.text(
        0.02,
        0.905,
        "A held-out protein sequence retrieves candidates, traverses curated evidence, and reaches a citation-bounded local agent.",
        fontsize=7.9,
        color="#475569",
        ha="left",
        va="top",
    )

    # Main path nodes.
    query = draw_box(ax, 0.018, 0.43, 0.10, 0.17, "query\nprotein\nsequence", "#F8FAFC", COLORS["dark"])
    candidate = draw_box(ax, 0.158, 0.40, 0.13, 0.22, "candidate\nUniProt\nprotein", "#E8F4F2", COLORS["teal"])
    go = draw_box(ax, 0.338, 0.60, 0.12, 0.145, "GO term\nfunction /\nprocess", "#EEF2FF", COLORS["purple"], fontsize=8.0)
    evidence = draw_box(ax, 0.338, 0.35, 0.12, 0.145, "GOA evidence\ncode +\ncurator link", "#FFF3E0", COLORS["orange"], fontsize=7.8)
    paper = draw_box(ax, 0.508, 0.43, 0.12, 0.19, "PubMed\npaper\nPMID citation", "#F0F7EC", COLORS["green"], fontsize=8.0)
    pack = draw_box(ax, 0.678, 0.43, 0.12, 0.19, "Graph-IDF\ncompact\nevidence pack", "#F3EEFA", COLORS["purple"], fontsize=7.8)
    agent = draw_box(ax, 0.848, 0.40, 0.13, 0.22, "local agent\ncite IDs\nor abstain", "#EAF2F8", COLORS["blue"], fontsize=8.1)

    # Context nodes.
    gene = draw_box(ax, 0.158, 0.16, 0.13, 0.11, "gene / organism", "#F8FAFC", COLORS["gray"], fontsize=7.8)
    future = draw_box(ax, 0.338, 0.13, 0.12, 0.12, "domain / family /\npathway extension", "#F8FAFC", COLORS["gray"], fontsize=7.1)

    arrow(ax, right(query), left(candidate), COLORS["dark"])
    arrow(ax, right(candidate, dy=0.045), left(go, dy=-0.015), COLORS["teal"])
    arrow(ax, right(candidate, dy=-0.045), left(evidence, dy=0.015), COLORS["orange"])
    arrow(ax, right(go), left(paper, dy=0.06), COLORS["purple"])
    arrow(ax, right(evidence), left(paper, dy=-0.055), COLORS["orange"])
    arrow(ax, right(paper), left(pack), COLORS["green"])
    arrow(ax, right(pack), left(agent), COLORS["purple"])
    arrow(ax, bottom(candidate), top(gene), COLORS["gray"])
    arrow(ax, right(gene), left(future), COLORS["gray"], rad=0.10)
    arrow(ax, top(future), bottom(evidence), COLORS["gray"])

    # Explain edge types without in-app tutorial wording; this is a paper figure legend.
    legend_y = 0.835
    legend_items = [
        ("sequence candidate", COLORS["teal"]),
        ("curated GO evidence", COLORS["orange"]),
        ("literature support", COLORS["green"]),
        ("graph selection", COLORS["purple"]),
        ("agent output", COLORS["blue"]),
    ]
    for idx, (label, color) in enumerate(legend_items):
        x = 0.025 + idx * 0.19
        ax.plot([x, x + 0.027], [legend_y, legend_y], color=color, lw=1.7, solid_capstyle="round")
        ax.text(x + 0.034, legend_y, label, fontsize=6.8, color="#334155", va="center", ha="left")

    stats = [
        ("DAG proteins", counts.get("selected_proteins", 0), COLORS["teal"]),
        ("GO annotations", counts.get("selected_go_annotations", 0), COLORS["orange"]),
        ("PMIDs", counts.get("selected_pmids", 0), COLORS["green"]),
        ("typed edges", counts.get("edge_count", 0), COLORS["purple"]),
    ]
    for idx, (label, value, color) in enumerate(stats):
        x = 0.035 + idx * 0.235
        ax.text(x, 0.050, f"{int(value):,}", fontsize=12.5, fontweight="bold", color=color, ha="left", va="bottom")
        ax.text(x, 0.027, label, fontsize=7.5, color="#475569", ha="left", va="bottom")

    ax.text(0.52, 0.205, "Typed identifiers bound what the agent may claim.", fontsize=7.4, color="#475569", ha="left", va="center")
    ax.text(0.52, 0.165, "Missing mechanism evidence triggers explicit abstention.", fontsize=7.4, color="#475569", ha="left", va="center")

    save_figure(fig, "fig7_seq_lit_dag")
    fig.savefig(ROOT / "figures/fig7_seq_lit_dag.png", dpi=300, bbox_inches="tight", pad_inches=0.04)


def load_manifest() -> dict[str, object]:
    path = DAG_DIR / "manifest.json"
    if not path.exists():
        return {"counts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def draw_box(
    ax: plt.Axes,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    face: str,
    edge: str,
    *,
    fontsize: float = 8.6,
) -> FancyBboxPatch:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.014,rounding_size=0.022",
        linewidth=1.15,
        edgecolor=edge,
        facecolor=face,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, color="#0f172a")
    return patch


def arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float], color: str, *, rad: float = 0.0) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=9,
            linewidth=1.35,
            color=color,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=5,
            shrinkB=5,
        )
    )


def left(box: FancyBboxPatch, *, dy: float = 0.0) -> tuple[float, float]:
    x, y = box.get_x(), box.get_y()
    return x - 0.012, y + box.get_height() / 2 + dy


def right(box: FancyBboxPatch, *, dy: float = 0.0) -> tuple[float, float]:
    x, y = box.get_x(), box.get_y()
    return x + box.get_width() + 0.012, y + box.get_height() / 2 + dy


def top(box: FancyBboxPatch) -> tuple[float, float]:
    x, y = box.get_x(), box.get_y()
    return x + box.get_width() / 2, y + box.get_height() + 0.012


def bottom(box: FancyBboxPatch) -> tuple[float, float]:
    x, y = box.get_x(), box.get_y()
    return x + box.get_width() / 2, y - 0.012


if __name__ == "__main__":
    main()

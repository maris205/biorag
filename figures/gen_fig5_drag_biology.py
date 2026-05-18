import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from paper_plot_style import COLORS, label_panel, save_figure


ROOT = Path(__file__).resolve().parents[1]


GRAPH_ORDER = [
    ("dna_vector", "DNA\nvector", COLORS["teal"]),
    ("dna_blast", "DNA\nBLAST", COLORS["orange"]),
    ("dna_hybrid", "DNA\nhybrid", COLORS["green"]),
    ("protein_vector", "Protein\nvector", COLORS["teal"]),
    ("protein_blast", "Protein\nBLAST", COLORS["orange"]),
    ("protein_hybrid", "Protein\nhybrid", COLORS["green"]),
]


def main():
    with (ROOT / "reports/drag_gene_family_purity_10k.json").open() as f:
        purity = json.load(f)
    with (ROOT / "reports/drag_functional_enrichment_10k.json").open() as f:
        func = json.load(f)
    with (ROOT / "reports/drag_literature_support_10k.json").open() as f:
        lit = json.load(f)

    fig, axes = plt.subplots(1, 3, figsize=(8.2, 3.05), constrained_layout=True)

    labels = [label for _, label, _ in GRAPH_ORDER]
    colors = [color for _, _, color in GRAPH_ORDER]
    x = np.arange(len(GRAPH_ORDER))

    components = [purity["graphs"][key]["summary"]["connected_components"] for key, _, _ in GRAPH_ORDER]
    modularity = [purity["graphs"][key]["summary"]["modularity"] for key, _, _ in GRAPH_ORDER]
    ax0 = axes[0]
    ax0.bar(x, components, color=colors, alpha=0.78)
    ax0.set_yscale("log")
    ax0.set_ylabel("connected components (log)")
    ax0.set_xticks(x)
    ax0.set_xticklabels(labels, rotation=35, ha="right")
    ax0b = ax0.twinx()
    ax0b.plot(x, modularity, color=COLORS["dark"], marker="o", linewidth=1.2)
    ax0b.set_ylim(0, 1.05)
    ax0b.set_yticks([0, 0.5, 1.0])
    ax0b.tick_params(axis="y", labelsize=7)
    ax0.text(0.04, 0.92, "black line: modularity", transform=ax0.transAxes, fontsize=7, color=COLORS["dark"])
    label_panel(ax0, "A")

    go_q = []
    react_q = []
    for key, _, _ in GRAPH_ORDER:
        summary = func["graphs"][key]["summary"]
        top_go = summary.get("top_go") or []
        top_reactome = summary.get("top_reactome") or []
        go_q.append(-np.log10(max(top_go[0]["q_value"], 1e-12)) if top_go else 0)
        react_q.append(-np.log10(max(top_reactome[0]["q_value"], 1e-12)) if top_reactome else 0)
    w = 0.36
    axes[1].bar(x - w / 2, go_q, width=w, color=COLORS["blue"], label="GO")
    axes[1].bar(x + w / 2, react_q, width=w, color=COLORS["purple"], label="Reactome")
    axes[1].set_ylabel("-log10(q)")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=35, ha="right")
    axes[1].legend(frameon=False, fontsize=7)
    label_panel(axes[1], "B")

    shared = [lit["graphs"][key]["summary"]["communities_with_shared_pmids"] for key, _, _ in GRAPH_ORDER]
    unique = [lit["graphs"][key]["summary"]["unique_pmids"] for key, _, _ in GRAPH_ORDER]
    axes[2].bar(x, shared, color=colors, alpha=0.82)
    axes[2].set_ylabel("communities with\nshared PMIDs")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(labels, rotation=35, ha="right")
    axes[2].set_ylim(0, max(shared) * 1.25)
    for i, u in enumerate(unique):
        axes[2].text(i, shared[i] + 0.45, f"{u:,}", ha="center", va="bottom", fontsize=6.6, rotation=90, color=COLORS["gray"])
    label_panel(axes[2], "C")

    save_figure(fig, "fig5_drag_biology")


if __name__ == "__main__":
    main()

import json
from pathlib import Path

import matplotlib.pyplot as plt

from paper_plot_style import COLORS, label_panel, save_figure


ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / "data/biorag_standard_v0/manifest.json").open() as f:
        manifest = json.load(f)

    corpus = manifest["corpus"]
    corpus_labels = ["Text", "Protein\nwindows", "DNA/cDNA\nwindows", "Mixed"]
    corpus_values = [
        corpus["standard_text"]["records"],
        corpus["protein_sequence_window"]["records"],
        corpus["dna_sequence_window"]["records"],
        corpus["mixed"]["records"],
    ]
    task_parts = manifest["tasks"]["partitions"]
    task_labels = ["Protein\nsequence", "DNA/cDNA\nsequence", "Gene\nlookup", "Pathway\nlookup"]
    task_values = [
        task_parts["protein_sequence"],
        task_parts["dna_sequence"],
        task_parts["gene_lookup"],
        task_parts["pathway_lookup"],
    ]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8), gridspec_kw={"width_ratios": [1.45, 1]})

    colors = [COLORS["blue"], COLORS["teal"], COLORS["green"], COLORS["gray"]]
    bars = axes[0].bar(corpus_labels, corpus_values, color=colors, edgecolor="white", linewidth=0.8)
    axes[0].set_ylabel("retrievable records")
    axes[0].set_ylim(0, 112000)
    label_panel(axes[0], "A")
    for bar, val in zip(bars, corpus_values):
        axes[0].text(bar.get_x() + bar.get_width() / 2, val + 2200, f"{val:,}", ha="center", va="bottom", fontsize=8)

    wedges, _ = axes[1].pie(
        task_values,
        colors=[COLORS["teal"], COLORS["green"], COLORS["blue"], COLORS["purple"]],
        startangle=90,
        wedgeprops={"linewidth": 0.8, "edgecolor": "white"},
    )
    axes[1].legend(
        wedges,
        [f"{l}: {v}" for l, v in zip(task_labels, task_values)],
        loc="center left",
        bbox_to_anchor=(0.92, 0.5),
        frameon=False,
        fontsize=8,
    )
    axes[1].set_aspect("equal")
    label_panel(axes[1], "B")
    axes[1].text(0, 0, "112\ntasks", ha="center", va="center", fontsize=10, fontweight="bold")

    save_figure(fig, "fig2_dataset")


if __name__ == "__main__":
    main()

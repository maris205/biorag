import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from paper_plot_style import COLORS, label_panel, save_figure


ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / "reports/instant_verified_latency_benchmark.json").open() as f:
        lat = json.load(f)
    with (ROOT / "reports/chroma_lookup_text_sequence_100k_benchmark.json").open() as f:
        chroma_text = json.load(f)
    with (ROOT / "reports/faiss_cpu_lookup_standard_text_57856.json").open() as f:
        faiss_text = json.load(f)
    with (ROOT / "reports/faiss_cpu_lookup_dna_sequence_window_100k.json").open() as f:
        faiss_dna = json.load(f)
    with (ROOT / "reports/faiss_cpu_lookup_protein_sequence_window_100k.json").open() as f:
        faiss_prot = json.load(f)

    comp = lat["composite_profiles"]
    dna_parts = comp["verified_vector_blast_graph"]["dna"]["parts_ms"]
    prot_parts = comp["verified_vector_blast_graph"]["protein"]["parts_ms"]
    instant = comp["instant_vector_only"]

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0), constrained_layout=True)

    labels = ["DNA/cDNA", "Protein"]
    vector = [dna_parts["vector_ms"], prot_parts["vector_ms"]]
    blast = [dna_parts["blast_ms"], prot_parts["blast_ms"]]
    graph = [dna_parts["graph_ms"], prot_parts["graph_ms"]]
    x = np.arange(2)
    w0 = 0.24
    axes[0].bar(x - w0, vector, width=w0, color=COLORS["teal"], label="vector lookup")
    axes[0].bar(x, blast, width=w0, color=COLORS["orange"], label="BLAST")
    axes[0].bar(x + w0, graph, width=w0, color=COLORS["green"], label="graph")
    axes[0].set_yscale("log")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_ylabel("median latency (ms, log)")
    axes[0].legend(frameon=False, loc="upper left")
    label_panel(axes[0], "A")

    lookup_labels = ["Text", "DNA/cDNA", "Protein"]
    chroma_vals = [
        chroma_text["vector_lookup"]["text"]["latency_ms"]["median"],
        instant["dna"]["median_ms"],
        instant["protein"]["median_ms"],
    ]
    faiss_vals = [
        faiss_text["lookup_ms_per_query"],
        faiss_dna["lookup_ms_per_query"],
        faiss_prot["lookup_ms_per_query"],
    ]
    w = 0.36
    x2 = np.arange(3)
    axes[1].bar(x2 - w / 2, chroma_vals, width=w, color=COLORS["teal"], label="Chroma")
    axes[1].bar(x2 + w / 2, faiss_vals, width=w, color=COLORS["blue"], label="FAISS CPU")
    axes[1].set_xticks(x2)
    axes[1].set_xticklabels(lookup_labels)
    axes[1].set_ylabel("top-10 lookup (ms)")
    axes[1].legend(frameon=False)
    for i, val in enumerate(chroma_vals):
        axes[1].text(i - w / 2, val + 0.4, f"{val:.1f}", ha="center", va="bottom", fontsize=7)
    for i, val in enumerate(faiss_vals):
        axes[1].text(i + w / 2, val + 0.4, f"{val:.1f}", ha="center", va="bottom", fontsize=7)
    label_panel(axes[1], "B")

    save_figure(fig, "fig4_latency")


if __name__ == "__main__":
    main()

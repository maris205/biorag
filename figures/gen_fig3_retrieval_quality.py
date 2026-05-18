import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from paper_plot_style import COLORS, label_panel, save_figure


ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / "reports/sequence_window_bf16_100k_100query_bio_split_summary.json").open() as f:
        split = json.load(f)
    with (ROOT / "reports/vector_candidate_budget_sweep_eval.json").open() as f:
        sweep = json.load(f)

    seed = split["seeds"]["seed20260516"]
    methods = [
        ("BLAST", seed["blast"]["bio_hit_at_10"], seed["blast"]["bio_mrr"], COLORS["orange"]),
        ("Vector", seed["vector"]["bio_hit_at_10"], seed["vector"]["bio_mrr"], COLORS["teal"]),
        ("Vector+\nseq rerank", seed["vector_rerank"]["bio_hit_at_10"], seed["vector_rerank"]["bio_mrr"], COLORS["blue"]),
        ("Hybrid\ngated", seed["hybrid_gated"]["bio_hit_at_10"], seed["hybrid_gated"]["bio_mrr"], COLORS["green"]),
    ]
    budgets = [10, 25, 50, 100, 200]
    summary = sweep["summary_by_budget"]
    overall = [summary[str(b)]["bio_hit_at_10"] for b in budgets]
    recall = [summary[str(b)]["candidate_bio_hit_at_n"] for b in budgets]
    dna = [sweep["category_summary_by_budget"]["dna_sequence"][str(b)]["bio_hit_at_10"] for b in budgets]
    protein = [sweep["category_summary_by_budget"]["protein_sequence"][str(b)]["bio_hit_at_10"] for b in budgets]

    fig, axes = plt.subplots(1, 2, figsize=(7.7, 3.0), constrained_layout=True)

    x = np.arange(len(methods))
    width = 0.36
    axes[0].bar(x - width / 2, [m[1] for m in methods], width, label="Bio Hit@10", color=[m[3] for m in methods])
    axes[0].bar(x + width / 2, [m[2] for m in methods], width, label="Bio MRR", color=COLORS["light_gray"], edgecolor=COLORS["dark"], linewidth=0.8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([m[0] for m in methods])
    axes[0].set_ylim(0.62, 1.02)
    axes[0].set_ylabel("score")
    axes[0].legend(frameon=False, loc="lower right")
    label_panel(axes[0], "A")

    axes[1].plot(budgets, overall, marker="o", color=COLORS["blue"], label="candidate BLAST Bio Hit@10")
    axes[1].plot(budgets, recall, marker="s", color=COLORS["green"], label="candidate Bio Recall@N")
    axes[1].plot(budgets, dna, marker="^", color=COLORS["teal"], linestyle="--", label="DNA/cDNA Bio Hit@10")
    axes[1].plot(budgets, protein, marker="v", color=COLORS["purple"], linestyle="--", label="protein Bio Hit@10")
    axes[1].set_xscale("log")
    axes[1].set_xticks(budgets)
    axes[1].get_xaxis().set_major_formatter(plt.ScalarFormatter())
    axes[1].set_ylim(0.80, 1.01)
    axes[1].set_xlabel("vector candidate budget")
    axes[1].set_ylabel("score")
    axes[1].legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(0.02, 0.98))
    label_panel(axes[1], "B")

    save_figure(fig, "fig3_retrieval_quality")


if __name__ == "__main__":
    main()

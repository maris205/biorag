from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.pyplot as plt

from paper_plot_style import COLORS, save_figure


def box(ax, xy, wh, text, fc, ec=None, fontsize=8.5):
    x, y = xy
    w, h = wh
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.018,rounding_size=0.025",
        linewidth=1.0,
        edgecolor=ec or COLORS["dark"],
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize)
    return patch


def arrow(ax, start, end, color=COLORS["dark"], rad=0.0, lw=1.2):
    arr = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=lw,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(arr)


def main():
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    box(ax, (0.03, 0.42), (0.17, 0.16), "query\ntext / DNA / protein", "#F7FAFC", fontsize=8.0)

    box(ax, (0.28, 0.70), (0.21, 0.15), "OmniGene vector\ncoarse retrieval", "#E8F4F2", COLORS["teal"])
    box(ax, (0.28, 0.42), (0.21, 0.15), "BLAST verification\nor reranking", "#FFF3E0", COLORS["orange"])
    box(ax, (0.28, 0.14), (0.21, 0.15), "FTS / SQL / metadata\ntext lookup", "#EEF2FF", COLORS["purple"])

    box(ax, (0.58, 0.63), (0.18, 0.14), "instant context\nvector candidates", "#E8F4F2", COLORS["teal"])
    box(ax, (0.58, 0.33), (0.18, 0.14), "verified evidence\nalignment support", "#FFF3E0", COLORS["orange"])

    box(ax, (0.81, 0.47), (0.15, 0.18), "DRAG graph\npaths + citations", "#F0F7EC", COLORS["green"])
    box(ax, (0.81, 0.18), (0.15, 0.14), "auditable\nagent answer", "#F7FAFC")

    arrow(ax, (0.20, 0.50), (0.28, 0.775))
    arrow(ax, (0.20, 0.50), (0.28, 0.50))
    arrow(ax, (0.20, 0.50), (0.28, 0.215))
    arrow(ax, (0.49, 0.775), (0.58, 0.70), COLORS["teal"])
    arrow(ax, (0.49, 0.50), (0.58, 0.40), COLORS["orange"])
    arrow(ax, (0.49, 0.215), (0.58, 0.40), COLORS["purple"], rad=0.08)
    arrow(ax, (0.76, 0.70), (0.81, 0.58), COLORS["teal"])
    arrow(ax, (0.76, 0.40), (0.81, 0.54), COLORS["orange"])
    arrow(ax, (0.885, 0.47), (0.885, 0.32), COLORS["green"])

    ax.text(0.355, 0.91, "unified candidate layer", ha="center", fontsize=8, color=COLORS["teal"])
    ax.text(0.67, 0.86, "fast response", ha="center", fontsize=8, color=COLORS["teal"])
    ax.text(0.67, 0.23, "verified mode", ha="center", fontsize=8, color=COLORS["orange"])
    ax.text(0.885, 0.73, "typed evidence", ha="center", fontsize=8, color=COLORS["green"])

    save_figure(fig, "fig1_architecture")


if __name__ == "__main__":
    main()

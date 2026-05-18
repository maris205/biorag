from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

FIG_DIR = Path(__file__).resolve().parent

matplotlib.rcParams.update(
    {
        "font.size": 9,
        "font.family": "serif",
        "font.serif": ["DejaVu Serif", "Times New Roman", "Times"],
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.04,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "grid.linewidth": 0.6,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "text.usetex": False,
        "mathtext.fontset": "stix",
    }
)

COLORS = {
    "blue": "#2F6B9A",
    "teal": "#2A9D8F",
    "green": "#4D8B31",
    "orange": "#E38B29",
    "red": "#C44E52",
    "purple": "#7A5AA6",
    "gray": "#6E7781",
    "light_gray": "#D8DEE4",
    "dark": "#1F2933",
    "gold": "#B8870B",
}


def save_figure(fig, name: str) -> None:
    out = FIG_DIR / f"{name}.pdf"
    fig.savefig(out)
    print(f"Saved {out}")


def label_panel(ax, label: str) -> None:
    ax.text(
        -0.08,
        1.04,
        label,
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        va="bottom",
        ha="left",
    )

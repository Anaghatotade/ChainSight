"""viz.py - one consistent chart style + a save helper (PNG files that open directly in Power BI / Excel / Word)."""
import matplotlib
matplotlib.use("Agg")                     # no pop-up windows: works on any machine / in scripts
import matplotlib.pyplot as plt
import seaborn as sns

import config as cfg

PALETTE = {"main": "#1f4e79", "accent": "#e07b00", "good": "#2e8b57", "bad": "#c0392b", "grey": "#7f8c8d"}


def setup():
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams.update({"figure.dpi": 100, "savefig.dpi": 150, "axes.titlesize": 13, "axes.titleweight": "bold",
                         "axes.labelsize": 11, "font.family": "DejaVu Sans"})


def save(fig, name):
    """Save figure to outputs/charts/<name>.png and close it."""
    cfg.CHARTS.mkdir(parents=True, exist_ok=True)
    path = cfg.CHARTS / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def pct_axis(ax, axis="y"):
    from matplotlib.ticker import PercentFormatter
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(PercentFormatter(1.0, decimals=None))


def money_axis(ax, axis="y", unit=1e6, suffix="M"):
    from matplotlib.ticker import FuncFormatter
    fmt = FuncFormatter(lambda v, _: f"${v / unit:,.1f}{suffix}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)

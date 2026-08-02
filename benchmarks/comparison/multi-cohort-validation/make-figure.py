"""Create the publication figure for the AXIS-versus-limma validation."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import NullLocator

HERE = Path(__file__).resolve().parent


def read_rows(name: str) -> list[dict[str, str]]:
    with (HERE / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


rows = read_rows("validation-summary.tsv")
adjusted = read_rows("adjusted-validation.tsv")[0]
all_rows = [*rows, adjusted]
labels = [
    f"{row['accession']}\n{row['platform']}" + ("\nadjusted" if row is adjusted else "")
    for row in all_rows
]
y = np.arange(len(all_rows))

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)
figure, axes = plt.subplots(1, 3, figsize=(12.5, 4.6), constrained_layout=True)

correlations = [float(row["effect_spearman"]) for row in all_rows]
axes[0].scatter(correlations, y, s=38, color="#176B87", zorder=3)
axes[0].axvline(1, color="#94A3B8", linewidth=1)
axes[0].set_xlim(0.9999999999988, 1.0000000000001)
axes[0].set_xticks(
    [0.999999999999, 1.0],
    [r"$1-10^{-12}$", "1.0"],
)
axes[0].set_yticks(y, labels)
axes[0].invert_yaxis()
axes[0].set_xlabel("Spearman correlation of effects")
axes[0].set_title("A  Effect estimates", loc="left", fontweight="bold")

top_100 = [int(row["top_100_overlap"]) / 100 for row in all_rows]
top_500 = [int(row["top_500_overlap"]) / 500 for row in all_rows]
axes[1].scatter(top_100, y - 0.11, marker="o", s=35, color="#176B87", label="Top 100")
axes[1].scatter(top_500, y + 0.11, marker="s", s=30, color="#D97706", label="Top 500")
axes[1].axvline(1, color="#94A3B8", linewidth=1)
axes[1].set_xlim(0.985, 1.002)
axes[1].set_xticks([0.99, 1.0], ["0.99", "1.00"])
axes[1].set_yticks([])
axes[1].invert_yaxis()
axes[1].set_xlabel("Fraction of probes shared")
axes[1].set_title("B  Ranked-list overlap", loc="left", fontweight="bold")
axes[1].legend(frameon=False, loc="lower left")

differences = [
    float(row["maximum_absolute_effect_difference"]) for row in all_rows
]
axes[2].scatter(differences, y, s=38, color="#176B87", zorder=3)
axes[2].set_xscale("log")
axes[2].set_xlim(4.5e-13, 5.6e-12)
axes[2].set_xticks(
    [5e-13, 1e-12, 5e-12],
    [r"$5\times10^{-13}$", r"$10^{-12}$", r"$5\times10^{-12}$"],
)
axes[2].xaxis.set_minor_locator(NullLocator())
axes[2].set_yticks([])
axes[2].invert_yaxis()
axes[2].set_xlabel("Maximum absolute difference")
axes[2].set_title("C  Numerical error", loc="left", fontweight="bold")
axes[2].grid(axis="x", color="#CBD5E1", linewidth=0.6)

figure.suptitle(
    "AXIS reproduces native limma results across four GEO cohorts",
    fontsize=13,
    fontweight="bold",
)
figure.text(
    0.5,
    -0.02,
    "Four unadjusted contrasts (163 samples, three platforms) and one "
    "covariate-adjusted contrast. All directions and adjusted-p rankings agree.",
    ha="center",
    fontsize=9,
)
for extension in ("png", "pdf"):
    figure.savefig(
        HERE / f"axis-limma-validation.{extension}",
        dpi=300,
        bbox_inches="tight",
    )
plt.close(figure)

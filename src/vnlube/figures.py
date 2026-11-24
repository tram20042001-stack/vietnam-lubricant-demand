"""Static report figures (PNG). The interactive views live in the Streamlit dashboard."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import FIGURES  # noqa: E402

# reference palette (validated categorical slots 1-3) and chart chrome
SEG_COLORS = {"MCO": "#2a78d6", "PCMO": "#eb6834", "HDMO": "#1baf7a"}
SEG_LABEL = {"MCO": "Motorbike oil (MCO)", "PCMO": "Passenger-car oil (PCMO)", "HDMO": "Heavy-duty oil (HDMO)"}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 10,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titlesize": 12,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "legend.frameon": False, "savefig.dpi": 160, "savefig.bbox": "tight",
})


def _save(fig, name: str) -> str:
    """Write a figure to reports/figures/<name> and free its memory."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / name
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def density_by_region(base: pd.DataFrame) -> str:
    """H1 chart: every province as a dot (jittered vertically), regional median as a bar."""
    order = base.groupby("region_en")["vehicles_per_1000"].median().sort_values().index
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for i, reg in enumerate(order):
        y = base.loc[base["region_en"] == reg, "vehicles_per_1000"].values
        ax.scatter(y, np.full(len(y), i) + np.random.default_rng(i).uniform(-0.12, 0.12, len(y)),
                   s=36, color=SEG_COLORS["MCO"], edgecolor=SURFACE, linewidth=1.5, zorder=3)
        ax.plot([np.median(y)] * 2, [i - 0.3, i + 0.3], color=INK, lw=2, zorder=4)
    ax.set_yticks(range(len(order)), order)
    ax.set_xlabel("Vehicles (cars + motorbikes) per 1,000 people, 2025")
    ax.set_title("H1 - Vehicle density differs by region (bar = regional median)")
    ax.grid(axis="y", visible=False)
    return _save(fig, "fig1_density_by_region.png")


def income_scatter(base: pd.DataFrame) -> str:
    """H2 chart: density vs GRDP per capita (log x), coloured by urban share (sequential blues)."""
    fig, ax = plt.subplots(figsize=(7, 4.6))
    sc = ax.scatter(base["grdp_pc_mvnd"], base["vehicles_per_1000"], c=base["urban_share_model"],
                    cmap="Blues", vmin=0, vmax=0.9, s=46, edgecolor=INK2, linewidth=0.5, zorder=3)
    ax.set_xscale("log")
    for _, r in base.nlargest(4, "grdp_pc_mvnd").iterrows():
        ax.annotate(r["province_en"], (r["grdp_pc_mvnd"], r["vehicles_per_1000"]), xytext=(5, 4),
                    textcoords="offset points", fontsize=8, color=INK2)
    cb = fig.colorbar(sc, ax=ax, shrink=0.8)
    cb.set_label("Urban share of population (2024)", color=INK2)
    ax.set_xlabel("GRDP per capita 2025, million VND (log scale)")
    ax.set_ylabel("Vehicles per 1,000 people")
    ax.set_title("H2 - Density tracks urbanisation more than income")
    return _save(fig, "fig2_density_vs_income.png")


def top_provinces(priority: pd.DataFrame, dim: pd.DataFrame, n: int = 15) -> str:
    """Stacked horizontal bars: 2025 demand of the n largest provinces, split by segment."""
    d = priority.merge(dim[["province_code", "province_en"]], on="province_code")
    d = d.nlargest(n, "litres_2025_p50").iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5.4))
    left = np.zeros(len(d))
    for seg, col in [("MCO", "mco_share_2025"), ("PCMO", "pcmo_share_2025"), ("HDMO", "hdmo_share_2025")]:
        w = d[col].values * d["litres_2025_p50"].values / 1e6
        ax.barh(d["province_en"], w, left=left, color=SEG_COLORS[seg], label=SEG_LABEL[seg],
                edgecolor=SURFACE, linewidth=2, height=0.7)
        left += w
    ax.set_xlabel("Lubricant demand potential 2025, million litres (median of 10,000 simulations)")
    ax.set_title(f"Top {n} provinces by demand potential, by segment")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    return _save(fig, "fig3_top_provinces.png")


def national_fan(national: pd.DataFrame) -> str:
    """National total with its 95% band (grey) plus the median of each segment, 2025-2028."""
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    tot = national[national["segment"] == "TOTAL"]
    ax.fill_between(tot["year"], tot["litres_p025"] / 1e6, tot["litres_p975"] / 1e6, color=GRID, label="Total, 95% interval")
    ax.plot(tot["year"], tot["litres_p50"] / 1e6, color=INK, lw=2, label="Total (median)")
    for seg in ["MCO", "PCMO", "HDMO"]:
        s = national[national["segment"] == seg]
        ax.plot(s["year"], s["litres_p50"] / 1e6, color=SEG_COLORS[seg], lw=2, marker="o", ms=5, label=SEG_LABEL[seg])
    ax.set_ylim(0, None)
    ax.set_xticks(tot["year"])
    ax.set_ylabel("Million litres per year")
    ax.set_title("National demand potential and forecast")
    ax.legend(fontsize=8, ncol=2, loc="upper left")
    return _save(fig, "fig4_national_forecast.png")


def sensitivity(sens: pd.DataFrame, n: int = 10) -> str:
    """Tornado-style chart of the n parameters most correlated with the national total."""
    d = sens.head(n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors = [SEG_COLORS["MCO"] if v > 0 else SEG_COLORS["PCMO"] for v in d["spearman_with_total_2025"]]
    ax.barh(d["parameter"], d["spearman_with_total_2025"], color=colors, height=0.6)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_xlabel("Rank correlation with national 2025 demand (across simulations)")
    ax.set_title("Which assumptions drive the uncertainty")
    ax.grid(axis="y", visible=False)
    return _save(fig, "fig5_sensitivity.png")


def triangulation(national: pd.DataFrame, bench: pd.DataFrame) -> str:
    """Model's 2025 total (median + 95% interval) against published third-party estimates."""
    tot = national[(national["segment"] == "TOTAL") & (national["year"] == 2025)].iloc[0]
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.errorbar([tot["litres_p50"] / 1e6], [0], xerr=[[(tot["litres_p50"] - tot["litres_p025"]) / 1e6],
                [(tot["litres_p975"] - tot["litres_p50"]) / 1e6]], fmt="o", color=INK, capsize=4, lw=2, ms=8)
    ax.annotate("This model: road-vehicle lubricants\n(median, 95% interval)", (tot["litres_p50"] / 1e6, 0),
                xytext=(0, 14), textcoords="offset points", ha="center", fontsize=8, color=INK2)
    for i, (_, b) in enumerate(bench.iterrows()):
        y = 1 + i * 0.5
        ax.scatter([b["value_million_litres"]], [y], marker="D", color=SEG_COLORS["PCMO"], s=40, zorder=3)
        ax.annotate(f"{b['publisher']} - {b['benchmark'].replace('_', ' ')} ({b['year']})",
                    (b["value_million_litres"], y), xytext=(8, -3), textcoords="offset points", fontsize=8, color=INK2)
    ax.set_yticks([])
    ax.set_xlim(0, 450)
    ax.set_xlabel("Million litres per year")
    ax.set_title("Triangulation against published market estimates")
    return _save(fig, "fig6_triangulation.png")


def backtest(bt: pd.DataFrame) -> str:
    """Hold-out MAPE of every forecasting method per variable; the selected method in blue."""
    fig, ax = plt.subplots(figsize=(8, 3.4))
    labels, pos, x = [], [], 0.0
    names = {"population_k": "Population", "road_freight_kt": "Road freight"}
    for _, r in bt.iterrows():
        # one bar per candidate method; the method the pipeline selected is highlighted
        for m, key in [("ETS damped", "ets_damped"), ("Drift", "drift"), ("Naive (flat)", "naive")]:
            v = r[f"median_province_mape_{key}"]
            ax.bar(x, v, color=SEG_COLORS["MCO"] if r["chosen_method"] == key else AXIS, width=0.7)
            ax.text(x, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=8, color=INK2)
            labels.append(f"{names.get(r['variable'], r['variable'])}\n{m}")
            pos.append(x)
            x += 1
        x += 0.6
    ax.set_xticks(pos, labels, fontsize=8)
    ax.set_ylabel("Median province MAPE, 2023-2025 hold-out")
    ax.set_title("Forecast back-test (chosen method in blue)")
    ax.grid(axis="x", visible=False)
    return _save(fig, "fig7_backtest.png")


def make_all(base, priority, dim, national, sens, bench, bt_summary) -> list[str]:
    """Render every report figure; returns their paths in a fixed order (used by report.py)."""
    return [density_by_region(base), income_scatter(base), top_provinces(priority, dim),
            national_fan(national), sensitivity(sens), triangulation(national, bench), backtest(bt_summary)]

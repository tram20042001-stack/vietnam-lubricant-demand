"""Extra figures for the technical report (architecture diagram, EDA, model diagnostics).

The pipeline already writes fig1-fig7 to reports/figures/; this adds fig8-fig13.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from vnlube import data_access as da  # noqa: E402
from vnlube import statistics as st  # noqa: E402
from vnlube.figures import AXIS, GRID, INK, INK2, MUTED, SEG_COLORS, SURFACE  # noqa: E402,F401

from .common import FIG, Facts  # noqa: E402


def _save(fig, name):
    path = FIG / name
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path


def architecture() -> object:
    """Pipeline diagram: source -> ingest -> DuckDB layers -> models -> outputs."""
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.set_xlim(0, 11); ax.set_ylim(0, 4.4); ax.axis("off")
    boxes = [
        (0.1, 1.6, 1.7, 1.2, "NSO PX-Web\n14 official tables\n(JSON-stat, UTF-8)", "#eef3fb"),
        (2.2, 1.6, 1.7, 1.2, "Ingest\nretry + TLS fix\nSHA-256 change\ndetection", "#eef3fb"),
        (4.3, 2.55, 1.9, 1.05, "DuckDB staging\n-> clean (SQL)", "#e8f6ef"),
        (4.3, 0.85, 1.9, 1.05, "Marts + dq_* checks\n63->34 roll-up", "#e8f6ef"),
        (6.6, 3.0, 1.9, 0.95, "Hypothesis tests\n+ assumption checks", "#fdeee6"),
        (6.6, 1.75, 1.9, 0.95, "Driver forecasts\n(back-tested)", "#fdeee6"),
        (6.6, 0.5, 1.9, 0.95, "Monte Carlo demand\n10,000 draws", "#fdeee6"),
        (8.9, 2.55, 2.0, 1.05, "Streamlit dashboard\n+ Power BI star schema", "#f3f2ee"),
        (8.9, 0.85, 2.0, 1.05, "findings.md, figures,\nprofiling reports", "#f3f2ee"),
    ]
    for x, y, w, h, txt, col in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.12",
                                    fc=col, ec=AXIS, lw=1))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=8.6, color=INK)

    def arrow(x0, y0, x1, y1):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12, color=INK2, lw=1.2))
    arrow(1.8, 2.2, 2.2, 2.2)
    arrow(3.9, 2.4, 4.3, 3.05); arrow(3.9, 2.0, 4.3, 1.4)
    arrow(5.25, 2.55, 5.25, 1.9)
    for y in (3.45, 2.2, 0.95):
        arrow(6.2, 1.4, 6.6, y)
    for y0 in (3.45, 2.2, 0.95):
        arrow(8.5, y0, 8.9, 3.05 if y0 > 2 else 1.4)
    ax.text(5.5, 4.2, "Weekly scheduled task: rebuild only when NSO publishes new data", ha="center",
            fontsize=9, color=INK2, style="italic")
    ax.text(0.95, 1.35, "data/raw/*.json + *.csv\nmanifest.csv", ha="center", va="top", fontsize=7.5, color=MUTED)
    ax.text(5.25, 0.6, "data/warehouse.duckdb", ha="center", va="top", fontsize=7.5, color=MUTED)
    return _save(fig, "fig8_architecture.png")


def eda_trends(f: Facts):
    py, prod = f.tables["py"], f.tables["prod"]
    nat = py.groupby("year")[["road_freight_kt"]].sum()
    p = prod[prod["year"] >= 2005]
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.4))
    ax[0].plot(nat.index, nat["road_freight_kt"] / 1000, marker="o", ms=4, color=SEG_COLORS["HDMO"], lw=2)
    ax[0].set_title("Road freight carried, million tonnes"); ax[0].set_ylim(0, None)
    ax[1].plot(p["year"], p["motorbikes_assembled_k"], marker="o", ms=4, color=SEG_COLORS["MCO"], lw=2, label="Motorbikes")
    ax[1].plot(p["year"], p["cars_assembled_k"] * 10, marker="o", ms=4, color=SEG_COLORS["PCMO"], lw=2, label="Cars (x10)")
    ax[1].set_title("Vehicles assembled per year, thousand"); ax[1].set_ylim(0, None); ax[1].legend(fontsize=8)
    for a in ax:   # whole-year ticks (no "2005.0")
        a.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    fig.tight_layout()
    return _save(fig, "fig9_eda_trends.png")


def corr_heatmap(f: Facts):
    v = f.tables["veh"].rename(columns={"vehicles_per_1000": "density", "grdp_pc_mvnd": "GRDP pc",
                                        "urban_share": "urban share", "road_freight_kt": "freight",
                                        "accidents_per_10k": "accident rate", "population_k": "population"})
    cols = ["density", "GRDP pc", "urban share", "freight", "population", "accident rate"]
    c = v[cols].corr(method="spearman")
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    im = ax.imshow(c, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), cols, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(cols)), cols, fontsize=8)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{c.iloc[i, j]:.2f}", ha="center", va="center", fontsize=7.5,
                    color="white" if abs(c.iloc[i, j]) > 0.6 else INK)
    ax.grid(False); fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Spearman correlations, 34 provinces (2025)", fontsize=10)
    return _save(fig, "fig10_correlations.png")


def inverted_u():
    base = da.province_base()
    _, _, d = st.h2_design(base)
    d = d.assign(log_grdp_sq=d["log_grdp"] ** 2)
    m = sm.OLS(d["log_density"], sm.add_constant(d[["log_grdp", "log_grdp_sq", "urban_share_model"]])).fit()
    nl = st.h2_nonlinear(base)
    g = np.linspace(d["log_grdp"].min(), d["log_grdp"].max(), 100)
    pred = m.params["const"] + m.params["log_grdp"] * g + m.params["log_grdp_sq"] * g ** 2 \
        + m.params["urban_share_model"] * d["urban_share_model"].mean()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.scatter(d["grdp_pc_mvnd"], d["vehicles_per_1000"], color=SEG_COLORS["MCO"], s=30, label="province")
    ax.plot(np.exp(g), np.exp(pred), color=INK, lw=2, label="quadratic fit (mean urban share)")
    ax.axvline(nl["turning_point_grdp_pc"], color=INK2, ls="--", lw=1)
    ax.text(nl["turning_point_grdp_pc"] * 1.03, ax.get_ylim()[0] + 30, f"turning point\n~{nl['turning_point_grdp_pc']:.0f} M VND",
            fontsize=8, color=INK2)
    ax.set_xscale("log"); ax.set_xlabel("GRDP per capita 2025, million VND (log)"); ax.set_ylabel("vehicles per 1,000 people")
    ax.set_xticks([50, 75, 100, 150, 200, 250], ["50", "75", "100", "150", "200", "250"])   # plain numbers, not 10^x
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("Vehicle density vs income: inverted U (exploratory)")
    return _save(fig, "fig11_inverted_u.png")


def baseline_diff(f: Facts):
    s = f.tables["bcmp"].sort_values("diff_vs_population_share_pct")
    fig, ax = plt.subplots(figsize=(7.5, 6.6))
    ax.barh(s["province_en"], s["diff_vs_population_share_pct"],
            color=[SEG_COLORS["MCO"] if v > 0 else SEG_COLORS["PCMO"] for v in s["diff_vs_population_share_pct"]])
    ax.axvline(0, color=INK2, lw=1)
    ax.set_xlabel("Model vs population-share rule of thumb, 2025 (%)")
    ax.set_title("Where the rule of thumb under-estimates (blue) or over-estimates (orange)", fontsize=10)
    ax.tick_params(axis="y", labelsize=7.5)
    return _save(fig, "fig12_baseline_diff.png")


def priority_matrix(f: Facts):
    p = f.tables["pri"]
    colors = {"A": SEG_COLORS["MCO"], "B": SEG_COLORS["PCMO"], "C": "#9a9890"}
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    for tier in ["C", "B", "A"]:
        q = p[p["tier"] == tier]
        ax.scatter(q["litres_2025_p50"] / 1e6, q["increment_2025_2028_p50"] / 1e6, s=50, color=colors[tier],
                   edgecolor="white", lw=1.5, label=f"Tier {tier}", zorder=3)
    for _, r in p[p["tier"] == "A"].nlargest(5, "litres_2025_p50").iterrows():   # label the 5 largest only
        ax.annotate(r["province_en"], (r["litres_2025_p50"] / 1e6, r["increment_2025_2028_p50"] / 1e6),
                    xytext=(5, 3), textcoords="offset points", fontsize=7.5, color=INK2)
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 5, 10, 20, 40], ["1", "2", "5", "10", "20", "40"])
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlabel("Demand potential 2025, million litres (log)"); ax.set_ylabel("Added litres 2025->2028, million")
    ax.set_title("Priority matrix: market size vs growth"); ax.legend(fontsize=8)
    return _save(fig, "fig13_priority_matrix.png")


def make_all(f: Facts) -> dict:
    return {"architecture": architecture(), "eda_trends": eda_trends(f), "corr": corr_heatmap(f),
            "inverted_u": inverted_u(), "baseline": baseline_diff(f), "priority": priority_matrix(f)}

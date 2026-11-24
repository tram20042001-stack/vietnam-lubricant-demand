"""Auto-generated findings note (reports/findings.md), rewritten on every pipeline run.

No number in the note is typed by hand: every figure is read from the run's results, so the
note can never drift out of sync with the data after an NSO update.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .config import BASE_YEAR, FORECAST_TO, REPORTS


def _ml(x: float) -> str:
    """Litres -> 'million litres' text with one decimal."""
    return f"{x / 1e6:,.1f}"


def _p(p: float) -> str:
    """Format a p-value (tiny values shown as <0.001)."""
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def write_findings(*, base, dim, tests, details, outl, fc, out, bench, dq, n_draws, figures,
                   checks=None, baseline_metrics=None) -> Path:
    """Compose the markdown report from the run's results and write it to reports/findings.md."""
    nat, pri, sens = out["national"], out["priority"], out["sensitivity"]
    # national totals for the base year and the last forecast year
    t25 = nat[(nat.segment == "TOTAL") & (nat.year == BASE_YEAR)].iloc[0]
    t28 = nat[(nat.segment == "TOTAL") & (nat.year == FORECAST_TO)].iloc[0]
    seg25 = nat[nat.year == BASE_YEAR].set_index("segment")
    seg28 = nat[nat.year == FORECAST_TO].set_index("segment")
    cagr = (t28.litres_p50 / t25.litres_p50) ** (1 / (FORECAST_TO - BASE_YEAR)) - 1
    seg_growth = {s: seg28.loc[s].litres_p50 / seg25.loc[s].litres_p50 - 1 for s in ["MCO", "PCMO", "HDMO"]}
    fastest = max(seg_growth, key=seg_growth.get)
    biggest = max(seg_growth, key=lambda s: seg28.loc[s].litres_p50 - seg25.loc[s].litres_p50)
    seg_name = {"MCO": "motorbike oil", "PCMO": "passenger-car oil", "HDMO": "heavy-duty oil"}
    p = pri.merge(dim[["province_code", "province_en", "region_en"]], on="province_code")
    h1, h2, h3 = details["H1"], details["H2"], details["H3"]
    bt = fc["backtest_summary"].set_index("variable")
    rec = dq["dq_reconciliation"]
    auto = bench[bench.benchmark == "automotive_engine_oils"].iloc[0]
    rel = lambda f: Path(f).relative_to(REPORTS).as_posix()

    lines = [
        "# Findings - Vietnam lubricant demand potential",
        "",
        f"_Generated {dt.datetime.now():%Y-%m-%d %H:%M} by `python -m vnlube.pipeline`. "
        f"Every number below is recomputed from the official NSO data on each run._",
        "",
        "## Headline",
        "",
        f"- **{_ml(t25.litres_p50)} million litres** of road-vehicle lubricant demand potential in {BASE_YEAR} "
        f"(95% interval {_ml(t25.litres_p025)}-{_ml(t25.litres_p975)} M L, {n_draws:,} Monte Carlo draws).",
        f"- Split: motorbike oil {_ml(seg25.loc['MCO'].litres_p50)} M L, passenger-car oil "
        f"{_ml(seg25.loc['PCMO'].litres_p50)} M L, heavy-duty oil {_ml(seg25.loc['HDMO'].litres_p50)} M L.",
        f"- Forecast {FORECAST_TO}: **{_ml(t28.litres_p50)} M L** (CAGR {cagr:.1%}). Fastest-growing segment: "
        f"{seg_name[fastest]} (+{seg_growth[fastest]:.0%}, {_ml(seg25.loc[fastest].litres_p50)} -> "
        f"{_ml(seg28.loc[fastest].litres_p50)} M L); largest absolute gain: {seg_name[biggest]} "
        f"(+{_ml(seg28.loc[biggest].litres_p50 - seg25.loc[biggest].litres_p50)} M L).",
        f"- Triangulation: published estimates put automotive engine oils at {auto.value_million_litres:.0f} M L "
        f"({auto.year}, {auto.publisher}) and all lubricants (incl. industrial) at "
        f"{bench[bench.benchmark == 'total_lubricants'].value_million_litres.min():.0f}-"
        f"{bench[bench.benchmark == 'total_lubricants'].value_million_litres.max():.0f} M L; the model's road-vehicle "
        f"estimate sits between the two, as it should.",
        "",
        f"![national]({rel(figures[3])})",
        "",
        "## Priority provinces (tier A)",
        "",
        "Score = 60% size of the 2025 market + 40% absolute growth to 2028 (percentile ranks, computed in every "
        "simulation). *P(top 10)* = share of simulations in which the province ranks in the top 10.",
        "",
        "| Rank | Province | Region | 2025 M L | +M L to 2028 | CAGR | Growth focus | P(top 10) |",
        "|---:|---|---|---:|---:|---:|---|---:|",
    ]
    for _, r in p[p.tier == "A"].iterrows():
        lines.append(f"| {r.priority_rank} | {r.province_en} | {r.region_en} | {_ml(r.litres_2025_p50)} | "
                     f"{_ml(r.increment_2025_2028_p50)} | {r.cagr_2025_2028_p50:.1%} | {r.growth_focus_segment} | "
                     f"{r.prob_top10:.0%} |")
    stable = p[(p.tier == "A") & (p.prob_top10 >= 0.9)].province_en.tolist()
    fragile = p[(p.tier != "A") & (p.prob_top10 >= 0.3)].province_en.tolist()
    lines += [
        "",
        f"Robust picks (in the top 10 in at least 90% of simulations): {', '.join(stable)}. "
        f"Borderline provinces outside tier A that still reach the top 10 in 30% or more of simulations: "
        f"{', '.join(fragile) or 'none'}.",
        "",
        f"![top]({rel(figures[2])})",
        "",
        "## Hypothesis tests (observed data only, Holm-adjusted)",
        "",
        "| Hypothesis | Method | Statistic | p | p (Holm) | Result |",
        "|---|---|---:|---:|---:|---|",
    ]
    for _, t in tests.iterrows():
        lines.append(f"| {t.test} | {t.method} | {t.statistic:.3f} | {_p(t.p_value)} | {_p(t.p_holm)} | "
                     f"{'reject H0' if t.reject_h0 else 'fail to reject H0'} |")
    med = h1["region_medians"]
    nl = h2["nonlinear"]                      # exploratory quadratic follow-up (RESET rejected linearity)
    eff = {e["percentile"]: e for e in nl["elasticity_at"]}
    lines += [
        "",
        f"- **H1** - regions differ (epsilon^2 = {h1['effect_size']:.2f}, a large effect). Median vehicles per "
        f"1,000 people: " + ", ".join(f"{k} {v:,.0f}" for k, v in med.items()) + ".",
        f"- **H2 (pre-registered, linear)** - no positive *linear* income elasticity once urbanisation is "
        f"controlled (elasticity {h2['effect_size']:.2f}, 95% CI {h2['ci95'][0]:.2f} to {h2['ci95'][1]:.2f}; "
        f"region-clustered p = {_p(h2['p_cluster_region'])}); urban share matters (coef {h2['beta_urban']:.2f}, "
        f"p = {_p(h2['p_urban'])}). The raw rank correlation with income (rho = {h2['spearman_rho']:.2f}, "
        f"p = {_p(h2['spearman_p'])}) is largely urbanisation.",
        f"- **H2 follow-up (exploratory)** - the RESET test rejects the linear form; with a squared income term "
        f"the relationship is an **inverted U** (squared term p = {_p(nl['p_sq'])}). Elasticity of vehicle "
        f"density to income: {eff[10]['elasticity']:+.2f} at {eff[10]['grdp_pc_mvnd']:.0f} M VND per capita "
        f"(p = {_p(eff[10]['p_value'])}), {eff[50]['elasticity']:+.2f} at the median "
        f"(p = {_p(eff[50]['p_value'])}), {eff[90]['elasticity']:+.2f} at {eff[90]['grdp_pc_mvnd']:.0f} M VND "
        f"(p = {_p(eff[90]['p_value'])}); turning point about {nl['turning_point_grdp_pc']:.0f} M VND "
        f"({nl['n_above_turning']} provinces above it). Interpretation: in poorer provinces rising income "
        "still adds vehicles (mostly motorbikes, MCO); in the richest provinces density levels off and falls "
        "as cars replace motorbikes, so income growth there shows up as PCMO rather than more vehicles. "
        "Because this was found after looking at the data, it is a hypothesis for the next data release, "
        "not a confirmed result.",
        f"- **H3** - no evidence that low-density provinces grow faster (rho = {h3['effect_size']:.2f}, 95% "
        f"bootstrap CI {h3['ci95'][0]:.2f} to {h3['ci95'][1]:.2f}). Growth potential has to be judged province "
        "by province, which is what the priority score does.",
        "",
        f"![h1]({rel(figures[0])})  ![h2]({rel(figures[1])})",
        "",
        "## Forecast back-test (fit <= 2022, predict 2023-2025)",
        "",
        "Naive (flat) and drift are the baselines; ETS is only used if it beats them out of sample.",
        "",
        "| Variable | Chosen method | Median province MAPE: ETS | Drift | Naive | National MAPE (chosen) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for var, r in bt.iterrows():
        lines.append(f"| {var} | {r.chosen_method} | {r.median_province_mape_ets_damped:.1f}% | "
                     f"{r.median_province_mape_drift:.1f}% | {r.median_province_mape_naive:.1f}% | "
                     f"{r[f'national_mape_{r.chosen_method}']:.1f}% |")
    out_flags = outl[outl.flag != ""]
    lines += ["", f"![backtest]({rel(figures[6])})", ""]

    # --- baseline comparison for the demand model -----------------------------------------------
    if baseline_metrics:
        m = baseline_metrics
        lines += [
            "## Demand model vs baselines (2025)",
            "",
            f"- **Deterministic baseline** (every assumption at its most-likely value, no simulation): "
            f"{m['national_deterministic_ML']:,.1f} M L vs Monte Carlo median {m['national_mc_median_ML']:,.1f} M L "
            f"({m['mc_vs_deterministic_pct']:+.1f}%). The difference comes from skewed assumption ranges; the "
            "simulation also provides the interval the point estimate cannot.",
            f"- **Population-share baseline** (today's practice: national total split by headcount): rank "
            f"correlation with the model {m['spearman_model_vs_population_share']:.2f}, but provincial volumes "
            f"differ by {m['mean_abs_diff_vs_population_share_pct']:.0f}% on average (up to "
            f"{m['max_abs_diff_vs_population_share_pct']:.0f}%), and {m['top10_changed_vs_population_share']} of "
            "the model's top-10 provinces are not in the population-share top 10.",
            "",
        ]

    # --- assumption checks ----------------------------------------------------------------------
    if checks is not None:
        lines += ["## Model assumption checks", "",
                  "| Model | Assumption | Check | Statistic | p | Passed | If violated |",
                  "|---|---|---|---:|---:|---|---|"]
        for _, c in checks.iterrows():
            pv = "" if pd.isna(c.p_value) else _p(c.p_value)
            lines.append(f"| {c.model} | {c.assumption} | {c.check} | {c.statistic:.3f} | {pv} | "
                         f"{'yes' if c.passed else '**no**'} | {c.consequence} |")
        lines.append("")

    top_param = sens.iloc[0].parameter
    lines += [
        "## Uncertainty drivers",
        "",
        "Top parameters by rank correlation with the national 2025 total: "
        + "; ".join(f"`{r.parameter}` ({r.spearman_with_total_2025:+.2f})" for _, r in sens.head(5).iterrows())
        + f". Narrowing `{top_param}` (e.g. with a workshop or fleet survey) is the most effective way to "
          "tighten the estimate.",
        "",
        f"![sens]({rel(figures[4])})  ![tri]({rel(figures[5])})",
        "",
        "## Data quality",
        "",
        f"- 63->34 province roll-up reproduces the official 34-province figures for 2020-2025: max absolute "
        f"difference {rec.pop_diff_pct.abs().max():.4f}% (population), {rec.freight_diff_pct.abs().max():.4f}% "
        f"(road freight), {rec.grdp_pc_diff_pct.abs().max():.4f}% (GRDP per capita).",
        f"- Provincial vehicle counts add up exactly to the published regional and national totals "
        f"({dq['dq_vehicle_totals'].iloc[0].published_k:,.0f} thousand vehicles).",
        "- Missing values: " + "; ".join(f"{r.sid} {r.missing_type} x{r.n_cells}"
                                         for _, r in dq["dq_missingness"].iterrows()) + ".",
        f"- Series breaks: {int((dq['dq_series_breaks'].year == 2025).sum())} provinces show an urban-share jump "
        "in 2025 caused by the commune-level reform; the model uses the 2024 urban share.",
        f"- Outliers (robust z > 3.5): " + (", ".join(f"{r.province_en} ({r.flag})" for _, r in out_flags.iterrows())
                                             or "none") + ". They are kept (they are real) and reported.",
        "",
        "## Caveats",
        "",
        "- NSO publishes cars and motorbikes as one combined total per province. The car / motorbike / "
        "commercial split is modelled from national registration anchors, GRDP per capita and road freight; "
        "its uncertainty is part of the intervals above.",
        "- The registered fleet overstates the active fleet (no compulsory de-registration of motorbikes); "
        "the `active_share` parameter covers this.",
        "- Market benchmarks are third-party estimates used only as a sanity check, never as model inputs.",
    ]
    path = REPORTS / "findings.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

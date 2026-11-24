"""Monte Carlo lubricant demand model (litres per year) by province x segment x year.

Fleet (2025)
    V_p (official, cars + motorbikes) is split into passenger cars (PC), commercial
    vehicles (CV) and motorbikes (MC):
      PC_p = C * s_pass * w_p / sum(w),            w_p = V_p * (GRDPpc_p / GRDPpc_nat)^eps
      CV_p = C * (1 - s_pass) * [a * F_p / sum(F) + (1 - a) * w_p / sum(w)]   (F = road freight)
      MC_p = V_p - PC_p - CV_p
Demand
    L_{p,s} = fleet_{p,s} * active_s * (annual_km_s / drain_interval_s) * fill_s * other_fluids_s
    MCO <- MC, PCMO <- PC, HDMO <- CV
Forecast (2026-2028)
    MC grows with population and real GRDP per capita^eta_mc, PC with population and
    real GRDP per capita^eta_car, CV with forecast road freight^eta_cv.
Every assumption is drawn from its triangular range in each of N draws, so the output
intervals reflect parameter uncertainty (national parameters are shared by all
provinces within a draw, which keeps provincial results consistent with each other).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import BASE_YEAR, FORECAST_TO

SEGMENTS = ["MCO", "PCMO", "HDMO"]                 # index 0, 1, 2 in every segment axis below
YEARS = list(range(BASE_YEAR, FORECAST_TO + 1))    # 2025 (base, observed fleet) .. 2028


def _tri(rng, row, n) -> np.ndarray:
    """Sample n values from a triangular(low, mode, high) distribution.

    Triangular is used because each assumption is elicited as min / most-likely / max; a range
    with low == high (e.g. in the deterministic baseline) returns the constant mode.
    """
    lo, mode, hi = float(row["low"]), float(row["mode"]), float(row["high"])
    return rng.triangular(lo, mode, hi, n) if hi > lo else np.full(n, mode)


def draw_parameters(lube: pd.DataFrame, split: pd.DataFrame, n: int, seed: int = 2025) -> dict[str, np.ndarray]:
    """Draw n samples of every assumption. A fixed seed makes every run reproducible.

    Keys: fleet-split parameters by name (e.g. ``national_cars_2025``) and lubricant
    parameters as ``<segment>.<parameter>`` (e.g. ``MCO.drain_interval_km``).
    Parameters are drawn independently (no assumed correlation between them).
    """
    rng = np.random.default_rng(seed)
    p = {}
    for _, r in split.iterrows():
        p[r["parameter"]] = _tri(rng, r, n)
    for _, r in lube.iterrows():
        p[f"{r['segment']}.{r['parameter']}"] = _tri(rng, r, n)
    return p


@dataclass
class McResult:
    """Raw simulation output (kept in memory; ~35 MB for 10,000 draws)."""
    draws: np.ndarray            # shape (n, provinces, segments, years) litres
    fleet: np.ndarray            # shape (n, provinces, segments, years) vehicles (registered)
    params: dict[str, np.ndarray]
    provinces: list[str]


def simulate(base: pd.DataFrame, drivers: pd.DataFrame, growth: pd.DataFrame,
             lube: pd.DataFrame, split: pd.DataFrame, n: int = 10_000, seed: int = 2025) -> McResult:
    """Run the Monte Carlo. All arrays are vectorised over draws (n) and provinces (P).

    Array shapes used below: (n, P) per draw and province; (P, Y) per province and year;
    final arrays (n, P, 3 segments, Y years).
    """
    base = base.sort_values("province_code").reset_index(drop=True)
    codes = base["province_code"].tolist()
    P = len(codes)
    prm = draw_parameters(lube, split, n, seed)          # dict: parameter name -> n sampled values

    # --- observed inputs (official NSO data, 2025) --------------------------------------------
    V = base["vehicles_k"].to_numpy() * 1000.0           # registered cars + motorbikes
    pop25 = base["population_k"].to_numpy()
    g = base["grdp_pc_mvnd"].to_numpy()                  # GRDP per capita, million VND
    g_nat = np.sum(g * pop25) / pop25.sum()              # population-weighted national GRDP per capita
    F = base["road_freight_kt"].to_numpy()               # road freight, thousand tonnes

    # --- 1. split each province's combined count into PC / CV / MC ------------------------------
    # Richer provinces own proportionally more cars: weight = vehicles x relative income ^ elasticity
    eps = prm["car_income_elasticity"][:, None]
    w = V[None, :] * (g[None, :] / g_nat) ** eps                      # (n, P)
    w_share = w / w.sum(axis=1, keepdims=True)                        # each draw's shares sum to 1
    C = prm["national_cars_2025"][:, None]                            # national car total in this draw
    s_pass = prm["passenger_share_of_cars"][:, None]
    a = prm["commercial_freight_weight"][:, None]
    PC = C * s_pass * w_share                                         # passenger cars follow the car weight
    # commercial vehicles follow a blend of road-freight share and the car weight
    CV = C * (1 - s_pass) * (a * (F / F.sum())[None, :] + (1 - a) * w_share)
    MC = V[None, :] - PC - CV                                         # the rest are motorbikes
    if (MC <= 0).any():                                               # guard: the split must stay feasible
        raise ValueError("car allocation exceeds total vehicles in some province/draw")

    # --- 2. grow each fleet to 2026-2028 --------------------------------------------------------
    drv = drivers.pivot(index="province_code", columns="year")
    pop_ratio = (drv["population_k"].loc[codes, YEARS].to_numpy() / pop25[:, None])          # (P, Y), 1.0 in 2025
    fr_ratio = drv["road_freight_kt"].loc[codes, YEARS].to_numpy() / F[:, None]              # (P, Y)
    r = growth.set_index("province_code").loc[codes, "real_gdp_pc_growth"].to_numpy()
    t = np.array(YEARS) - BASE_YEAR                                   # 0, 1, 2, 3
    inc = (1 + r[:, None]) ** t[None, :]                              # cumulative real income factor (P, Y)

    eta_mc = prm["moto_density_income_elasticity"][:, None, None]     # ~0: motorbikes near saturation
    eta_car = prm["car_density_income_elasticity"][:, None, None]     # >1: cars respond strongly to income
    eta_cv = prm["commercial_freight_elasticity"][:, None, None]
    fleet = np.empty((n, P, 3, len(YEARS)))
    fleet[:, :, 0, :] = MC[:, :, None] * pop_ratio[None] * inc[None] ** eta_mc
    fleet[:, :, 1, :] = PC[:, :, None] * pop_ratio[None] * inc[None] ** eta_car
    fleet[:, :, 2, :] = CV[:, :, None] * fr_ratio[None] ** eta_cv

    # --- 3. litres per vehicle per year = active x oil changes per year x litres per change x top-ups
    litres_per_vehicle = np.stack([
        prm[f"{s}.active_share"] * prm[f"{s}.annual_km"] / prm[f"{s}.drain_interval_km"]
        * prm[f"{s}.fill_litres"] * prm[f"{s}.other_fluids_factor"] for s in SEGMENTS], axis=1)  # (n, 3)
    draws = fleet * litres_per_vehicle[:, None, :, None]              # broadcast over provinces and years
    return McResult(draws=draws, fleet=fleet, params=prm, provinces=codes)


# ----------------------------------------------------------------------------- baselines
def _modes_only(table: pd.DataFrame) -> pd.DataFrame:
    """Collapse every triangular range to its most-likely value (low = high = mode)."""
    return table.assign(low=table["mode"], high=table["mode"])


def deterministic_baseline(base, drivers, growth, lube, split) -> pd.DataFrame:
    """Baseline 1 - the same model run ONCE with every assumption at its most-likely value.

    This is what a spreadsheet would give: a single number with no uncertainty. Comparing it with
    the Monte Carlo median shows how much the non-linear model shifts the central estimate.
    """
    res = simulate(base, drivers, growth, _modes_only(lube), _modes_only(split), n=1, seed=0)
    rows = [{"province_code": c, "segment": s, "year": y, "litres": res.draws[0, i, k, j]}
            for i, c in enumerate(res.provinces) for k, s in enumerate(SEGMENTS) for j, y in enumerate(YEARS)]
    return pd.DataFrame(rows)


def population_share_baseline(base: pd.DataFrame, national_litres: float) -> pd.DataFrame:
    """Baseline 2 - the current top-down practice: split a national total by population share.

    It ignores how vehicle ownership, income and freight differ between provinces, which is
    exactly the gap the model is meant to close.
    """
    share = base["population_k"] / base["population_k"].sum()
    return pd.DataFrame({"province_code": base["province_code"], "litres": national_litres * share.values})


def compare_baselines(base, drivers, growth, lube, split, summary: dict) -> tuple[pd.DataFrame, dict]:
    """Compare the Monte Carlo model with both baselines for 2025, province by province.

    The population-share baseline gets the model's own national median so that ONLY the
    provincial allocation differs; any difference in ranking is due to the model's use of
    vehicles, income and freight instead of headcount.
    """
    from scipy import stats   # local import: only needed here

    mc = (summary["demand"].query("year == @BASE_YEAR").groupby("province_code")["litres_p50"].sum()
          .rename("model_mc_p50"))
    det = (deterministic_baseline(base, drivers, growth, lube, split).query("year == @BASE_YEAR")
           .groupby("province_code")["litres"].sum().rename("baseline_deterministic"))
    nat = summary["national"].query("segment == 'TOTAL' and year == @BASE_YEAR")["litres_p50"].iloc[0]
    pop = population_share_baseline(base, nat).set_index("province_code")["litres"].rename("baseline_population_share")
    cmp = pd.concat([mc, det, pop], axis=1).reset_index()
    for col in ["model_mc_p50", "baseline_population_share"]:
        cmp[f"rank_{col}"] = cmp[col].rank(ascending=False).astype(int)
    cmp["diff_vs_population_share_pct"] = 100 * (cmp["model_mc_p50"] / cmp["baseline_population_share"] - 1)

    top_model = set(cmp.nsmallest(10, "rank_model_mc_p50")["province_code"])
    top_pop = set(cmp.nsmallest(10, "rank_baseline_population_share")["province_code"])
    metrics = {
        "national_mc_median_ML": nat / 1e6,
        "national_deterministic_ML": cmp["baseline_deterministic"].sum() / 1e6,
        "mc_vs_deterministic_pct": 100 * (nat / cmp["baseline_deterministic"].sum() - 1),
        "spearman_model_vs_population_share": stats.spearmanr(cmp["model_mc_p50"], cmp["baseline_population_share"])[0],
        "mean_abs_diff_vs_population_share_pct": cmp["diff_vs_population_share_pct"].abs().mean(),
        "max_abs_diff_vs_population_share_pct": cmp["diff_vs_population_share_pct"].abs().max(),
        "top10_changed_vs_population_share": len(top_model - top_pop),
    }
    return cmp, metrics


def summarise(res: McResult, base: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Turn the raw draws into report tables.

    Returns demand (province x segment x year percentiles), national (segment x year),
    priority (province ranking with P(top 10)) and sensitivity (parameter importance).
    """
    q = [2.5, 10, 50, 90, 97.5]               # percentiles kept: 95% and 80% intervals plus the median
    d = res.draws
    rows = []
    for i, code in enumerate(res.provinces):
        for s, seg in enumerate(SEGMENTS):
            for y, year in enumerate(YEARS):
                x = d[:, i, s, y]
                f = res.fleet[:, i, s, y]
                pct = np.percentile(x, q)
                rows.append({"province_code": code, "segment": seg, "year": year,
                             "litres_mean": x.mean(), "litres_p025": pct[0], "litres_p10": pct[1],
                             "litres_p50": pct[2], "litres_p90": pct[3], "litres_p975": pct[4],
                             "fleet_registered_p50": np.median(f)})
    demand = pd.DataFrame(rows)

    nat = d.sum(axis=1)                       # (n, 3, Y)
    nat_rows = []
    for y, year in enumerate(YEARS):
        for s, seg in enumerate(SEGMENTS + ["TOTAL"]):
            x = nat[:, s, y] if seg != "TOTAL" else nat[:, :, y].sum(axis=1)
            pct = np.percentile(x, q)
            nat_rows.append({"segment": seg, "year": year, "litres_mean": x.mean(), "litres_p025": pct[0],
                             "litres_p50": pct[2], "litres_p975": pct[4]})
    national = pd.DataFrame(nat_rows)

    # priority score per draw: 60% size of 2025 market, 40% absolute growth 2025->2028.
    # Ranking inside every draw (not on the medians) lets us measure how stable each ranking is.
    tot = d.sum(axis=2)                                         # all segments together: (n, P, Y)
    size, incr = tot[:, :, 0], tot[:, :, -1] - tot[:, :, 0]
    # double argsort turns values into ranks 0..P-1 per draw; dividing gives a percentile rank 0..1
    rank = lambda m: m.argsort(axis=1).argsort(axis=1) / (m.shape[1] - 1)
    score = 0.6 * rank(size) + 0.4 * rank(incr)
    top10 = (score.argsort(axis=1).argsort(axis=1) >= score.shape[1] - 10)   # True where in this draw's top 10
    seg_incr = np.median(d[:, :, :, -1] - d[:, :, :, 0], axis=0)  # median added litres per segment (P, 3)
    pri = pd.DataFrame({
        "province_code": res.provinces,
        "litres_2025_p50": np.median(size, axis=0),
        "litres_2028_p50": np.median(tot[:, :, -1], axis=0),
        "increment_2025_2028_p50": np.median(incr, axis=0),
        "cagr_2025_2028_p50": np.median((tot[:, :, -1] / size) ** (1 / (len(YEARS) - 1)) - 1, axis=0),
        "priority_score_p50": np.median(score, axis=0),
        "prob_top10": top10.mean(axis=0),
        "growth_focus_segment": [SEGMENTS[k] for k in seg_incr.argmax(axis=1)],
        "mco_share_2025": np.median(d[:, :, 0, 0] / size, axis=0),
        "pcmo_share_2025": np.median(d[:, :, 1, 0] / size, axis=0),
        "hdmo_share_2025": np.median(d[:, :, 2, 0] / size, axis=0),
    }).merge(base[["province_code", "population_k"]], on="province_code")
    pri["litres_per_capita_2025"] = pri["litres_2025_p50"] / (pri["population_k"] * 1000)
    pri = pri.sort_values("priority_score_p50", ascending=False).reset_index(drop=True)
    pri["priority_rank"] = np.arange(1, len(pri) + 1)
    # tiers: A = top 10 (focus), B = next 12 (develop), C = rest (maintain)
    pri["tier"] = np.select([pri["priority_rank"] <= 10, pri["priority_rank"] <= 22], ["A", "B"], "C")

    # sensitivity: rank correlation of each sampled parameter with the national 2025 total.
    # A large |rho| means narrowing that assumption would narrow the overall interval the most.
    total25 = nat[:, :, 0].sum(axis=1)
    sens = pd.DataFrame({
        "parameter": list(res.params),
        "spearman_with_total_2025": [pd.Series(v).corr(pd.Series(total25), method="spearman")
                                     for v in res.params.values()],
    })
    sens["abs"] = sens["spearman_with_total_2025"].abs()
    sens = sens.sort_values("abs", ascending=False).drop(columns="abs").reset_index(drop=True)
    return {"demand": demand, "national": national, "priority": pri, "sensitivity": sens}

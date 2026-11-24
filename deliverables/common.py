"""Shared data + metrics for the technical report and the executive deck.

Headline numbers in both deliverables are read from the pipeline outputs in dashboard/data/ (a few narrative values, e.g. test statistics quoted in prose, mirror reports/findings.md)
(run `python -m vnlube.pipeline --offline` first), so the documents stay consistent with the
code and can be regenerated after each NSO release.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboard" / "data"
FIG = ROOT / "reports" / "figures"
OUT = ROOT / "deliverables"
REPO_URL = "https://github.com/tram20042001-stack/vietnam-lubricant-demand"
AUTHOR = "tram20042001-stack"
PROGRAM = "upGrad Bring Your Own Capstone - Data Analytics track"

# Indicative market value per litre, derived from published 2025 value and volume estimates:
# value USD 593.7 M (IMARC) to USD 620 M (Ken Research); volume 321-380 M L (EMR, Mordor, L&G).
# 593.7 / 380.2 = 1.56 USD/L and 620 / 321 = 1.93 USD/L -> midpoint used, range reported.
USD_PER_LITRE = (1.56, 1.75, 1.93)

# Manual refresh effort before the project (from the proposal): ~2 working days per release;
# NSO publishes the provincial yearbook tables several times a year (preliminary -> official).
MANUAL_HOURS_PER_REFRESH = 16
RELEASES_PER_YEAR = 4

SEG_NAME = {"MCO": "Motorbike oil (MCO)", "PCMO": "Passenger-car oil (PCMO)", "HDMO": "Heavy-duty oil (HDMO)"}
SEG_COLOR = {"MCO": "#2a78d6", "PCMO": "#eb6834", "HDMO": "#1baf7a"}


def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{name}.csv", encoding="utf-8-sig")


@dataclass
class Facts:
    """Everything the documents need, computed once."""
    t: dict = field(default_factory=dict)          # scalar facts (numbers, strings)
    tables: dict = field(default_factory=dict)     # DataFrames


def load() -> Facts:
    f = Facts()
    dim = _csv("dim_province")
    nat = _csv("national_demand")
    pri = _csv("priority").merge(dim[["province_code", "province_en", "region_en"]], on="province_code")
    veh = _csv("fact_vehicles_2025").merge(dim[["province_code", "province_en", "region_en"]], on="province_code")
    tests = _csv("hypothesis_tests")
    checks = _csv("assumption_checks")
    bt = _csv("backtest_summary")
    sens = _csv("sensitivity")
    bmet = _csv("baseline_metrics").iloc[0].to_dict()
    bcmp = _csv("baseline_comparison").merge(dim[["province_code", "province_en"]], on="province_code")
    bench = _csv("market_benchmarks")
    py = _csv("fact_province_year")
    prod = _csv("national_production")
    meta = json.loads((DATA / "run_metadata.json").read_text(encoding="utf-8"))
    rec = _csv("dq_reconciliation")
    miss = _csv("dq_missingness")
    breaks = _csv("dq_series_breaks")
    outl = _csv("outliers")

    def natv(seg, year, col="litres_p50"):
        return float(nat.query("segment == @seg and year == @year")[col].iloc[0])

    t = f.t
    t["total25"], t["lo25"], t["hi25"] = natv("TOTAL", 2025), natv("TOTAL", 2025, "litres_p025"), natv("TOTAL", 2025, "litres_p975")
    t["total28"], t["lo28"], t["hi28"] = natv("TOTAL", 2028), natv("TOTAL", 2028, "litres_p025"), natv("TOTAL", 2028, "litres_p975")
    t["cagr"] = (t["total28"] / t["total25"]) ** (1 / 3) - 1
    for s in ["MCO", "PCMO", "HDMO"]:
        t[f"{s}25"], t[f"{s}28"] = natv(s, 2025), natv(s, 2028)
        t[f"{s}_growth"] = t[f"{s}28"] / t[f"{s}25"] - 1
    t["increment"] = t["total28"] - t["total25"]
    t["vehicles_total_k"] = float(veh["vehicles_k"].sum())
    t["pop_total_k"] = float(veh["population_k"].sum())
    t["density_nat"] = 1000 * t["vehicles_total_k"] / t["pop_total_k"]

    # value translation
    lo, mid, hi = USD_PER_LITRE
    t["value25_usd_m"] = t["total25"] * mid / 1e6
    t["value_incr_usd_m"] = t["increment"] * mid / 1e6
    t["usd_per_litre"] = USD_PER_LITRE
    # misallocation under the population-share rule: half the sum of absolute differences
    mis = (bcmp["model_mc_p50"] - bcmp["baseline_population_share"]).abs().sum() / 2
    t["misallocated_litres"] = mis
    t["misallocated_share"] = mis / bcmp["model_mc_p50"].sum()
    t["misallocated_usd_m"] = mis * mid / 1e6
    t["hours_saved_year"] = MANUAL_HOURS_PER_REFRESH * RELEASES_PER_YEAR
    t["refresh_seconds"] = float(meta.get("seconds", 30))
    t["bmet"] = bmet

    # tiers
    tierA = pri[pri["tier"] == "A"]
    t["tierA_litres"] = float(tierA["litres_2025_p50"].sum())
    t["tierA_share"] = t["tierA_litres"] / float(pri["litres_2025_p50"].sum())
    t["tierA_incr_share"] = float(tierA["increment_2025_2028_p50"].sum()) / float(pri["increment_2025_2028_p50"].sum())
    t["robust_top10"] = tierA[tierA["prob_top10"] >= 0.9]["province_en"].tolist()
    t["fragile"] = pri[(pri["prob_top10"] >= 0.3) & (pri["prob_top10"] < 0.9)]["province_en"].tolist()

    # data quality
    t["rec_max"] = float(rec[["pop_diff_pct", "freight_diff_pct", "grdp_pc_diff_pct"]].abs().max().max())
    t["n_breaks_2025"] = int((breaks["year"] == 2025).sum())
    t["outliers"] = outl[outl["flag"].fillna("") != ""]["province_en"].tolist()
    t["n_raw_cells"] = 20695
    t["n_sources"] = 14

    # EDA facts
    nat_py = py.groupby("year")[["population_k", "road_freight_kt"]].sum()
    t["freight_growth_2011_25"] = nat_py.loc[2025, "road_freight_kt"] / nat_py.loc[2011, "road_freight_kt"] - 1
    t["pop_growth_2011_25"] = nat_py.loc[2025, "population_k"] / nat_py.loc[2011, "population_k"] - 1
    p = prod.set_index("year")
    t["moto_assembled_2025"] = float(p.loc[2025, "motorbikes_assembled_k"])
    t["cars_assembled_2025"] = float(p.loc[2025, "cars_assembled_k"])
    t["cars_assembled_2015"] = float(p.loc[2015, "cars_assembled_k"])
    t["density_min"] = veh.loc[veh["vehicles_per_1000"].idxmin(), ["province_en", "vehicles_per_1000"]].tolist()
    t["density_max"] = veh.loc[veh["vehicles_per_1000"].idxmax(), ["province_en", "vehicles_per_1000"]].tolist()
    t["rho_grdp_urban"] = float(veh[["grdp_pc_mvnd", "urban_share"]].corr(method="spearman").iloc[0, 1])

    f.tables.update(dict(dim=dim, nat=nat, pri=pri, veh=veh, tests=tests, checks=checks, bt=bt, sens=sens,
                         bcmp=bcmp, bench=bench, py=py, prod=prod, miss=miss, rec=rec, outl=outl))
    return f


def ml(x: float, d: int = 1) -> str:
    """litres -> 'xx.x' million litres"""
    return f"{x / 1e6:,.{d}f}"


def pct(x: float, d: int = 0) -> str:
    """0.123 -> '12%' (d decimals)"""
    return f"{x * 100:.{d}f}%"

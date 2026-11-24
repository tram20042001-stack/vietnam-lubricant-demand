"""Sales dashboard - Vietnam lubricant demand potential.

Run:  .venv\\Scripts\\streamlit run dashboard\\app.py
Reads the CSV exports in dashboard/data written by `python -m vnlube.pipeline`.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data"
ROOT = Path(__file__).parents[1]
SEG = ["MCO", "PCMO", "HDMO"]
SEG_LABEL = {"MCO": "Motorbike oil", "PCMO": "Passenger-car oil", "HDMO": "Heavy-duty oil"}
SEG_COLOR = {"MCO": "#2a78d6", "PCMO": "#eb6834", "HDMO": "#1baf7a"}
TIER_COLOR = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
GRID, MUTED = "#e1e0d9", "#898781"

st.set_page_config(page_title="VN Lubricant Demand", page_icon="🛢️", layout="wide")


def data_version() -> float:
    """Timestamp of the last pipeline run. The pipeline rewrites run_metadata.json on every run, so a
    new value means new data on disk."""
    meta_file = DATA / "run_metadata.json"
    return meta_file.stat().st_mtime if meta_file.exists() else 0.0


@st.cache_data
def load(version: float) -> dict[str, pd.DataFrame]:
    """Read every exported table. The cache is keyed on `version`, so after a scheduled pipeline run
    the next page refresh reloads the data automatically, even if the app was left running."""
    names = ["dim_province", "fact_demand", "national_demand", "priority", "fact_vehicles_2025",
             "fact_drivers_forecast", "hypothesis_tests", "backtest_summary", "sensitivity",
             "assumptions_lubricant", "dq_vehicle_totals", "dq_missingness", "outliers", "fact_province_year",
             "assumption_checks", "baseline_metrics", "baseline_comparison"]
    return {n: pd.read_csv(DATA / f"{n}.csv", encoding="utf-8-sig") for n in names}


def style(fig: go.Figure, height: int = 420) -> go.Figure:
    """Shared chart styling: transparent background (works in light and dark theme), hairline grid,
    legend in one row above the plot."""
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.08, x=0, title=None),
                      hoverlabel=dict(bgcolor="white"))
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID)
    return fig


if not (DATA / "priority.csv").exists():
    st.error("No outputs yet - run `python -m vnlube.pipeline --force` first.")
    st.stop()

d = load(data_version())
dim = d["dim_province"]
meta = json.loads((DATA / "run_metadata.json").read_text(encoding="utf-8")) if (DATA / "run_metadata.json").exists() else {}

# ---------------------------------------------------------------- header + refresh
left, right = st.columns([4, 1])
left.title("Vietnam lubricant demand potential")
left.caption("Official NSO vehicle, population, income and freight statistics -> Monte Carlo demand model "
             f"(litres/year). Last pipeline run: {meta.get('run_at_utc', 'n/a')} - {meta.get('outcome', '')}")
# The refresh button needs the full pipeline (package `vnlube`), which exists only in a local install.
# The hosted copy (Streamlit Community Cloud) shows the data committed to GitHub instead.
PIPELINE_AVAILABLE = importlib.util.find_spec("vnlube") is not None
if not PIPELINE_AVAILABLE:
    right.caption("Hosted copy: shows the data in the GitHub repo; refreshed when the repo is updated.")
elif right.button("Check NSO for new data", help="Downloads the latest NSO tables; rebuilds only if something changed"):
    with st.spinner("Checking NSO PX-Web for new releases..."):
        r = subprocess.run([sys.executable, "-m", "vnlube.pipeline"], cwd=ROOT, capture_output=True, text=True)
    st.cache_data.clear()
    (st.success if r.returncode == 0 else st.error)((r.stderr or r.stdout).strip().splitlines()[-1])

# ---------------------------------------------------------------- filters (one row)
f1, f2, f3 = st.columns([3, 2, 1])
regions = f1.multiselect("Region", sorted(dim["region_en"].unique()), placeholder="All regions")
segments = f2.multiselect("Segment", SEG, default=SEG, format_func=SEG_LABEL.get)
year = f3.selectbox("Year", sorted(d["fact_demand"]["year"].unique()), index=0)
segments = segments or SEG
codes = dim[dim["region_en"].isin(regions)]["province_code"] if regions else dim["province_code"]

dem = d["fact_demand"].merge(dim[["province_code", "province_en", "region_en"]], on="province_code")
dem = dem[dem["province_code"].isin(codes) & dem["segment"].isin(segments)]
dy = dem[dem["year"] == year]

# ---------------------------------------------------------------- KPI tiles
nat = d["national_demand"]
k1, k2, k3, k4 = st.columns(4)
sel_total = dy["litres_p50"].sum() / 1e6
k1.metric(f"Demand potential {year} (selection)", f"{sel_total:,.1f} M L",
          help="Sum of province x segment medians. The national median (next tile) is the median of the "
               "simulated national totals, so the two differ slightly.")
t = nat[(nat["segment"] == "TOTAL") & (nat["year"] == year)].iloc[0]
k2.metric("National total, 95% interval", f"{t.litres_p50 / 1e6:,.0f} M L",
          f"{t.litres_p025 / 1e6:,.0f}-{t.litres_p975 / 1e6:,.0f} M L", delta_color="off")
y0 = dem[dem["year"] == dem["year"].min()]["litres_p50"].sum()
y1 = dem[dem["year"] == dem["year"].max()]["litres_p50"].sum()
k3.metric("Growth 2025->2028 (selection)", f"{(y1 / y0 - 1):+.1%}")
pri = d["priority"].merge(dim[["province_code", "province_en", "region_en"]], on="province_code")
k4.metric("Tier-A provinces in selection", int(pri[pri["province_code"].isin(codes) & (pri["tier"] == "A")].shape[0]))

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Province ranking", "Province drill-down", "Priority matrix",
                                        "What-if assumptions", "Evidence & data quality"])

# ---------------------------------------------------------------- 1 ranking
with tab1:
    order = dy.groupby("province_en")["litres_p50"].sum().sort_values(ascending=False).index
    fig = px.bar(dy.assign(ml=dy["litres_p50"] / 1e6, lo=dy["litres_p025"] / 1e6, hi=dy["litres_p975"] / 1e6,
                           seg=dy["segment"].map(SEG_LABEL)),
                 x="ml", y="province_en", color="segment", orientation="h",
                 category_orders={"province_en": list(order), "segment": SEG},
                 color_discrete_map=SEG_COLOR, labels={"ml": "Million litres", "province_en": ""},
                 custom_data=["seg", "lo", "hi", "region_en"])
    fig.update_traces(marker_line_color="white", marker_line_width=1.5,
                      hovertemplate="<b>%{y}</b> - %{customdata[3]}<br>%{customdata[0]}: %{x:.2f} M L"
                                    "<br>95% interval %{customdata[1]:.2f}-%{customdata[2]:.2f} M L<extra></extra>")
    fig.for_each_trace(lambda tr: tr.update(name=SEG_LABEL[tr.name]))
    st.plotly_chart(style(fig, max(420, 22 * len(order))), use_container_width=True)
    tbl = dy.pivot_table(index=["province_en", "region_en"], columns="segment", values="litres_p50", aggfunc="sum") / 1e6
    tbl["Total"] = tbl.sum(axis=1)
    st.dataframe(tbl.sort_values("Total", ascending=False).round(2), use_container_width=True)

# ---------------------------------------------------------------- 2 drill-down
with tab2:
    names = dim[dim["province_code"].isin(codes)].sort_values("province_en")
    prov = st.selectbox("Province", names["province_en"], index=0)
    code = names.loc[names["province_en"] == prov, "province_code"].iloc[0]
    pd_ = d["fact_demand"][(d["fact_demand"]["province_code"] == code) & d["fact_demand"]["segment"].isin(segments)]
    c1, c2 = st.columns([3, 2])
    fig = go.Figure()
    for s in segments:
        g = pd_[pd_["segment"] == s]
        fig.add_trace(go.Scatter(x=list(g["year"]) + list(g["year"])[::-1],
                                 y=list(g["litres_p975"] / 1e6) + list(g["litres_p025"] / 1e6)[::-1],
                                 fill="toself", fillcolor=SEG_COLOR[s], opacity=0.15, line=dict(width=0),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=g["year"], y=g["litres_p50"] / 1e6, name=SEG_LABEL[s], mode="lines+markers",
                                 line=dict(color=SEG_COLOR[s], width=2), marker=dict(size=8),
                                 hovertemplate="%{x}: %{y:.2f} M L<extra>" + SEG_LABEL[s] + "</extra>"))
    fig.update_layout(title=f"{prov} - demand potential (median, 95% band)", yaxis_title="Million litres",
                      hovermode="x unified", yaxis_rangemode="tozero")
    fig.update_xaxes(dtick=1)
    c1.plotly_chart(style(fig), use_container_width=True)
    v = d["fact_vehicles_2025"].set_index("province_code").loc[code]
    p = pri.set_index("province_code").loc[code]
    c2.markdown(f"**Tier {p['tier']}** - priority rank {int(p['priority_rank'])} of 34 "
                f"(top 10 in {p['prob_top10']:.0%} of simulations)")
    c2.markdown(f"- Registered vehicles 2025 (official): **{v['vehicles_k']:,.0f} thousand** "
                f"({v['vehicles_per_1000']:,.0f} per 1,000 people)\n"
                f"- Population: {v['population_k']:,.0f} thousand; GRDP per capita {v['grdp_pc_mvnd']:,.0f} M VND\n"
                f"- Road freight: {v['road_freight_kt'] / 1000:,.1f} M tonnes\n"
                f"- Largest absolute growth: **{SEG_LABEL[p['growth_focus_segment']]}**\n"
                f"- Segment mix 2025: MCO {p['mco_share_2025']:.0%} / PCMO {p['pcmo_share_2025']:.0%} / "
                f"HDMO {p['hdmo_share_2025']:.0%}")
    hist = d["fact_province_year"][d["fact_province_year"]["province_code"] == code]
    fig2 = px.line(hist, x="year", y="road_freight_kt", markers=True,
                   labels={"road_freight_kt": "Road freight (thousand tonnes)", "year": ""})
    fig2.update_traces(line_color=SEG_COLOR["HDMO"])
    c2.plotly_chart(style(fig2, 260), use_container_width=True)

# ---------------------------------------------------------------- 3 priority
with tab3:
    pp = pri[pri["province_code"].isin(codes)].copy()
    pp["size"], pp["incr"] = pp["litres_2025_p50"] / 1e6, pp["increment_2025_2028_p50"] / 1e6
    pp["label"] = pp["province_en"].where(pp["tier"] == "A", "")   # label tier A only; hover for the rest
    fig = px.scatter(pp, x="size", y="incr", color="tier", text="label", color_discrete_map=TIER_COLOR,
                     category_orders={"tier": ["A", "B", "C"]},
                     labels={"size": "Demand potential 2025 (M L)", "incr": "Added demand 2025->2028 (M L)"},
                     custom_data=["province_en", "prob_top10", "cagr_2025_2028_p50", "growth_focus_segment"])
    fig.update_traces(marker=dict(size=11, line=dict(color="white", width=2)), textposition="top center",
                      textfont=dict(size=10, color=MUTED),
                      hovertemplate="<b>%{customdata[0]}</b><br>2025: %{x:.1f} M L<br>+%{y:.2f} M L to 2028"
                                    "<br>CAGR %{customdata[2]:.1%}<br>P(top 10) %{customdata[1]:.0%}"
                                    "<br>Growth focus: %{customdata[3]}<extra></extra>")
    fig.update_xaxes(type="log")
    st.plotly_chart(style(fig, 520), use_container_width=True)
    show = pp[["priority_rank", "tier", "province_en", "region_en", "size", "incr", "cagr_2025_2028_p50",
               "prob_top10", "growth_focus_segment", "litres_per_capita_2025"]]
    st.dataframe(show.rename(columns={"size": "2025 M L", "incr": "+M L to 2028", "cagr_2025_2028_p50": "CAGR",
                                      "prob_top10": "P(top 10)", "litres_per_capita_2025": "L per capita"}),
                 hide_index=True, use_container_width=True,
                 column_config={"CAGR": st.column_config.NumberColumn(format="%.1f%%"),
                                "P(top 10)": st.column_config.ProgressColumn(min_value=0, max_value=1)})

# ---------------------------------------------------------------- 4 what-if
with tab4:
    st.caption("Change a usage assumption and the demand potential is recomputed from the modelled fleet "
               "(median fleet per province and segment). Defaults are the most-likely values of the model.")
    a = d["assumptions_lubricant"].set_index(["segment", "parameter"])
    # sliders are bounded by each assumption's documented low/high range; default = most-likely value
    vals = {}
    cols = st.columns(3)
    for col, s in zip(cols, SEG):
        col.markdown(f"**{SEG_LABEL[s]}**")
        for prm, label, step in [("active_share", "Active share of registered fleet", 0.01),
                                 ("annual_km", "Annual km per vehicle", 500.0),
                                 ("drain_interval_km", "Oil-change interval (km)", 250.0),
                                 ("fill_litres", "Litres per oil change", 0.1)]:
            r = a.loc[(s, prm)]
            vals[(s, prm)] = col.slider(label, float(r["low"]), float(r["high"]), float(r["mode"]), step=step,
                                        key=f"{s}{prm}")
        vals[(s, "other_fluids_factor")] = float(a.loc[(s, "other_fluids_factor"), "mode"])
    # litres per registered vehicle per year, under the scenario (lpv) and under the defaults (base_lpv)
    lpv = {s: vals[(s, "active_share")] * vals[(s, "annual_km")] / vals[(s, "drain_interval_km")]
           * vals[(s, "fill_litres")] * vals[(s, "other_fluids_factor")] for s in SEG}
    base_lpv = {s: a.loc[(s, "active_share"), "mode"] * a.loc[(s, "annual_km"), "mode"]
                / a.loc[(s, "drain_interval_km"), "mode"] * a.loc[(s, "fill_litres"), "mode"]
                * a.loc[(s, "other_fluids_factor"), "mode"] for s in SEG}
    # the fleet is held at its simulated median; only the usage assumptions change in the what-if
    w = dem[dem["year"] == year].copy()
    w["scenario"] = w["fleet_registered_p50"] * w["segment"].map(lpv) / 1e6
    w["default"] = w["fleet_registered_p50"] * w["segment"].map(base_lpv) / 1e6
    m1, m2 = st.columns(2)
    m1.metric(f"Scenario demand {year} (selection)", f"{w['scenario'].sum():,.1f} M L",
              f"{w['scenario'].sum() - w['default'].sum():+,.1f} M L vs default")
    m2.metric("Litres per vehicle per year", " / ".join(f"{SEG_LABEL[s].split()[0]} {lpv[s]:.1f}" for s in SEG))
    agg = w.groupby("segment")[["default", "scenario"]].sum().reindex(SEG).reset_index()
    agg["segment"] = agg["segment"].map(SEG_LABEL)
    fig = px.bar(agg.melt(id_vars="segment", var_name="case", value_name="ml"), x="segment", y="ml",
                 color="case", barmode="group", color_discrete_map={"default": "#c3c2b7", "scenario": "#2a78d6"},
                 labels={"ml": "Million litres", "segment": ""})
    st.plotly_chart(style(fig, 360), use_container_width=True)

# ---------------------------------------------------------------- 5 evidence
with tab5:
    st.subheader("Hypothesis tests (observed data, Holm-adjusted)")
    st.dataframe(d["hypothesis_tests"], hide_index=True, use_container_width=True)
    st.subheader("Model assumption checks")
    st.dataframe(d["assumption_checks"], hide_index=True, use_container_width=True)
    st.subheader("Model vs baselines (2025)")
    st.caption("Deterministic = all assumptions at their most-likely value; population share = national "
               "total split by headcount (current rule of thumb)")
    st.dataframe(d["baseline_metrics"].T.rename(columns={0: "value"}).round(2), use_container_width=True)
    e1, e2 = st.columns(2)
    e1.subheader("Forecast back-test (2023-2025 hold-out)")
    e1.dataframe(d["backtest_summary"].round(2), hide_index=True, use_container_width=True)
    e2.subheader("What drives the uncertainty")
    sens = d["sensitivity"].head(10).iloc[::-1]
    fig = px.bar(sens, x="spearman_with_total_2025", y="parameter", orientation="h",
                 labels={"spearman_with_total_2025": "Rank correlation with national 2025 demand", "parameter": ""})
    fig.update_traces(marker_color="#2a78d6")
    e2.plotly_chart(style(fig, 340), use_container_width=True)
    st.subheader("Data quality")
    q1, q2 = st.columns(2)
    q1.caption("Province vehicle counts vs published regional / national totals (thousand vehicles)")
    q1.dataframe(d["dq_vehicle_totals"], hide_index=True, use_container_width=True)
    q2.caption("Missing values by type (structural = unit did not exist; random = interpolated)")
    q2.dataframe(d["dq_missingness"], hide_index=True, use_container_width=True)
    st.caption("Robust outlier screen (|z| > 3.5 flagged; kept, not removed)")
    st.dataframe(d["outliers"], hide_index=True, use_container_width=True)
    if meta.get("sources"):
        st.caption("Source status at last run")
        st.json(meta["sources"])

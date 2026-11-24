"""Generate notebooks/01_preliminary_model.ipynb from the cell definitions below.

Keeping the notebook as code makes it reviewable in Git and regenerable:
    .venv\\Scripts\\python.exe notebooks\\build_notebook.py
    .venv\\Scripts\\jupyter.exe nbconvert --to notebook --execute --inplace notebooks\\01_preliminary_model.ipynb
"""
from pathlib import Path

import nbformat as nbf

cells = []


def md(text: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(text.strip()))


def code(text: str) -> None:
    cells.append(nbf.v4.new_code_cell(text.strip()))


# =============================================================================================
md("""
# Vietnam Lubricant Demand Potential: Preliminary Model

**Capstone - Data Analytics track.** This notebook is the preliminary model file. It walks through every
pre-submission task on the real, official data:

| # | Task | Section |
|---|---|---|
| 1 | Problem framing | [1](#1.-Problem-framing) |
| 2 | Raw data & data cleaning | [2](#2.-Raw-data), [3](#3.-Data-cleaning) |
| 3 | Exploratory data analysis (EDA) | [4](#4.-Exploratory-data-analysis) |
| 4 | Feature engineering | [5](#5.-Feature-engineering) |
| 5 | Data transformation & storage | [6](#6.-Data-transformation-and-storage) |
| 6 | Model preparation | [7](#7.-Model-preparation) |
| 7 | Model assumption checks | [8](#8.-Model-assumption-checks) |
| 8 | Baseline model building | [9](#9.-Baseline-models) |

The production code lives in `src/vnlube/` (imported here), so the notebook and the automated pipeline
always use the same logic. The notebook shows *why* each step is done and what the data looks like at
each stage.
""")

code("""
# --- setup -------------------------------------------------------------------------------
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)      # keep the output readable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import statsmodels.api as sm
from scipy import stats

# project modules (installed in editable mode: pip install -e .)
from vnlube import config, transform, statistics, forecast, demand
from vnlube import data_access as da
from vnlube.figures import SEG_COLORS, SEG_LABEL, INK, INK2, GRID, SURFACE   # shared chart palette
from vnlube.ingest import raw_csv_path
from vnlube.jsonstat import read_jsonstat

# vnlube.figures switches matplotlib to the file-only "Agg" backend (for the pipeline);
# switch back so charts are displayed and saved inside the notebook
%matplotlib inline

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
pd.set_option("display.float_format", "{:,.3f}".format)
print("project root:", config.ROOT)
""")

# =============================================================================================
md("""
## 1. Problem framing

**Business problem.** The lubricant sales team sets provincial targets, distributor coverage and sales
headcount using national totals split by population share ("rule of thumb"). There is no defensible
estimate of how many litres of **motorbike oil (MCO)**, **passenger-car motor oil (PCMO)** and
**heavy-duty oil (HDMO)** each province can consume, or where demand is growing fastest. The estimate
also has to be redone by hand whenever the government publishes new statistics.

**Decision supported.** *Which provinces should get more sales and distributor effort, and with which
product focus?* This is reviewed quarterly by the national sales director, regional managers, distributor
development and marketing.

**Unit of analysis.** Province (34 provinces in force since 1 July 2025) x segment x year (2025 base,
forecast 2026-2028).

**Approach.** Lubricant demand is driven by the vehicle fleet:

$$\\text{litres} = \\text{fleet} \\times \\text{active share} \\times \\frac{\\text{km per year}}{\\text{km per oil change}}
\\times \\text{litres per change} \\times \\text{top-up factor}$$

Official province vehicle counts come from the NSO. The usage parameters are uncertain, so they are given
as ranges and propagated with Monte Carlo simulation.

**KPIs and success metrics** (defined before looking at results):

| KPI | Target |
|---|---|
| Demand potential by province x segment with a 95% interval | all 34 x 3 |
| Forecast accuracy of drivers on a 2023-2025 hold-out | national MAPE <= 10%, median province MAPE <= 15% |
| Model must beat simple baselines | lower hold-out error than naive / drift; provincial allocation that differs from population share where vehicles, income or freight differ |
| Refresh effort after an NSO release | < 15 minutes, no manual steps |

**Testable hypotheses** (on observed data only, alpha = 0.05, Holm-corrected):
* **H1** - vehicle density (vehicles per 1,000 people) differs between the 6 regions.
* **H2** - vehicle density increases with GRDP per capita (controlling for urbanisation).
* **H3** - provinces with lower vehicle density grow faster in real GRDP (catch-up headroom).
""")

# =============================================================================================
md("""
## 2. Raw data

All data come from the Vietnam National Statistics Office (NSO) PX-Web database and were downloaded by
`python -m vnlube.ingest`. Each table is archived **unchanged** in `data/raw/<sid>/<sid>.json` (the
original download) and as a flat `data/raw/<sid>/<sid>.csv` copy. The manifest records the URL, time
and SHA-256 hash of every download.
""")

code("""
# The download manifest: one row per download attempt (latest attempt per source shown)
manifest = pd.read_csv(config.MANIFEST)
latest = manifest.sort_values("downloaded_at_utc").groupby("sid").tail(1)
latest[["sid", "table", "geography", "downloaded_at_utc", "cells", "status", "sha256"]].assign(
    sha256=lambda d: d["sha256"].str[:12] + "...")
""")

code("""
# Load every raw CSV exactly as published and summarise its shape, years and missing cells
summary = []
raw = {}
for src in config.SOURCES:
    df = pd.read_csv(raw_csv_path(src.sid), encoding="utf-8-sig")
    raw[src.sid] = df
    year_col = "Năm"
    summary.append({
        "sid": src.sid, "content": src.title_en[:60], "rows": len(df),
        "columns": ", ".join(c for c in df.columns if c not in ("value", "flag")),
        "periods": f"{df[year_col].iloc[0]} .. {df[year_col].iloc[-1]}",
        "missing_values": int(df["value"].isna().sum()),
    })
pd.DataFrame(summary)
""")

code("""
# The key table: registered vehicles (cars + motorbikes) by province, 2025 - as published
raw["p34_vehicles"].head(8)
""")

# =============================================================================================
md("""
## 3. Data cleaning

The raw tables are real and messy. The problems found, and how each is handled in `sql/02_clean.sql` /
`sql/03_marts.sql`:

| Problem in the raw data | Treatment |
|---|---|
| Two look-alike capital letters for Đ: `Đ` (U+0110) and `Ð` (U+00D0) | ASCII matching key `name_key()` |
| "TP. Hồ Chí Minh", "TP.Hồ Chí Minh", "Thừa Thiên Huế" vs "Huế" | prefix stripping + alias table |
| Year labels such as `Sơ bộ 2025` (preliminary), `Ước tính 2025` (estimate) | parse year + keep a data-status column |
| Region and national subtotal rows mixed with provinces | classify each row (national / region / province / unallocated) |
| `..` cells (no value) | classify as **structural** (unit did not exist) or **random** (interior gap -> interpolate) |
| 63 former provinces in the history, 34 since July 2025 | roll-up with an official merger map, validated against NSO's own 34-province figures |
| Urban/rural reclassification in 2025 | series-break table; models use the 2024 urban share |
| Implausible / extreme values | robust z-score screen (reported, not deleted) |
""")

code("""
# Problem 1: the same region is spelled with two different capital D letters across tables
names = pd.concat([raw[s].iloc[:, 0] for s in ["p34_population", "p63_population"]]).drop_duplicates()
odd = names[names.str.contains("Ð")]          # U+00D0, the look-alike letter
print("labels using U+00D0 'Ð':", list(odd)[:6])
print("same text with U+0110 'Đ' exists?", any(n.replace("Ð", "Đ") in set(names) for n in odd))
""")

code("""
# Problem 2: period labels are not plain years
periods = pd.concat([raw[s]["Năm"].astype(str) for s in raw]).drop_duplicates()
print(sorted(p for p in periods if not p.isdigit()))
""")

code("""
# Problem 3: where are the missing values in the 63-province population history?
p63 = raw["p63_population"]
missing = p63[p63["value"].isna()]
missing.groupby("Tỉnh, thành phố")["Năm"].agg(["min", "max", "count"])
# -> all gaps are at the START (provinces split off in 2004) or END (Ha Tay merged into Ha Noi in 2008)
#    of a series: structural, not random. They must NOT be imputed.
""")

code("""
# Build the warehouse: staging -> clean -> marts (runs sql/01..03 in DuckDB)
transform.run()
print(da.query("SELECT count(*) AS unmatched_labels FROM dq_unmatched_geography"))
""")

code("""
# Missing-value classification produced by the SQL cleaning step
da.query("SELECT sid, geo_level, missing_type, n_cells, min_year, max_year, left(units, 70) AS units "
         "FROM dq_missingness ORDER BY sid")
""")

code("""
# Validation of the 63 -> 34 province roll-up against the OFFICIAL 34-province series (2020-2025):
# if the merger map were wrong, these differences would be large.
rec = da.query("SELECT * FROM dq_reconciliation")
rec[["pop_diff_pct", "freight_diff_pct", "grdp_pc_diff_pct"]].abs().describe().loc[["count", "mean", "max"]]
""")

code("""
# Provinces must add up to the published regional and national vehicle totals
da.query("SELECT * FROM dq_vehicle_totals")
""")

code("""
# Series breaks: urban share jumps > 3 percentage points (2025 = administrative reform)
breaks = da.query("SELECT * FROM dq_series_breaks ORDER BY year DESC, abs(change_pp) DESC")
print(breaks["year"].value_counts().sort_index().to_dict())
breaks.head(8)
""")

code("""
# Outlier screen on the 2025 cross-section (robust z = (x - median) / (1.4826 * MAD))
base = da.province_base()
out = statistics.outliers(base)
fig, ax = plt.subplots(1, 2, figsize=(11, 3.2))
for a, col, lab in [(ax[0], "z_density", "vehicle density"), (ax[1], "z_accident_rate", "accident rate")]:
    a.bar(out["province_en"], out[col], color=[SEG_COLORS["PCMO"] if abs(v) > 3.5 else SEG_COLORS["MCO"] for v in out[col]])
    a.axhline(3.5, color=INK2, ls="--", lw=1); a.axhline(-3.5, color=INK2, ls="--", lw=1)
    a.set_title(f"Robust z-score: {lab}"); a.tick_params(axis="x", rotation=90, labelsize=7)
plt.tight_layout(); plt.show()
out[out["flag"] != ""]
# Thai Nguyen and Lang Son have ~2.5x the national accident rate per vehicle. They are genuine
# official figures (not data errors) and do not enter the demand model, so they are kept and reported.
""")

# =============================================================================================
md("""
## 4. Exploratory data analysis
""")

code("""
# Descriptive statistics of the 2025 province cross-section (n = 34)
cols = ["vehicles_k", "vehicles_per_1000", "population_k", "grdp_pc_mvnd", "urban_share_model",
        "road_freight_kt", "accidents_per_10k"]
base[cols].describe().T.assign(skew=base[cols].skew())
""")

code("""
# Distributions: vehicle density is fairly symmetric; GRDP per capita and freight are right-skewed
fig, ax = plt.subplots(1, 3, figsize=(12, 3))
ax[0].hist(base["vehicles_per_1000"], bins=12, color=SEG_COLORS["MCO"], edgecolor=SURFACE)
ax[0].set_title("Vehicles per 1,000 people")
ax[1].hist(base["grdp_pc_mvnd"], bins=12, color=SEG_COLORS["PCMO"], edgecolor=SURFACE)
ax[1].set_title("GRDP per capita (M VND)")
ax[2].hist(base["road_freight_kt"] / 1000, bins=12, color=SEG_COLORS["HDMO"], edgecolor=SURFACE)
ax[2].set_title("Road freight (M tonnes)")
plt.tight_layout(); plt.show()
""")

code("""
# Vehicle density by region (visual check for H1)
order = base.groupby("region_en")["vehicles_per_1000"].median().sort_values().index
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.boxplot([base.loc[base.region_en == r, "vehicles_per_1000"] for r in order], vert=False, widths=0.5)
ax.set_yticks(range(1, len(order) + 1), order)
ax.set_xlabel("Vehicles per 1,000 people (2025)")
plt.tight_layout(); plt.show()
""")

code("""
# Bivariate relationships (visual check for H2): density vs income and vs urbanisation
fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
ax[0].scatter(base["grdp_pc_mvnd"], base["vehicles_per_1000"], color=SEG_COLORS["MCO"])
ax[0].set_xscale("log"); ax[0].set_xlabel("GRDP per capita (log)"); ax[0].set_ylabel("vehicles per 1,000")
ax[1].scatter(base["urban_share_model"], base["vehicles_per_1000"], color=SEG_COLORS["PCMO"])
ax[1].set_xlabel("urban share (2024)")
plt.tight_layout(); plt.show()
""")

code("""
# Spearman correlation matrix (rank-based: robust to the skewed variables)
corr = base[cols].corr(method="spearman")
fig, ax = plt.subplots(figsize=(6.5, 5))
im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)          # diverging: blue <- 0 -> red
ax.set_xticks(range(len(cols)), cols, rotation=60, ha="right"); ax.set_yticks(range(len(cols)), cols)
for i in range(len(cols)):
    for j in range(len(cols)):
        ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=7)
fig.colorbar(im, ax=ax, shrink=0.8); plt.tight_layout(); plt.show()
# Note: GRDP per capita and urban share are correlated (rho ~ 0.6), so income and urbanisation
# have to be separated in a multivariable model (H2) rather than judged from one scatter.
""")

code("""
# National trends 2011-2025: population, road freight, and new vehicles assembled
py = da.province_year()
nat = py.groupby("year")[["population_k", "road_freight_kt"]].sum()
prod = da.query("SELECT * FROM mart_national_production WHERE year >= 2005")
fig, ax = plt.subplots(1, 3, figsize=(13, 3))
ax[0].plot(nat.index, nat["population_k"] / 1000, marker="o", color=INK); ax[0].set_title("Population (M)")
ax[1].plot(nat.index, nat["road_freight_kt"] / 1000, marker="o", color=SEG_COLORS["HDMO"]); ax[1].set_title("Road freight (M tonnes)")
ax[2].plot(prod["year"], prod["motorbikes_assembled_k"], marker="o", color=SEG_COLORS["MCO"], label="motorbikes")
ax[2].plot(prod["year"], prod["cars_assembled_k"] * 10, marker="o", color=SEG_COLORS["PCMO"], label="cars x10")
ax[2].set_title("Assembled per year (thousand)"); ax[2].legend()
for a in ax: a.set_ylim(0, None)
plt.tight_layout(); plt.show()
# Freight more than doubled since 2011 (HDMO driver); motorbike assembly has plateaued at ~3-4 M/yr
# since ~2011 (saturation); car assembly is still rising (PCMO driver).
""")

code("""
# Which provinces' road freight grew fastest 2020 -> 2025 (official 34-province series)?
fr = py[py.year.isin([2020, 2025])].pivot(index="province_code", columns="year", values="road_freight_kt")
growth_fr = ((fr[2025] / fr[2020]) ** (1 / 5) - 1).rename("freight_cagr_2020_25")
growth_fr.to_frame().join(base.set_index("province_code")["province_en"]).sort_values(
    "freight_cagr_2020_25", ascending=False).head(8)
""")

# =============================================================================================
md("""
## 5. Feature engineering

Features are derived from the cleaned marts. Each has a stated purpose:

| Feature | Definition | Used for |
|---|---|---|
| `vehicles_per_1000` | 1000 x vehicles / population | H1-H3 outcome; comparable across provinces of different size |
| `log_density`, `log_grdp` | natural logs | H2 regression (elasticity, reduces skew) |
| `urban_share_model` | urban / total population, **2024** | H2 control; avoids the 2025 reclassification break |
| `real_growth_22_25` | geometric mean of the official real GRDP index 2022-2025 | H3; income growth for the forecast |
| `rel_income` | GRDP per capita / national (population-weighted) | car allocation weight in the demand model |
| `freight_share` | province road freight / national | commercial-vehicle allocation |
| `freight_per_capita` | tonnes per person | EDA of HDMO intensity |
""")

code("""
# Build the feature table (the production code computes the same features inside its functions)
feat = base.copy()
feat["log_density"] = np.log(feat["vehicles_per_1000"])
feat["log_grdp"] = np.log(feat["grdp_pc_mvnd"])
g_nat = np.average(feat["grdp_pc_mvnd"], weights=feat["population_k"])     # population-weighted national
feat["rel_income"] = feat["grdp_pc_mvnd"] / g_nat
feat["freight_share"] = feat["road_freight_kt"] / feat["road_freight_kt"].sum()
feat["freight_per_capita"] = feat["road_freight_kt"] / feat["population_k"]   # tonnes per person
feat = feat.join(statistics.real_growth(py).rename("real_growth_22_25"), on="province_code")
feat_cols = ["vehicles_per_1000", "log_density", "log_grdp", "urban_share_model", "real_growth_22_25",
             "rel_income", "freight_share", "freight_per_capita"]
feat[["province_en"] + feat_cols].head()
""")

code("""
# Log transforms reduce skewness (closer to 0 = more symmetric), which suits linear regression
pd.DataFrame({
    "skew raw": [feat["grdp_pc_mvnd"].skew(), feat["vehicles_per_1000"].skew()],
    "skew log": [feat["log_grdp"].skew(), feat["log_density"].skew()],
}, index=["GRDP per capita", "vehicle density"])
""")

code("""
# Engineered allocation feature: implied car share of each province's fleet at the most-likely
# assumptions (elasticity 1.0, 7.2 M cars nationally). Shown to sanity-check the allocation logic.
eps, C = 1.0, 7.2e6
w = feat["vehicles_k"] * feat["rel_income"] ** eps
feat["implied_cars_k"] = C / 1000 * w / w.sum()
feat["implied_car_share"] = feat["implied_cars_k"] / feat["vehicles_k"]
feat.sort_values("implied_car_share", ascending=False)[["province_en", "vehicles_k", "rel_income",
                                                        "implied_cars_k", "implied_car_share"]].head(6)
# Plausibility: reported figures for Ha Noi are roughly 0.7-1.1 M cars (press, 2024); the implied value
# above sits in that range, so the allocation feature behaves sensibly.
""")

# =============================================================================================
md("""
## 6. Data transformation and storage

```
data/raw/<sid>.json  --(Python: JSON-stat -> long table)-->  stg_observation
        --(sql/01_reference.sql)--> ref_*  (provinces, 63->34 map, assumptions, benchmarks)
        --(sql/02_clean.sql)-->     cln_observation (typed years, status, geography, missing type), dq_*
        --(sql/03_marts.sql)-->     int_* (interpolation, roll-up) -> mart_* (analysis-ready) + dq_*
        --(pipeline.py)-->          res_* tables, dashboard/data/*.csv, data/processed/*.parquet
```

**Storage choices.** Raw JSON stays immutable for audit. DuckDB (a single file, in-process, SQL with window
functions) holds every layer. CSV feeds the dashboard and Power BI, and Parquet holds typed columnar copies
for analysis.
""")

code("""
# Every table in the warehouse, grouped by layer
tables = da.query("SELECT table_name, estimated_size AS rows FROM duckdb_tables() ORDER BY table_name")
tables["layer"] = tables["table_name"].str.split("_").str[0]
tables.groupby("layer")["table_name"].agg(["count", lambda s: ", ".join(s)]).rename(
    columns={"count": "tables", "<lambda_0>": "names"})
""")

code("""
# The core of the name harmonisation (DuckDB macro in sql/01_reference.sql)
print((config.SQL_DIR / "01_reference.sql").read_text(encoding="utf-8").split("CREATE OR REPLACE TABLE")[0])
print(da.query("SELECT name_key('TP.Hồ Chí Minh') AS a, name_key('Thành phố Hồ Chí Minh') AS b, "
               "name_key('Ðiện Biên') AS c, name_key('Điện Biên') AS d"))
""")

code("""
# The analysis-ready province-year mart (2011-2025, 34 provinces)
mart = da.query("SELECT * FROM mart_province_year")
print(mart.shape, "| years", mart.year.min(), "-", mart.year.max(),
      "| sources:", mart.geography_source.value_counts().to_dict())
mart[mart.province_code == "P01"].tail(4)
""")

code("""
# Storage footprint: raw downloads vs warehouse vs columnar exports
size = lambda p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6
print(f"raw JSON + CSV : {size(config.RAW):6.2f} MB")
print(f"DuckDB file    : {config.WAREHOUSE.stat().st_size / 1e6:6.2f} MB")
print(f"Parquet exports: {size(config.PROCESSED):6.2f} MB" if config.PROCESSED.exists() else "parquet: run the pipeline")
""")

# =============================================================================================
md("""
## 7. Model preparation

Three model components are prepared:
1. **Hypothesis models** (H1-H3) on the 34-province cross-section.
2. **Driver forecasts** - a time-based split: train on years <= 2022 and test on 2023-2025 (no random
   split, which would leak future information).
3. **Monte Carlo demand model** - every uncertain assumption gets a documented triangular range.
""")

code("""
# Assumption ranges (data/reference/*.csv) - every parameter has a rationale and/or a source
lube = da.triangular_table("ref_lubricant_assumptions")
split = da.triangular_table("ref_fleet_split_assumptions")
lube[["segment", "parameter", "low", "mode", "high", "unit"]]
""")

code("""
split[["parameter", "low", "mode", "high", "unit", "source"]]
""")

code("""
# Implied litres per registered vehicle per year, by segment (distribution over 10,000 draws)
prm = demand.draw_parameters(lube, split, n=10_000, seed=2025)
lpv = {s: prm[f"{s}.active_share"] * prm[f"{s}.annual_km"] / prm[f"{s}.drain_interval_km"]
          * prm[f"{s}.fill_litres"] * prm[f"{s}.other_fluids_factor"] for s in demand.SEGMENTS}
fig, ax = plt.subplots(1, 3, figsize=(12, 2.8))
for a, s in zip(ax, demand.SEGMENTS):
    a.hist(lpv[s], bins=50, color=SEG_COLORS[s]); a.set_title(f"{SEG_LABEL[s]}: litres/vehicle/yr")
plt.tight_layout(); plt.show()
pd.DataFrame({s: np.percentile(v, [2.5, 50, 97.5]) for s, v in lpv.items()}, index=["p2.5", "median", "p97.5"])
""")

code("""
# Time-based split used to evaluate the driver forecasts
print("train years:", py.year.min(), "-", forecast.BACKTEST_CUTOFF,
      "| test years:", forecast.BACKTEST_CUTOFF + 1, "-", config.BASE_YEAR,
      "| forecast:", config.BASE_YEAR + 1, "-", config.FORECAST_TO)
""")

code("""
# How many Monte Carlo draws are enough? Re-run with increasing n and watch the national median settle.
fc = forecast.run(py)
conv = []
for n in [250, 500, 1000, 2500, 5000, 10000]:
    r = demand.simulate(base, fc["drivers"], fc["growth"], lube, split, n=n, seed=11)
    tot = r.draws[:, :, :, 0].sum(axis=(1, 2)) / 1e6
    conv.append({"draws": n, "median_ML": np.median(tot), "p2.5": np.percentile(tot, 2.5), "p97.5": np.percentile(tot, 97.5)})
pd.DataFrame(conv)
# The median moves < 1% beyond ~2,500 draws; 10,000 draws are used (about 2 seconds).
""")

# =============================================================================================
md("""
## 8. Model assumption checks
""")

code("""
# Formal checks for the H1 (Kruskal-Wallis) and H2 (OLS) models
checks = statistics.assumption_checks(base)
checks
""")

code("""
# Visual residual diagnostics for the H2 regression
y, X, d = statistics.h2_design(base)
ols = sm.OLS(y, X).fit()
fig, ax = plt.subplots(1, 3, figsize=(13, 3.4))
ax[0].scatter(ols.fittedvalues, ols.resid, color=SEG_COLORS["MCO"]); ax[0].axhline(0, color=INK2)
ax[0].set_title("Residuals vs fitted (look for funnels / curves)")
sm.qqplot(ols.resid, line="s", ax=ax[1]); ax[1].set_title("Normal Q-Q of residuals")
infl = ols.get_influence().cooks_distance[0]
ax[2].bar(d["province_en"], infl, color=SEG_COLORS["HDMO"]); ax[2].axhline(4 / len(d), color=INK2, ls="--")
ax[2].set_title("Cook's distance (dashed = 4/n)"); ax[2].tick_params(axis="x", rotation=90, labelsize=6)
plt.tight_layout(); plt.show()
""")

md("""
**Remedy for the failed check.** The Ramsey RESET test flags that the log-log specification misses some
curvature. Before trusting the H2 conclusion ("income has no effect once urbanisation is controlled"), the
model is re-estimated with more flexible functional forms. If the income coefficient stays small and
non-significant in every one of them, the conclusion is robust to the misspecification.
""")

code("""
# Alternative specifications for H2 (all with HC3 robust errors)
specs = {
    "baseline: log grdp + urban": ["log_grdp", "urban_share_model"],
    "+ urban^2":                  ["log_grdp", "urban_share_model", "urban_sq"],
    "+ log grdp^2":               ["log_grdp", "log_grdp_sq", "urban_share_model"],
    "log urban instead of urban": ["log_grdp", "log_urban"],
    "+ region fixed effects":     ["log_grdp", "urban_share_model"] + [c for c in pd.get_dummies(d["region_en"], prefix="r", drop_first=True, dtype=float).columns],
}
dd = d.assign(urban_sq=d["urban_share_model"] ** 2, log_grdp_sq=d["log_grdp"] ** 2,
              log_urban=np.log(d["urban_share_model"]))
dd = dd.join(pd.get_dummies(d["region_en"], prefix="r", drop_first=True, dtype=float))
rows = []
for name, xs in specs.items():
    m = sm.OLS(dd["log_density"], sm.add_constant(dd[xs])).fit(cov_type="HC3")
    reset_p = float(sm.stats.diagnostic.linear_reset(sm.OLS(dd["log_density"], sm.add_constant(dd[xs])).fit(),
                                                    power=2, use_f=True).pvalue)
    rows.append({"specification": name, "income coef": m.params["log_grdp"], "p (two-sided)": m.pvalues["log_grdp"],
                 "adj R2": m.rsquared_adj, "AIC": m.aic, "RESET p": reset_p})
pd.DataFrame(rows)
# Reading the table: in every LINEAR specification (incl. region fixed effects) the income coefficient
# is small and non-significant. In the quadratic specification the linear coefficient alone is NOT the
# income effect (the effect depends on the income level) - it is evaluated properly in the next cell.
""")

code("""
# Income effect in the quadratic specification, evaluated at low / median / high income
nl = statistics.h2_nonlinear(base)
print(f"squared term b2 = {nl['b_log_grdp_sq']:.3f} (p = {nl['p_sq']:.4f}) -> "
      f"{'inverted U' if nl['b_log_grdp_sq'] < 0 else 'U shape'}; "
      f"turning point at GRDP per capita ~ {nl['turning_point_grdp_pc']:.0f} M VND "
      f"({nl['n_above_turning']} of 34 provinces above it)")
display(pd.DataFrame(nl["elasticity_at"]))

# visualise: fitted density curve at the average urban share
grid = np.linspace(dd["log_grdp"].min(), dd["log_grdp"].max(), 100)
fit_q = sm.OLS(dd["log_density"], sm.add_constant(dd[["log_grdp", "log_grdp_sq", "urban_share_model"]])).fit()
pred = fit_q.params["const"] + fit_q.params["log_grdp"] * grid + fit_q.params["log_grdp_sq"] * grid ** 2 \\
       + fit_q.params["urban_share_model"] * dd["urban_share_model"].mean()
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.scatter(dd["grdp_pc_mvnd"], dd["vehicles_per_1000"], color=SEG_COLORS["MCO"], label="provinces")
ax.plot(np.exp(grid), np.exp(pred), color=INK, lw=2, label="quadratic fit (avg. urban share)")
ax.axvline(nl["turning_point_grdp_pc"], color=INK2, ls="--", lw=1, label="turning point")
ax.set_xscale("log"); ax.set_xlabel("GRDP per capita, M VND (log)"); ax.set_ylabel("vehicles per 1,000")
ax.legend(fontsize=8); plt.tight_layout(); plt.show()
""")

md("""
**Interpretation of the assumption checks**

* **Normality, homoscedasticity, multicollinearity (H2) and equal spread (H1) pass.** The tests are
  used as intended.
* **Functional form (RESET) fails** for the linear H2 model. A squared income term removes the
  misspecification (RESET p > 0.05) and shows an **inverted U**. Vehicle density rises with income in
  poorer provinces, flattens around the median, and falls in the richest provinces, where cars replace
  motorbikes. The pre-registered *linear* H2 is still "not rejected". The inverted U is an
  **exploratory** finding, to be confirmed on the next data release rather than claimed as proven.
  Business meaning: in lower-income provinces, income growth still adds vehicles (mostly MCO); in rich
  provinces it shifts demand towards PCMO.
* **Independence (Durbin-Watson ~ 1.1) fails.** Neighbouring provinces have similar residuals (spatial
  correlation). Remedies used: region fixed effects and region-clustered standard errors (see
  `statistics.h2_income`, `p_cluster_region`). The linear income effect stays non-significant under both.
* **Influence:** 4 provinces exceed Cook's D > 4/n. The robustness refit without them is reported and
  does not change the conclusion.
""")

code("""
# Forecast model checks: are the hold-out errors of the chosen method unbiased (no systematic over/under)?
bt = fc["backtest"]
for var, g in bt.groupby("variable"):
    m = g["chosen_method"].iloc[0]
    bias = (g[f"pred_test_sum_{m}"] / g["actual_test_sum"] - 1) * 100
    t, p = stats.ttest_1samp(bias, 0)
    print(f"{var:16s} method={m:10s} mean bias {bias.mean():+.2f}%  (t-test vs 0: p = {p:.3f})")
# Population forecasts are unbiased. Freight forecasts UNDER-predict: road freight accelerated in
# 2023-2025 faster than its long-run trend. The HDMO growth forecast is therefore conservative
# (a lower bound rather than a central estimate); this is stated in the findings.
""")

code("""
# Monte Carlo checks: (1) the fleet split never produces a negative motorbike count,
# (2) results do not depend on the random seed, (3) the split conserves the official totals.
res = {s: demand.simulate(base, fc["drivers"], fc["growth"], lube, split, n=5000, seed=s) for s in [1, 2, 3]}
for s, r in res.items():
    mc_share = r.fleet[:, :, 0, 0] / r.fleet[:, :, :, 0].sum(axis=2)
    print(f"seed {s}: national median {np.median(r.draws[:, :, :, 0].sum(axis=(1, 2))) / 1e6:6.1f} M L | "
          f"min motorbike share of fleet {mc_share.min():.2f} | "
          f"fleet sum = official total: {np.allclose(r.fleet[:, :, :, 0].sum(axis=2), base.vehicles_k.values * 1000)}")
""")

code("""
# Parameter independence: assumptions are sampled independently. Check that no two sampled
# parameters are accidentally correlated (|r| should be ~0 for independent draws).
pm = pd.DataFrame(res[1].params)
c = pm.corr().where(~np.eye(len(pm.columns), dtype=bool)).abs()
print("largest |correlation| between any two sampled parameters:", round(float(c.max().max()), 3))
""")

# =============================================================================================
md("""
## 9. Baseline models

A model only adds value if it beats simple alternatives. Three comparisons:

1. **Driver forecasts** - ETS vs naive (flat) vs drift on the 2023-2025 hold-out.
2. **H2 explanatory model** - leave-one-out cross-validation against a mean-only baseline.
3. **Demand model** - Monte Carlo vs (a) a deterministic point estimate, (b) the population-share rule of thumb.
""")

code("""
# 9.1 Forecast baselines (median province MAPE and national MAPE on the hold-out)
bs = fc["backtest_summary"].set_index("variable")
bs
""")

code("""
# 9.2 Leave-one-out cross-validation for the density model: does adding predictors beat a
#     mean-only baseline? (LOO written by hand: each province is predicted by a model fitted on the other 33)
def loo_rmse(xcols):
    errs = []
    for i in range(len(dd)):
        train = dd.drop(dd.index[i]); test = dd.iloc[[i]]
        if xcols:
            m = sm.OLS(train["log_density"], sm.add_constant(train[xcols])).fit()
            pred = m.predict(sm.add_constant(test[xcols], has_constant="add"))
        else:
            pred = np.array([train["log_density"].mean()])     # baseline: predict the mean
        errs.append(float(test["log_density"].iloc[0] - np.asarray(pred)[0]))
    return float(np.sqrt(np.mean(np.square(errs))))

pd.DataFrame({"model": ["mean only (baseline)", "urban share", "income", "income + urban share",
                        "income + income^2 + urban share"],
              "LOO RMSE (log density)": [loo_rmse([]), loo_rmse(["urban_share_model"]),
                                         loo_rmse(["log_grdp"]), loo_rmse(["log_grdp", "urban_share_model"]),
                                         loo_rmse(["log_grdp", "log_grdp_sq", "urban_share_model"])]})
# Urban share alone beats the mean baseline; adding a LINEAR income term does not improve out-of-sample
# error (matches the linear H2 result). Whether the quadratic term generalises is shown in the last row.
""")

code("""
# 9.3 Full Monte Carlo run and comparison with both demand baselines
sim = demand.simulate(base, fc["drivers"], fc["growth"], lube, split, n=10_000)
summ = demand.summarise(sim, base)
cmp, metrics = demand.compare_baselines(base, fc["drivers"], fc["growth"], lube, split, summ)
pd.Series(metrics).round(2)
""")

code("""
# Model vs population-share allocation, province by province (2025, million litres)
cmpv = cmp.merge(base[["province_code", "province_en"]], on="province_code")
# % difference of the model from the rule of thumb: > 0 = rule of thumb UNDER-estimates the province
s = cmpv.sort_values("diff_vs_population_share_pct")
fig, ax = plt.subplots(figsize=(8, 7))
ax.barh(s["province_en"], s["diff_vs_population_share_pct"],
        color=[SEG_COLORS["MCO"] if v > 0 else SEG_COLORS["PCMO"] for v in s["diff_vs_population_share_pct"]])
ax.axvline(0, color=INK2, lw=1)
ax.set_xlabel("Model vs population-share baseline, 2025 (%)  - blue: rule of thumb under-estimates")
ax.tick_params(axis="y", labelsize=8); plt.tight_layout(); plt.show()
cmpv.sort_values("diff_vs_population_share_pct")[["province_en", "baseline_population_share", "model_mc_p50",
                                                  "diff_vs_population_share_pct"]].iloc[[0, 1, 2, -3, -2, -1]]
""")

code("""
# Provinces the rule of thumb would mis-prioritise (top 10 by 2025 volume)
top_model = set(cmpv.nsmallest(10, "rank_model_mc_p50").province_en)
top_pop = set(cmpv.nsmallest(10, "rank_baseline_population_share").province_en)
print("in model top 10 only           :", sorted(top_model - top_pop))
print("in population-share top 10 only:", sorted(top_pop - top_model))
""")

code("""
# Final model output: national total with 95% interval, and the priority ranking
nat_out = summ["national"].query("segment == 'TOTAL'")[["year", "litres_p025", "litres_p50", "litres_p975"]]
display(nat_out.assign(**{c: nat_out[c] / 1e6 for c in ["litres_p025", "litres_p50", "litres_p975"]}))
summ["priority"].merge(base[["province_code", "province_en"]], on="province_code")[
    ["priority_rank", "tier", "province_en", "litres_2025_p50", "increment_2025_2028_p50", "prob_top10",
     "growth_focus_segment"]].head(10)
""")

# =============================================================================================
md("""
## 10. Summary and next steps
""")

code("""
# Key results, printed from the objects above (no hand-typed numbers)
tests, det = statistics.run_all(base, py)
t25 = summ["national"].query("segment == 'TOTAL' and year == 2025").iloc[0]
print(f"National demand potential 2025: {t25.litres_p50 / 1e6:.0f} M L (95% {t25.litres_p025 / 1e6:.0f}-{t25.litres_p975 / 1e6:.0f})")
for _, r in tests.iterrows():
    print(f"{r.test[:2]}: p(Holm) = {r.p_holm:.3f} -> {'reject H0' if r.reject_h0 else 'fail to reject H0'}")
print("Assumption checks passed:", int(checks.passed.sum()), "of", len(checks))
fb = fc["backtest_summary"].set_index("variable")
for v, r in fb.iterrows():
    print(f"Forecast {v}: chosen {r.chosen_method}, median province MAPE "
          f"{r[f'median_province_mape_{r.chosen_method}']:.1f}%, national MAPE {r[f'national_mape_{r.chosen_method}']:.1f}%")
print(f"Model vs population share: mean |difference| {metrics['mean_abs_diff_vs_population_share_pct']:.0f}%, "
      f"{metrics['top10_changed_vs_population_share']} top-10 provinces change")
""")

md("""
**Next steps (weeks 3-4 of the plan)**
* Narrow the most influential assumption (motorbike oil-change interval) with a small workshop survey.
* Replace the modelled car / motorbike split if province-level car registrations become available.
* Finish the dashboard (Streamlit app done; Power BI build guide in `docs/powerbi_guide.md`), write the
  technical report and the executive deck from `reports/findings.md`.
* Production run: `python -m vnlube.pipeline` (weekly scheduled task) keeps all of the above current.
""")

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"] = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                  "language_info": {"name": "python"}}
out = Path(__file__).parent / "01_preliminary_model.ipynb"
nbf.write(nb, out)
print("wrote", out)

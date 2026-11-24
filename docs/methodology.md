# Methodology

## 1. KPIs and hypotheses (defined before modelling)

| KPI | Definition | Target (from proposal) |
|---|---|---|
| Demand potential | Litres/year by province x segment, median and 95% interval of 10,000 draws | Reported for all 34 provinces x 3 segments |
| Forecast accuracy | Back-test: fit <= 2022, forecast 2023-2025; MAPE | <= 10% national, <= 15% median province |
| Refresh effort | Time from NSO release to updated dashboard | < 15 minutes, no manual steps |
| Decision output | Ranked priority provinces with growth-focus segment and P(top 10) | Top 10 (tier A) |

Hypotheses are tested **only on observed official data** (testing the model's own outputs would be circular):

- **H1** - vehicle density (registered vehicles per 1,000 people, 2025) differs between the 6 regions.
  Kruskal-Wallis because there are only 3-9 provinces per region and no normality assumption; effect size
  epsilon squared. One-way ANOVA is reported alongside for reference.
- **H2** - vehicle density increases with GRDP per capita. OLS `log(density) ~ log(GRDP pc) + urban share`
  with HC3 robust standard errors; one-sided test on the income elasticity. Robustness: refit without provinces
  with Cook's distance > 4/n; Spearman rank correlation without controls.
- **H3** - provinces with lower density grow faster in real GRDP (2022-2025), i.e. have catch-up headroom.
  One-sided Spearman test with a 5,000-sample bootstrap confidence interval.
- Holm correction across the three primary tests (alpha = 0.05). A null result is reported as such.

### Assumption checks and remedies (`statistics.assumption_checks`, notebook section 8)

| Model | Check | Remedy if it fails |
|---|---|---|
| H2 OLS | Shapiro-Wilk, Jarque-Bera (residual normality) | HC3 / bootstrap inference |
| H2 OLS | Breusch-Pagan (homoscedasticity) | HC3 robust standard errors (always used) |
| H2 OLS | Ramsey RESET (functional form) | flexible specifications; **failed**, so the exploratory quadratic model (`h2_nonlinear`) was added |
| H2 OLS | VIF (multicollinearity) | drop or combine predictors |
| H2 OLS | Cook's distance (influence) | refit without influential provinces |
| H2 OLS | Durbin-Watson along north-south order (spatial dependence) | **failed**, so region fixed effects and region-clustered standard errors were added |
| H1 Kruskal-Wallis | Brown-Forsythe (equal spread), minimum group size | read the result as "distributions differ" |
| Forecasts | bias of hold-out errors (t-test) | freight is biased low, so the HDMO growth forecast is labelled conservative |
| Monte Carlo | convergence in n, seed stability, parameter independence, fleet conservation | more draws / fix the allocation |

### Baselines (notebook section 9, `demand.compare_baselines`)

- **Forecasts:** naive (flat) and drift baselines. ETS is used only if it wins on the hold-out.
- **Explanatory model:** a mean-only predictor, compared by leave-one-out RMSE.
- **Demand:** (a) a deterministic run at the most-likely assumptions, and (b) the population-share rule of
  thumb, given the model's own national total so that only the provincial allocation is compared.

## 2. Data preparation (DuckDB SQL, `sql/`)

1. **Staging** - every JSON-stat file becomes rows of `(source, geography label, period label, indicator, value)`.
2. **Name harmonisation** - `name_key()` folds diacritics, the two look-alike capital D letters (U+0110 "Đ"
   and U+00D0 "Ð", both used by NSO), the "TP." / "Thành phố" prefixes and spacing into an ASCII key.
   Aliases cover renames (Thừa Thiên Huế -> Huế). `dq_unmatched_geography` must be empty.
3. **Periods** - "Sơ bộ 2025" -> 2025 + status *preliminary*; "Ước tính 2025" -> *estimate*. Impossible years are
   caught in `dq_bad_years`.
4. **Missingness** - each gap is classified by position in its series. **Structural** gaps fall before a unit
   existed or after it was abolished, e.g. Đắk Nông before 2004 and Hà Tây after 2008; they are left empty.
   **Random** gaps are interior; they are linearly interpolated and flagged (`has_imputed_values`).
   Nothing is dropped blindly.
5. **63 -> 34 roll-up** - additive measures are summed and GRDP per capita is population-weighted, from 2008
   onwards (the first year with stable boundaries). A completeness flag checks every component province reported.
   **Validation:** for 2020-2025 the roll-up reproduces NSO's official 34-province population, freight and GRDP
   per capita to within 0.01% (`dq_reconciliation`, enforced by a test).
6. **Series breaks** - the 2025 commune-level reform reclassified urban areas, so the 2024 urban share is used in
   models (`dq_series_breaks`).
7. **Outliers** - robust z-scores (median / MAD) on density and accident rates, |z| > 3.5. Flagged provinces
   (Thái Nguyên and Lạng Sơn have accident rates about 2.5x the national rate) are real observations; they are
   kept and reported. Influential points in H2 are handled with Cook's distance and a robustness refit.
8. **Consistency checks** - provincial vehicle counts must add up to the published regional and national totals
   (`dq_vehicle_totals`). Accidents per 10,000 vehicles x vehicles must reproduce the accident counts
   (`accident_count_consistency` is about 1.00).

## 3. Demand model (`src/vnlube/demand.py`)

**Fleet split (2025).** `V_p` is the official cars + motorbikes count for province *p*.

```
w_p  = V_p * (GRDPpc_p / GRDPpc_national) ^ eps          car-allocation weight
PC_p = C * s_pass * w_p / sum(w)                         passenger cars
CV_p = C * (1 - s_pass) * [a * F_p/sum(F) + (1 - a) * w_p/sum(w)]   commercial vehicles (F = road freight)
MC_p = V_p - PC_p - CV_p                                 motorbikes
```

`C` (national cars), `s_pass`, `eps` and `a` are drawn from their ranges in `fleet_split_assumptions.csv`.
By construction `MC + PC + CV = V_p` in every draw, which a test enforces.

**Litres.** `L = fleet x active_share x annual_km / drain_interval_km x fill_litres x other_fluids_factor`,
each from a triangular distribution (`lubricant_assumptions.csv`). National parameters are shared by all
provinces within a draw, so provincial results stay mutually consistent and add up to the national
distribution.

**Forecast to 2028.** Motorbikes and cars grow with forecast population x (1 + real GRDP-per-capita growth)
raised to a segment elasticity: about 0 for motorbikes (saturated) and about 1.2 for cars. Commercial
vehicles grow with forecast road freight raised to an elasticity of about 0.7. Population and freight are
forecast with damped-trend ETS or naive drift, whichever has the lower back-test MAPE. Real GRDP-per-capita
growth is the 2022-2025 average from the official index, shrunk 50% towards the national rate.

**Priority score.** In every draw, `0.6 x percentile rank(2025 litres) + 0.4 x percentile rank(added litres
2025->2028)`. The median gives the ranking (tier A = top 10, B = 11-22, C = rest). The share of draws in which a
province is in the top 10 is reported as *P(top 10)*, so sales can see which picks are robust.

**Sensitivity.** Spearman correlation of every sampled parameter with the national 2025 total identifies which
assumptions are worth refining.

**Triangulation.** The national total is compared with published market estimates. Automotive engine oils are
about 215 M L (2024) and all lubricants including industrial are 321-380 M L (2025). These benchmarks are never
model inputs.

## 4. Why DuckDB

The data are megabytes, not gigabytes. DuckDB was chosen because it keeps the transformation layer as
version-controlled SQL with window functions (interpolation, series bounds, breaks), runs in-process with no
server, and lets Power BI or any SQL client query the same warehouse file. It also scales unchanged if monthly
series are added.

"""Hypothesis tests and model-assumption checks on OBSERVED official data.

Hypotheses are tested only on observed NSO data, never on the demand model's own outputs
(testing model outputs would be circular: they reflect our assumptions, not the world).

H1  Vehicle density (vehicles per 1,000 people, 2025) differs across the 6 regions.
    Kruskal-Wallis (non-parametric; n = 34 with 3-9 provinces per region), effect size epsilon^2.
H2  Vehicle density rises with income: OLS log(density) ~ log(GRDP per capita) + urban share,
    HC3 robust errors; one-sided test of beta_income > 0; robustness refit without
    influential provinces (Cook's D > 4/n).
H3  Catch-up: provinces with LOWER vehicle density grow faster in real GRDP (2022-2025)
    -> more headroom for new vehicles. One-sided Spearman test of rho < 0.
Holm correction is applied across the three primary tests (family-wise alpha = 0.05).

Assumption checks (``assumption_checks``) document whether each method's assumptions hold:
residual normality, homoscedasticity, multicollinearity, functional form, influence, and
equal spread across groups for Kruskal-Wallis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan, linear_reset
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor

ALPHA = 0.05            # family-wise significance level
ROBUST_Z_CUTOFF = 3.5   # Iglewicz & Hoaglin's recommended cut-off for modified z-scores


# ----------------------------------------------------------------------------- outliers
def robust_z(x: pd.Series) -> pd.Series:
    """Modified z-score using the median and MAD (not distorted by the outliers themselves)."""
    med = x.median()
    mad = (x - med).abs().median() * 1.4826   # 1.4826 makes MAD consistent with the SD for normal data
    return (x - med) / mad


def outliers(base: pd.DataFrame) -> pd.DataFrame:
    """Flag provinces whose vehicle density or accident rate is extreme (|robust z| > 3.5).

    Flagged provinces are REPORTED, not removed: they are genuine official figures.
    """
    out = base[["province_code", "province_en", "vehicles_per_1000", "accidents_per_10k"]].copy()
    out["z_density"] = robust_z(out["vehicles_per_1000"])
    out["z_accident_rate"] = robust_z(out["accidents_per_10k"])
    out["flag"] = np.select(
        [out["z_density"].abs() > ROBUST_Z_CUTOFF, out["z_accident_rate"].abs() > ROBUST_Z_CUTOFF],
        ["density outlier", "accident-rate outlier"], default="")
    return out


# ----------------------------------------------------------------------------- features
def real_growth(py: pd.DataFrame, start: int = 2022, end: int = 2025) -> pd.Series:
    """Average annual real GRDP growth per province from the official index (prev. year = 100).

    Geometric mean of the yearly growth factors, e.g. indices 107, 105, 108 -> about 6.7% a year.
    """
    idx = py[(py["year"] >= start) & (py["year"] <= end)].pivot(
        index="province_code", columns="year", values="real_grdp_index")
    return (idx / 100).prod(axis=1) ** (1 / idx.shape[1]) - 1


def h2_design(base: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """Build the H2 regression data: y = log density, X = const + log GRDP pc + urban share."""
    d = base.assign(log_density=np.log(base["vehicles_per_1000"]),
                    log_grdp=np.log(base["grdp_pc_mvnd"]))
    X = sm.add_constant(d[["log_grdp", "urban_share_model"]])
    return d["log_density"], X, d


# ----------------------------------------------------------------------------- hypotheses
def h1_regions(base: pd.DataFrame) -> dict:
    """H1: Kruskal-Wallis test of vehicle density across regions."""
    groups = [g["vehicles_per_1000"].values for _, g in base.groupby("region_en")]
    h, p = stats.kruskal(*groups)
    n, k = len(base), len(groups)
    eps2 = (h - k + 1) / (n - k)               # epsilon-squared effect size (0 = none, 1 = total)
    f, p_anova = stats.f_oneway(*groups)       # parametric counterpart, reported for comparison
    med = base.groupby("region_en")["vehicles_per_1000"].median().sort_values(ascending=False)
    return {"test": "H1 density differs across regions", "method": "Kruskal-Wallis",
            "statistic": h, "p_value": p, "effect_size": eps2, "effect_name": "epsilon^2",
            "anova_F": f, "anova_p": p_anova, "region_medians": med.round(0).to_dict(), "n": n}


def h2_income(base: pd.DataFrame) -> dict:
    """H2: income elasticity of vehicle density, controlling for urbanisation."""
    y, X, d = h2_design(base)
    fit = sm.OLS(y, X).fit(cov_type="HC3")     # HC3: robust to heteroscedasticity in small samples
    beta, se = fit.params["log_grdp"], fit.bse["log_grdp"]
    p_one = stats.norm.sf(beta / se)           # one-sided: H_a is beta > 0
    ci = fit.conf_int().loc["log_grdp"].tolist()

    # robustness: drop influential provinces (Cook's distance > 4/n) and refit
    infl = sm.OLS(y, X).fit().get_influence()
    cooks = pd.Series(infl.cooks_distance[0], index=d["province_code"])
    influential = cooks[cooks > 4 / len(d)].index.tolist()
    keep = ~d["province_code"].isin(influential)
    fit_r = sm.OLS(y[keep], X[keep]).fit(cov_type="HC3")

    # neighbouring provinces are similar (spatial correlation): cluster standard errors by region
    fit_cl = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["region_en"])[0]})

    # simple rank correlation without the urban control, to show the confounding
    rho, p_rho = stats.spearmanr(d["grdp_pc_mvnd"], d["vehicles_per_1000"])
    return {"test": "H2 density increases with GRDP per capita", "method": "OLS log-log, HC3, one-sided",
            "statistic": beta / se, "p_value": p_one, "effect_size": beta, "effect_name": "income elasticity",
            "ci95": ci, "r2": fit.rsquared, "beta_urban": fit.params["urban_share_model"],
            "p_urban": fit.pvalues["urban_share_model"], "influential": influential,
            "beta_robust": fit_r.params["log_grdp"], "p_robust_two_sided": fit_r.pvalues["log_grdp"],
            "p_cluster_region": fit_cl.pvalues["log_grdp"],
            "spearman_rho": rho, "spearman_p": p_rho, "n": len(d), "summary": fit.summary().as_text(),
            "nonlinear": h2_nonlinear(base)}


def h2_nonlinear(base: pd.DataFrame) -> dict:
    """Exploratory follow-up to H2 (the RESET test rejects the linear log-log form).

    Adds a squared income term: log(density) ~ log g + (log g)^2 + urban share. The income
    elasticity then depends on the income level: d log(density) / d log g = b1 + 2 * b2 * log g.
    It is evaluated (with a delta-method Wald test) at the 10th, 50th and 90th income percentile.
    A negative b2 means an inverted U: density first rises with income, then falls.
    """
    _, _, d = h2_design(base)
    d = d.assign(log_grdp_sq=d["log_grdp"] ** 2)
    fit = sm.OLS(d["log_density"], sm.add_constant(d[["log_grdp", "log_grdp_sq", "urban_share_model"]])).fit(
        cov_type="HC3")
    b1, b2 = fit.params["log_grdp"], fit.params["log_grdp_sq"]
    turning = float(np.exp(-b1 / (2 * b2))) if b2 != 0 else float("nan")   # GRDP pc where the slope is 0
    effects = []
    for q in (0.10, 0.50, 0.90):
        x = float(d["log_grdp"].quantile(q))
        t = fit.t_test(f"log_grdp + {2 * x} * log_grdp_sq = 0")      # elasticity at this income level
        effects.append({"percentile": int(q * 100), "grdp_pc_mvnd": float(np.exp(x)),
                        "elasticity": float(np.squeeze(t.effect)), "p_value": float(np.squeeze(t.pvalue))})
    return {"b_log_grdp": b1, "b_log_grdp_sq": b2, "p_sq": float(fit.pvalues["log_grdp_sq"]),
            "turning_point_grdp_pc": turning, "adj_r2": fit.rsquared_adj,
            "n_above_turning": int((d["grdp_pc_mvnd"] > turning).sum()), "elasticity_at": effects}


def h3_catch_up(base: pd.DataFrame, py: pd.DataFrame, n_boot: int = 5000) -> dict:
    """H3: Spearman correlation between vehicle density and real GRDP growth (expect rho < 0)."""
    g = real_growth(py).rename("real_growth")
    d = base.set_index("province_code").join(g)
    rho, p_two = stats.spearmanr(d["vehicles_per_1000"], d["real_growth"])
    p_one = p_two / 2 if rho < 0 else 1 - p_two / 2   # convert to the one-sided p for rho < 0
    # percentile bootstrap CI for rho (resample provinces with replacement)
    rng = np.random.default_rng(7)
    boots = []
    for _ in range(n_boot):
        s = d.sample(len(d), replace=True, random_state=rng.integers(1e9))
        boots.append(stats.spearmanr(s["vehicles_per_1000"], s["real_growth"])[0])
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return {"test": "H3 lower-density provinces grow faster (headroom)", "method": "Spearman, one-sided, bootstrap CI",
            "statistic": rho, "p_value": p_one, "effect_size": rho, "effect_name": "Spearman rho",
            "ci95": [lo, hi], "n": int(d["real_growth"].notna().sum())}


def run_all(base: pd.DataFrame, py: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Run H1-H3, apply the Holm correction, return (summary table, detailed results by test)."""
    res = [h1_regions(base), h2_income(base), h3_catch_up(base, py)]
    p_adj = multipletests([r["p_value"] for r in res], method="holm")[1]
    for r, pa in zip(res, p_adj):
        r["p_holm"] = pa
        r["reject_h0"] = bool(pa < ALPHA)
    table = pd.DataFrame([{k: r.get(k) for k in
                           ["test", "method", "n", "statistic", "p_value", "p_holm", "reject_h0",
                            "effect_name", "effect_size", "ci95"]} for r in res])
    return table, {r["test"][:2]: r for r in res}


# ----------------------------------------------------------------------------- assumption checks
def assumption_checks(base: pd.DataFrame) -> pd.DataFrame:
    """Check the assumptions behind H1 and H2; one row per check with a pass/fail verdict.

    A failed check does not invalidate the result automatically. The 'consequence' column states
    how the method copes (e.g. HC3 errors make the OLS test valid under heteroscedasticity).
    """
    rows = []
    y, X, d = h2_design(base)
    ols = sm.OLS(y, X).fit()
    resid = ols.resid

    # 1. normality of OLS residuals (needed for exact small-sample t-tests)
    w, p = stats.shapiro(resid)
    rows.append(("H2 OLS", "Residuals normally distributed", "Shapiro-Wilk", w, p, p > ALPHA,
                 "If violated, rely on HC3 / bootstrap inference rather than exact t-tests"))
    jb, p_jb = stats.jarque_bera(resid)
    rows.append(("H2 OLS", "Residual skewness/kurtosis normal", "Jarque-Bera", jb, p_jb, p_jb > ALPHA,
                 "Large-sample normality check; complements Shapiro-Wilk"))
    # 2. constant error variance
    lm, p_bp, _, _ = het_breuschpagan(resid, X)
    rows.append(("H2 OLS", "Homoscedastic errors", "Breusch-Pagan", lm, p_bp, p_bp > ALPHA,
                 "HC3 robust standard errors are used either way"))
    # 3. correct functional form (no missing non-linearity)
    reset = linear_reset(ols, power=2, use_f=True)
    rows.append(("H2 OLS", "Linear (log-log) functional form", "Ramsey RESET", float(reset.fvalue),
                 float(reset.pvalue), float(reset.pvalue) > ALPHA, "If violated, add non-linear terms"))
    # 4. multicollinearity between predictors
    for i, col in enumerate(X.columns):
        if col == "const":
            continue
        vif = variance_inflation_factor(X.values, i)
        rows.append(("H2 OLS", f"No multicollinearity ({col})", "VIF", vif, np.nan, vif < 5,
                     "VIF < 5 means coefficients are separately identifiable"))
    # 5. influential observations
    cooks = ols.get_influence().cooks_distance[0]
    n_infl = int((cooks > 4 / len(d)).sum())
    rows.append(("H2 OLS", "No single province drives the fit", "Cook's D > 4/n (count)", n_infl, np.nan,
                 n_infl <= 0.1 * len(d), "Robustness refit without influential provinces is reported"))
    # 6. independence: provinces are distinct units (cross-section), checked by residual autocorrelation
    #    in province-code order (a crude proxy for spatial ordering, codes run north -> south)
    dw = sm.stats.stattools.durbin_watson(resid)
    rows.append(("H2 OLS", "Independent errors (north-south order)", "Durbin-Watson", dw, np.nan,
                 1.5 < dw < 2.5, "Values near 2 mean no serial / spatial correlation along the country"))

    # Kruskal-Wallis compares medians only if the group distributions have similar spread
    groups = [g["vehicles_per_1000"].values for _, g in base.groupby("region_en")]
    lev, p_lev = stats.levene(*groups, center="median")
    rows.append(("H1 Kruskal-Wallis", "Similar spread across regions", "Brown-Forsythe (Levene, median)",
                 lev, p_lev, p_lev > ALPHA,
                 "If violated, H1 is read as 'distributions differ', not strictly 'medians differ'"))
    sizes = [len(g) for g in groups]
    rows.append(("H1 Kruskal-Wallis", "At least 3 observations per group", "min group size", min(sizes),
                 np.nan, min(sizes) >= 3, "Chi-square approximation of H needs reasonable group sizes"))

    return pd.DataFrame(rows, columns=["model", "assumption", "check", "statistic", "p_value", "passed",
                                       "consequence"])

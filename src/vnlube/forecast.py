"""Province driver forecasts (population, road freight, real GRDP per capita growth) to 2028.

Population and road freight
    Three candidate models are fitted per province on log levels (2011-2025):
      * ``naive``      - baseline: the last observed value stays flat ("nothing changes"),
      * ``drift``      - baseline: continue the average historical growth rate,
      * ``ets_damped`` - Holt exponential smoothing with a damped additive trend.
    All are back-tested on a hold-out (fit on years <= 2022, forecast 2023-2025). The method
    with the lowest MEDIAN province MAPE is refitted on all years and used for the forecast,
    so a sophisticated model is only used when it beats the simple baselines.

Real GRDP per capita growth
    Average 2022-2025 real GDP growth (official index, previous year = 100) minus population
    growth, then shrunk 50% towards the national rate. With only four years per province the
    raw provincial rates are noisy; shrinkage trades a little bias for much lower variance.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from .config import BASE_YEAR, FORECAST_TO
from .statistics import real_growth

HORIZON = FORECAST_TO - BASE_YEAR       # number of years to forecast (2026-2028 -> 3)
BACKTEST_CUTOFF = 2022                  # last year of the training window in the back-test
SHRINKAGE = 0.5                         # weight on the province's own growth rate (rest = national)


def _ets(y: pd.Series, h: int) -> np.ndarray:
    """Damped-trend exponential smoothing on log values; returns h forecasts in levels."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # statsmodels warns on short series; the fit is still valid
        model = ExponentialSmoothing(np.log(y.values), trend="add", damped_trend=True,
                                     initialization_method="estimated").fit(optimized=True)
    return np.exp(model.forecast(h))


def _drift(y: pd.Series, h: int) -> np.ndarray:
    """Random walk with drift: extend the average log growth between first and last year."""
    v = np.log(y.values)
    slope = (v[-1] - v[0]) / (len(v) - 1)
    return np.exp(v[-1] + slope * np.arange(1, h + 1))


def _naive(y: pd.Series, h: int) -> np.ndarray:
    """Naive baseline: the last observed value repeated (no growth)."""
    return np.full(h, float(y.values[-1]))


def _mape(actual, pred) -> float:
    """Mean absolute percentage error in percent."""
    actual, pred = np.asarray(actual), np.asarray(pred)
    return float(np.mean(np.abs(pred / actual - 1)) * 100)


# candidate models; order only matters for ties (the first listed wins)
METHODS = {"ets_damped": _ets, "drift": _drift, "naive": _naive}


def forecast_series(py: pd.DataFrame, column: str, start: int = 2011) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Back-test every method for one variable, keep the best, refit on all data and forecast.

    Returns (forecast rows 2026-2028, per-province back-test table, chosen method name).
    """
    series, bt = {}, []
    for code, g in py[py["year"] >= start].groupby("province_code"):
        y = g.set_index("year")[column].dropna()
        series[code] = y
        train, test = y[y.index <= BACKTEST_CUTOFF], y[y.index > BACKTEST_CUTOFF]
        row = {"province_code": code, "variable": column, "actual_test_sum": test.sum()}
        for name, fn in METHODS.items():
            pred = fn(train, len(test))
            row[f"mape_{name}"] = _mape(test, pred)
            row[f"pred_test_sum_{name}"] = pred.sum()   # kept to compute the national-level MAPE
        bt.append(row)
    bt = pd.DataFrame(bt)

    # model selection on out-of-sample accuracy (median is robust to one badly-behaved province)
    chosen = min(METHODS, key=lambda m: bt[f"mape_{m}"].median())

    rows = []
    for code, y in series.items():
        fc = METHODS[chosen](y, HORIZON)                 # refit on the full 2011-2025 history
        for i, year in enumerate(range(BASE_YEAR + 1, FORECAST_TO + 1)):
            rows.append({"province_code": code, "year": year, column: fc[i]})
    bt["chosen_method"] = chosen
    return pd.DataFrame(rows), bt, chosen


def _backtest_summary(bt: pd.DataFrame) -> pd.DataFrame:
    """One row per variable: median province MAPE and national MAPE for each method."""
    out = []
    for var, g in bt.groupby("variable"):
        row = {"variable": var, "chosen_method": g["chosen_method"].iloc[0]}
        for m in METHODS:
            row[f"median_province_mape_{m}"] = g[f"mape_{m}"].median()
            # national MAPE: compare the sum of province forecasts with the national actual
            row[f"national_mape_{m}"] = abs(g[f"pred_test_sum_{m}"].sum() / g["actual_test_sum"].sum() - 1) * 100
        out.append(row)
    return pd.DataFrame(out)


def run(py: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Forecast all drivers. Returns drivers (2025 actual + 2026-2028), growth, back-test tables."""
    pop_fc, pop_bt, _ = forecast_series(py, "population_k")
    fr_fc, fr_bt, _ = forecast_series(py, "road_freight_kt")

    # real GRDP per capita growth = (1 + real GDP growth) / (1 + population growth) - 1
    g = real_growth(py)
    pop = py.pivot(index="province_code", columns="year", values="population_k")
    pop_growth = (pop[2025] / pop[2022]) ** (1 / 3) - 1
    pc_growth = (1 + g) / (1 + pop_growth) - 1
    w = pop[2025] / pop[2025].sum()                      # population weights for the national rate
    national = float((pc_growth * w).sum())
    growth = pd.DataFrame({"real_gdp_growth": g, "pop_growth": pop_growth,
                           "real_gdp_pc_growth_raw": pc_growth,
                           "real_gdp_pc_growth": SHRINKAGE * pc_growth + (1 - SHRINKAGE) * national}).reset_index()

    # stack the observed base year on top of the forecasts so ratios to 2025 are easy downstream
    drivers = pop_fc.merge(fr_fc, on=["province_code", "year"])
    base = py[py["year"] == BASE_YEAR][["province_code", "year", "population_k", "road_freight_kt"]]
    drivers = pd.concat([base, drivers]).sort_values(["province_code", "year"]).reset_index(drop=True)
    backtest = pd.concat([pop_bt, fr_bt])
    return {"drivers": drivers, "growth": growth, "backtest": backtest,
            "backtest_summary": _backtest_summary(backtest)}

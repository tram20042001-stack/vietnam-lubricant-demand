import numpy as np
import pandas as pd
import pytest

from vnlube import demand, forecast
from vnlube import data_access as da
from vnlube.config import WAREHOUSE

pytestmark = pytest.mark.skipif(not WAREHOUSE.exists(), reason="warehouse not built")


@pytest.fixture(scope="module")
def sim():
    base, py = da.province_base(), da.province_year()
    fc = forecast.run(py)
    lube = da.triangular_table("ref_lubricant_assumptions")
    split = da.triangular_table("ref_fleet_split_assumptions")
    res = demand.simulate(base, fc["drivers"], fc["growth"], lube, split, n=500, seed=1)
    return base, res, demand.summarise(res, base)


def test_fleet_split_conserves_official_totals(sim):
    base, res, _ = sim
    fleet25 = res.fleet[:, :, :, 0].sum(axis=2)                     # MC + PC + CV, base year
    assert np.allclose(fleet25, base["vehicles_k"].to_numpy() * 1000, rtol=1e-9)


def test_demand_positive_and_intervals_ordered(sim):
    _, res, out = sim
    assert (res.draws > 0).all()
    d = out["demand"]
    assert (d.litres_p025 <= d.litres_p50).all() and (d.litres_p50 <= d.litres_p975).all()


def test_national_total_in_plausible_band(sim):
    _, _, out = sim
    n = out["national"].query("segment == 'TOTAL' and year == 2025").iloc[0]
    assert 100e6 < n.litres_p50 < 400e6      # published all-lubricant market estimates: 321-380 M L


def test_priority_table_complete(sim):
    _, _, out = sim
    p = out["priority"]
    assert len(p) == 34 and (p.tier == "A").sum() == 10 and p.prob_top10.between(0, 1).all()


def test_baselines_comparable(sim):
    """Population-share baseline uses the model's national total, so the totals must match."""
    base, _, out = sim
    py = da.province_year()
    fc = forecast.run(py)
    lube = da.triangular_table("ref_lubricant_assumptions")
    split = da.triangular_table("ref_fleet_split_assumptions")
    cmp, m = demand.compare_baselines(base, fc["drivers"], fc["growth"], lube, split, out)
    nat = out["national"].query("segment == 'TOTAL' and year == 2025").litres_p50.iloc[0]
    assert len(cmp) == 34
    assert abs(cmp["baseline_population_share"].sum() - nat) / nat < 1e-9
    assert m["national_deterministic_ML"] > 0


def test_forecast_beats_or_equals_naive():
    """The chosen forecasting method must never be worse than the naive baseline on the hold-out."""
    bs = forecast.run(da.province_year())["backtest_summary"]
    for _, r in bs.iterrows():
        assert r[f"median_province_mape_{r.chosen_method}"] <= r["median_province_mape_naive"]


def test_tri_handles_degenerate_range():
    row = pd.Series({"low": 1.0, "mode": 1.0, "high": 1.0})
    assert (demand._tri(np.random.default_rng(0), row, 5) == 1.0).all()

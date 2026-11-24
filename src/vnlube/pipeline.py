"""End-to-end pipeline: ingest -> transform -> analyse -> simulate -> export -> report.

    python -m vnlube.pipeline              # check NSO for new releases; rebuild only if something changed
    python -m vnlube.pipeline --force      # rebuild even if no source changed
    python -m vnlube.pipeline --offline    # skip downloading; rebuild from archived raw files
    python -m vnlube.pipeline --profile    # also write ydata-profiling HTML reports
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import time

import duckdb
import pandas as pd

from . import data_access as da
from . import demand, figures, forecast, ingest, report, statistics, transform
from .config import BASE_YEAR, EXPORTS, PROCESSED, REPORTS, WAREHOUSE

log = logging.getLogger("vnlube")
N_DRAWS = 10_000


def _write(tables: dict[str, pd.DataFrame]) -> None:
    """Store every result three ways: CSV (dashboard / Power BI), Parquet (analysis), DuckDB res_* tables."""
    EXPORTS.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    try:
        for name, df in tables.items():
            df.to_csv(EXPORTS / f"{name}.csv", index=False, encoding="utf-8-sig")
            df.to_parquet(PROCESSED / f"{name}.parquet", index=False)
            con.register("tmp_df", df)
            con.execute(f"CREATE OR REPLACE TABLE res_{name} AS SELECT * FROM tmp_df")
            con.unregister("tmp_df")
    finally:
        con.close()


def profile_reports() -> None:
    """Write ydata-profiling HTML reports (distributions, missingness, correlations) for the main marts."""
    from ydata_profiling import ProfileReport   # imported lazily: slow import, only needed with --profile
    out = REPORTS / "profiling"
    out.mkdir(parents=True, exist_ok=True)
    for name, sql in {"province_year": "SELECT * FROM mart_province_year",
                      "vehicles_2025": "SELECT * FROM mart_vehicles_2025"}.items():
        ProfileReport(da.query(sql), title=f"Profile - {name}", minimal=True,
                      progress_bar=False).to_file(out / f"{name}.html")


def analyse_and_export(n_draws: int = N_DRAWS) -> dict:
    """Everything after the warehouse is built: statistics, forecasts, simulation, exports, report."""
    # 1. inputs from the warehouse
    base, py = da.province_base(), da.province_year()
    dim = da.query("SELECT * FROM mart_dim_province")
    lube = da.triangular_table("ref_lubricant_assumptions")
    split = da.triangular_table("ref_fleet_split_assumptions")
    bench = da.triangular_table("ref_market_benchmarks")

    # 2. statistics on observed data: hypotheses, their assumption checks, outliers
    tests, details = statistics.run_all(base, py)
    checks = statistics.assumption_checks(base)
    outl = statistics.outliers(base)

    # 3. driver forecasts (with back-tested model choice) and the Monte Carlo demand model
    fc = forecast.run(py)
    sim = demand.simulate(base, fc["drivers"], fc["growth"], lube, split, n=n_draws)
    out = demand.summarise(sim, base)

    # 4. baselines: deterministic point estimate and the population-share rule of thumb
    baselines, baseline_metrics = demand.compare_baselines(base, fc["drivers"], fc["growth"], lube, split, out)

    # 5. export everything for the dashboard / Power BI and write the report
    drivers = fc["drivers"].assign(is_forecast=lambda d: d["year"] > BASE_YEAR)
    tests_out = tests.assign(ci95=tests["ci95"].astype(str))
    dq = {
        "dq_reconciliation": da.query("SELECT * FROM dq_reconciliation"),
        "dq_missingness": da.query("SELECT * FROM dq_missingness"),
        "dq_series_breaks": da.query("SELECT * FROM dq_series_breaks"),
        "dq_vehicle_totals": da.query("SELECT * FROM dq_vehicle_totals"),
    }
    _write({
        "dim_province": dim,
        "fact_province_year": py,
        "fact_vehicles_2025": da.query("SELECT * FROM mart_vehicles_2025"),
        "fact_drivers_forecast": drivers,
        "fact_growth": fc["growth"],
        "fact_demand": out["demand"],
        "national_demand": out["national"],
        "priority": out["priority"],
        "sensitivity": out["sensitivity"],
        "hypothesis_tests": tests_out,
        "assumption_checks": checks,
        "baseline_comparison": baselines,
        "baseline_metrics": pd.DataFrame([baseline_metrics]),
        "outliers": outl,
        "backtest": fc["backtest"],
        "backtest_summary": fc["backtest_summary"],
        "assumptions_lubricant": lube,
        "assumptions_fleet": split,
        "market_benchmarks": bench,
        "national_production": da.query("SELECT * FROM mart_national_production"),
        **dq,
    })
    figs = figures.make_all(base, out["priority"], dim, out["national"], out["sensitivity"], bench,
                            fc["backtest_summary"])
    report.write_findings(base=base, dim=dim, tests=tests, details=details, outl=outl, fc=fc, out=out,
                          bench=bench, dq=dq, n_draws=n_draws, figures=figs, checks=checks,
                          baseline_metrics=baseline_metrics)
    return {"tests": tests, "priority": out["priority"], "national": out["national"]}


def run(force: bool = False, offline: bool = False, profile: bool = False, n_draws: int = N_DRAWS) -> str:
    """Orchestrate one run; returns a one-line outcome that is also logged to reports/run_log.csv."""
    t0 = time.time()
    if offline:
        statuses = {}
    else:
        # a failed download is not fatal: the archived copy from the previous run is used
        statuses = ingest.run()
        if any(s == "failed" for s in statuses.values()):
            log.warning("some downloads failed; continuing with the archived copies of those sources")
    changed = [k for k, v in statuses.items() if v in {"new", "changed"}]
    have_outputs = (EXPORTS / "priority.csv").exists()
    # skip the (relatively expensive) rebuild when NSO published nothing new
    if not (force or offline or changed or not have_outputs):
        outcome = "no new data - outputs unchanged"
    else:
        transform.run()
        analyse_and_export(n_draws)
        if profile:
            profile_reports()
        outcome = f"rebuilt (changed sources: {', '.join(changed) or 'none'})"
    # run metadata: shown in the dashboard header and appended to an audit log
    meta = {"run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "outcome": outcome, "seconds": round(time.time() - t0, 1), "sources": statuses,
            "monte_carlo_draws": n_draws}
    EXPORTS.mkdir(parents=True, exist_ok=True)
    (EXPORTS / "run_metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log_path = REPORTS / "run_log.csv"
    pd.DataFrame([{k: v for k, v in meta.items() if k != "sources"}]).to_csv(
        log_path, mode="a", header=not log_path.exists(), index=False)
    log.info("%s in %.1fs", outcome, meta["seconds"])
    return outcome


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true", help="rebuild even when no source changed")
    p.add_argument("--offline", action="store_true", help="do not download; rebuild from archived raw files")
    p.add_argument("--profile", action="store_true", help="write ydata-profiling reports")
    p.add_argument("--draws", type=int, default=N_DRAWS, help="Monte Carlo draws (default 10,000)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(force=a.force, offline=a.offline, profile=a.profile, n_draws=a.draws)


if __name__ == "__main__":
    main()

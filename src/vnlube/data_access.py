"""Read-only helpers to pull marts and reference tables from the DuckDB warehouse.

Analysis code never touches the raw files: it reads the cleaned, validated marts built by
``transform.py`` so every analysis uses exactly the same harmonised data.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from .config import WAREHOUSE


def query(sql: str) -> pd.DataFrame:
    """Run a SQL query against the warehouse (read-only connection) and return a DataFrame."""
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()                           # release the file so the pipeline can rewrite it


def province_base() -> pd.DataFrame:
    """One row per current province with the 2025 cross-section used by the models.

    Joins the province dimension, the official 2025 vehicle counts and the modelling urban
    share (2024 value, i.e. before the 2025 urban reclassification break).
    """
    return query("""
        SELECT d.province_code, d.province_vi, d.province_en, d.region_vi, d.region_en, d.is_hn_hcmc,
               v.vehicles_k, v.vehicles_per_1000, v.accidents_per_10k, v.deaths_per_10k,
               v.population_k, v.grdp_pc_mvnd, v.road_freight_kt,
               u.urban_share_model, u.had_2025_break
        FROM mart_dim_province d
        JOIN mart_vehicles_2025 v USING (province_code)
        JOIN mart_urban_share_model u USING (province_code)
        ORDER BY d.province_code
    """)


def province_year() -> pd.DataFrame:
    """Province x year panel 2011-2025 (official 34-province series + historical roll-up)."""
    return query("SELECT * FROM mart_province_year ORDER BY province_code, year")


def triangular_table(name: str) -> pd.DataFrame:
    """Return an assumption/benchmark reference table (low / mode / high columns)."""
    return query(f"SELECT * FROM {name}")

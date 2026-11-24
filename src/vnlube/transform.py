"""Transform: raw JSON-stat files -> DuckDB warehouse (staging -> clean -> marts).

Python only does the format conversion (JSON-stat -> one long staging table);
all cleaning, harmonisation and aggregation is SQL in ``sql/`` executed by DuckDB.
"""
from __future__ import annotations

import logging

import duckdb
import pandas as pd

from .config import ROOT, SOURCES, SQL_DIR, WAREHOUSE
from .ingest import raw_path
from .jsonstat import read_jsonstat

log = logging.getLogger(__name__)
# NSO names the geography dimension differently across tables ("Locality", "Province, city",
# "Breakdown"); the time dimension is always "Năm" (year).
GEO_DIMS = {"Địa phương", "Tỉnh, thành phố", "Phân tổ"}
PERIOD_DIMS = {"Năm"}


def staging_frame() -> pd.DataFrame:
    """Stack every raw table into ONE long table with a common schema.

    Columns: sid, geography (p34/p63/national), geo_raw, period_raw, indicator_raw, value,
    flag, geo_order. Labels are kept exactly as published ("raw"); all interpretation
    (names, years, statuses) happens in SQL so it is visible and testable in one place.
    """
    frames = []
    for src in SOURCES:
        path = raw_path(src.sid)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing - run `python -m vnlube.ingest` first")
        df, meta = read_jsonstat(path)
        dims = meta["dimensions"]
        geo = next((d for d in dims if d in GEO_DIMS), None)      # None for national-only tables
        period = next(d for d in dims if d in PERIOD_DIMS)
        # every remaining dimension (e.g. indicator, sex, urban/rural) is folded into one label
        other = [d for d in dims if d not in {geo, period}]
        out = pd.DataFrame({
            "sid": src.sid,
            "geography": src.geography,
            "geo_raw": df[geo] if geo else "CẢ NƯỚC",
            "period_raw": df[period],
            "indicator_raw": df[other].astype(str).agg(" | ".join, axis=1) if other else "",
            "value": df["value"],
            "flag": df["flag"],
        })
        # NSO lists provinces under their region heading; keep the published order for reference
        order = {g: i for i, g in enumerate(dict.fromkeys(out["geo_raw"]))}
        out["geo_order"] = out["geo_raw"].map(order)
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


def run(db_path=WAREHOUSE) -> None:
    """Rebuild the whole warehouse from the raw files (idempotent: safe to run repeatedly)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        # relative paths in the SQL (data/reference/*.csv) resolve against the project root
        con.execute(f"SET file_search_path = '{ROOT.as_posix()}'")
        stg = staging_frame()
        con.register("stg_df", stg)                  # zero-copy view of the DataFrame inside DuckDB
        con.execute("CREATE OR REPLACE TABLE stg_observation AS SELECT * FROM stg_df")
        log.info("staged %d observations from %d sources", len(stg), stg["sid"].nunique())
        # 01_reference -> 02_clean -> 03_marts: file names fix the execution order
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            log.info("running %s", sql_file.name)
            con.execute(sql_file.read_text(encoding="utf-8"))
        for (name,) in con.execute("SELECT table_name FROM information_schema.tables "
                                   "WHERE table_name LIKE 'mart_%' OR table_name LIKE 'dq_%' ORDER BY 1").fetchall():
            n = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
            log.info("  %-34s %6d rows", name, n)
    finally:
        con.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()


if __name__ == "__main__":
    main()

"""Project paths and the catalogue of official data sources."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
REFERENCE = DATA / "reference"
PROCESSED = DATA / "processed"
WAREHOUSE = DATA / "warehouse.duckdb"
MANIFEST = RAW / "manifest.csv"
SQL_DIR = ROOT / "sql"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
EXPORTS = ROOT / "dashboard" / "data"

PXWEB_API = "https://pxweb.nso.gov.vn/api/v1/vi"
PXWEB_UI = "https://pxweb.nso.gov.vn/pxweb/vi"
USER_AGENT = "vnlube-research-pipeline/0.1 (academic capstone)"

BASE_YEAR = 2025          # latest year with official province vehicle counts
FORECAST_TO = 2028        # forecast horizon (3 years: matches a sales planning cycle)

# To add a new source: append a Source(...) below, run `python -m vnlube.ingest --only <sid>`,
# then reference it by sid in sql/03_marts.sql. The table name (e.g. "PL.V14.59.px") and the
# database name are visible in the URL of the table on https://pxweb.nso.gov.vn.


@dataclass(frozen=True)
class Source:
    """One table in the NSO (formerly GSO) PX-Web database."""

    sid: str          # short id: raw file name and staging table name
    db: str           # PX-Web database (theme) name
    table: str        # PX file name inside the database
    title_en: str
    geography: str    # "p34" (post-2025 provinces), "p63" (pre-2025 provinces) or "national"
    api: bool = False  # True if the table is also exposed through the PX-Web JSON API

    @property
    def page_url(self) -> str:
        from urllib.parse import quote
        return f"{PXWEB_UI}/{quote(self.db)}/{quote(self.db)}/{quote(self.table)}/"


SOURCES: list[Source] = [
    # --- 34 provinces (administrative units in force from 1 July 2025) -------------------
    Source("p34_vehicles", "PLV14Y tế, văn hóa và MSDC", "PL.V14.59.px",
           "Total vehicles (cars and motorbikes) and road-accident rates per 10,000 vehicles by province", "p34"),
    Source("p34_accidents", "PLV14Y tế, văn hóa và MSDC", "PL.V14.55.px",
           "Road traffic accidents, deaths and injuries by province", "p34"),
    Source("p34_population", "PLV02Dân số và lao động", "PL.V02.02-04.px",
           "Average population by province, sex and urban/rural", "p34"),
    Source("p34_area", "PLV02Dân số và lao động", "PL.V02.01.px",
           "Area, average population and population density by province", "p34"),
    Source("p34_grdp_pc", "PLV03Tài khoản quốc gia", "PL.V03.02.px",
           "GRDP per capita by province (million VND, current prices)", "p34"),
    Source("p34_grdp_growth", "PLV03Tài khoản quốc gia", "PL.V03.01.px",
           "GRDP growth index at constant 2010 prices by province (previous year = 100)", "p34"),
    Source("p34_income","PLV14Y tế, văn hóa và MSDC", "PL.V14.11.px",
           "Monthly income per capita by income quintile and province (thousand VND)", "p34"),
    Source("p34_road_passengers", "PLV12Vận tải và BCVT", "PL.V12.03.px",
           "Road passengers carried by province", "p34"),
    Source("p34_road_freight", "PLV12Vận tải và BCVT", "PL.V12.07.px",
           "Road freight carried by province", "p34"),
    # --- 63 provinces (historical series, pre-merger) ---------------------------------------
    Source("p63_population", "Dân số và lao động", "V02.03-07.px",
           "Average population by province, sex and urban/rural (1995-2025)", "p63"),
    Source("p63_grdp_pc", "Tài khoản quốc gia", "V03.12.px",
           "GRDP per capita by province (2018-2025)", "p63"),
    Source("p63_road_freight", "Vận tải và Bưu chính viễn thông", "V12.17.px",
           "Road freight carried by province (2000-2025)", "p63"),
    Source("p63_road_passengers", "Vận tải và Bưu chính viễn thông", "V12.07.px",
           "Road passengers carried by province (2000-2025)", "p63"),
    # --- national -------------------------------------------------------------------------
    Source("nat_industrial", "Công nghiệp", "V07.05.px",
           "Main industrial products incl. assembled motorbikes and cars (1995-2025)", "national"),
]

SOURCE_BY_ID = {s.sid: s for s in SOURCES}

# Raw datasets

Untouched downloads from the Vietnam National Statistics Office (NSO) PX-Web database
(<https://pxweb.nso.gov.vn>), produced by `python -m vnlube.ingest`. Each source has its own folder:

| File | What it is |
|---|---|
| `<sid>.json` | The **original download** (JSON-stat, UTF-8), byte-for-byte as served by NSO. Its SHA-256 hash is in `manifest.csv`. |
| `<sid>.csv` | The same table as a flat CSV (one row per cell, original Vietnamese labels, **no cleaning**), so it can be opened in Excel. Columns: the table's dimensions (e.g. `Địa phương`, `Năm`, `Chỉ tiêu`), `value`, `flag`. |
| `<sid>.<date>.prev.json` | A previous release, kept when NSO publishes a revision (only appears after a change). |
| `manifest.csv` | Log of every download attempt: source URL, UTC time, route, SHA-256, size, NSO update date, status (`new` / `changed` / `unchanged` / `failed`). |

| sid | NSO table | Content | Geography | Years | Unit |
|---|---|---|---|---|---|
| p34_vehicles | PL.V14.59 | Registered vehicles (cars + motorbikes); accidents, deaths and injuries per 10,000 vehicles | 34 provinces | 2025 | thousand vehicles |
| p34_accidents | PL.V14.55 | Road accidents, deaths, injuries | 34 provinces | 2025 | count |
| p34_population | PL.V02.02-04 | Average population: total, male, female, urban, rural | 34 provinces | 2020-2025 | thousand people |
| p34_area | PL.V02.01 | Area, population, density | 34 provinces | 2025 | km², thousand, people/km² |
| p34_grdp_pc | PL.V03.02 | GRDP per capita, current prices | 34 provinces | 2020-2025 | million VND |
| p34_grdp_growth | PL.V03.01 | Real GRDP growth index, constant 2010 prices | 34 provinces | 2020-2025 | previous year = 100 |
| p34_income | PL.V14.11 | Monthly income per capita by quintile | 34 provinces | 2025 | thousand VND |
| p34_road_passengers | PL.V12.03 | Road passengers carried | 34 provinces | 2020-2025 | million trips |
| p34_road_freight | PL.V12.07 | Road freight carried | 34 provinces | 2020-2025 | thousand tonnes |
| p63_population | V02.03-07 | Average population by sex and urban/rural | 63 former provinces | 1995-2025 | thousand people |
| p63_grdp_pc | V03.12 | GRDP per capita | 63 former provinces | 2018-2025 | million VND |
| p63_road_freight | V12.17 | Road freight carried | 63 former provinces | 2000-2025 | thousand tonnes |
| p63_road_passengers | V12.07 | Road passengers carried | 63 former provinces | 2000-2025 | million trips |
| nat_industrial | V07.05 | Main industrial products incl. assembled motorbikes and cars | national | 1995-2025 | thousand units |

Licence: official statistics published for public use under the Law on Statistics of Viet Nam
(No. 89/2015/QH13); cite "National Statistics Office of Viet Nam (NSO), PX-Web database, table <id>,
accessed <date>". No personal data: all values are province or national aggregates.

Known quirks of the raw data (handled in `sql/02_clean.sql`, demonstrated in `notebooks/01_preliminary_model.ipynb`):
look-alike letters `Ð` (U+00D0) vs `Đ` (U+0110) in names; "TP.Hồ Chí Minh" without a space; year labels such
as `Sơ bộ 2025` (preliminary) and `Ước tính 2025` (estimate); `..` cells for units that did not exist yet
(e.g. Đắk Nông before 2004) or no longer existed (Hà Tây after 2008); an unallocated `Khác` row in the
accident table; NSO "updated" date `9999-12-31` on some tables (placeholder).

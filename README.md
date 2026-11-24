# Vietnam Lubricant Demand Potential Monitor

Province-level market sizing for **motorbike oil (MCO), passenger-car motor oil (PCMO) and heavy-duty
diesel oil (HDMO)** across Vietnam's 34 provinces, built on official statistics from the Vietnam National
Statistics Office (NSO, formerly GSO). The pipeline checks the NSO database for new releases, rebuilds the
model only when a source changed, and refreshes a sales dashboard.

> Latest results: **[reports/findings.md](reports/findings.md)** (regenerated on every run).
> Preliminary model walkthrough: **[notebooks/01_preliminary_model.ipynb](notebooks/01_preliminary_model.ipynb)**.

## Submission checklist

| Requirement | Where |
|---|---|
| **Technical report (10-15 pages)** | [deliverables/technical_report.pdf](deliverables/technical_report.pdf) (11 pages; rebuild: `python -m deliverables.build_report`) |
| **Executive presentation (8-12 slides)** | [deliverables/executive_presentation.pptx](deliverables/executive_presentation.pptx) (11 slides + 2 hidden appendix slides, speaker notes; rebuild: `python -m deliverables.build_deck`) |
| Raw dataset(s) | [data/raw/](data/raw/) - 14 NSO tables, each as the original JSON download **and** a flat CSV; [data/raw/README.md](data/raw/README.md) describes every file; `manifest.csv` holds URL, time and SHA-256 per download |
| Preliminary model file (notebook) | [notebooks/01_preliminary_model.ipynb](notebooks/01_preliminary_model.ipynb) (executed, outputs saved); regenerate with `notebooks/build_notebook.py` |
| Well-commented code | `src/vnlube/*.py` (module docstrings, function docstrings, inline comments on the logic), `sql/*.sql`, `dashboard/app.py` |
| Problem framing | notebook section 1; [docs/methodology.md](docs/methodology.md) section 1 |
| Data cleaning | notebook section 3; [sql/02_clean.sql](sql/02_clean.sql), [sql/03_marts.sql](sql/03_marts.sql); `dq_*` tables |
| EDA | notebook section 4; `reports/profiling/*.html` (ydata-profiling) |
| Feature engineering | notebook section 5 |
| Data transformation & storage | notebook section 6; DuckDB warehouse `data/warehouse.duckdb`, Parquet `data/processed/`, CSV `dashboard/data/` |
| Model preparation | notebook section 7 (assumption ranges, time-based split, Monte Carlo convergence) |
| Model assumption checks | notebook section 8; `statistics.assumption_checks()`; table in `reports/findings.md` |
| Baseline model building | notebook section 9 (naive / drift vs ETS forecasts; mean-only vs regression with leave-one-out CV; deterministic and population-share demand baselines) |

## Business question

*How many litres of MCO / PCMO / HDMO can each province consume per year, how fast is that growing, and
which provinces should the sales team prioritise?* Answered with a quantified 95% interval rather than a
point guess, and refreshed automatically when the government publishes new numbers.

## Architecture

```
NSO PX-Web (pxweb.nso.gov.vn)          data/reference/*.csv
  14 official tables (JSON-stat)         province lists, 63->34 merger map,
        |                                lubricant + fleet-split assumptions,
        v                                market benchmarks (sanity check only)
  ingest.py  -- SHA-256 change detection, manifest.csv, previous release archived
        |                                        |
        v                                        v
  transform.py + sql/*.sql  (DuckDB warehouse: staging -> clean -> marts + dq_* checks)
        |
        +--> statistics.py   hypothesis tests on observed data (H1-H3, Holm), outlier screen
        +--> forecast.py     population / freight / real-income drivers, back-tested model choice
        +--> demand.py       10,000-draw Monte Carlo: fleet split -> litres by province x segment x year
        |
        v
  dashboard/data/*.csv (star schema) --> Streamlit app (dashboard/app.py)  /  Power BI (docs/powerbi_guide.md)
  reports/findings.md + reports/figures/*.png + reports/profiling/*.html
```

## Quick start (Windows, Python 3.11)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m vnlube.pipeline --offline --profile   # rebuild from the archived raw files
.\.venv\Scripts\streamlit.exe run dashboard\app.py                   # open the dashboard
.\.venv\Scripts\jupyter.exe lab notebooks\01_preliminary_model.ipynb # open the preliminary model notebook
.\.venv\Scripts\python.exe -m pytest -q                              # 18 tests: parser, data-quality gates, model invariants, baselines
```

| Command | What it does |
|---|---|
| `python -m vnlube.pipeline` | Download all sources; rebuild **only if** a file changed (normal scheduled mode) |
| `python -m vnlube.pipeline --force` | Download and always rebuild |
| `python -m vnlube.pipeline --offline` | No network; rebuild from `data/raw` |
| `python -m vnlube.pipeline --profile` | Also write ydata-profiling reports to `reports/profiling/` |
| `scripts\register_scheduled_task.ps1` | Register a weekly Windows scheduled task (Monday 07:00) that runs `scripts\run_pipeline.ps1` |

The dashboard also has a **Check NSO for new data** button that runs the same pipeline.

## Data sources

All tables come from the NSO PX-Web database. They are official statistics published for public use under
the Law on Statistics (No. 89/2015/QH13); every table is cited with its URL in `data/raw/manifest.csv`.

| id | NSO table | Content | Years |
|---|---|---|---|
| p34_vehicles | PL.V14.59 | **Registered vehicles (cars + motorbikes) by province**, accident rates per 10,000 vehicles | 2025 |
| p34_accidents | PL.V14.55 | Road accidents, deaths, injuries | 2025 |
| p34_population | PL.V02.02-04 | Population by sex, urban/rural | 2020-2025 |
| p34_area | PL.V02.01 | Area, density | 2025 |
| p34_grdp_pc | PL.V03.02 | GRDP per capita (current prices) | 2020-2025 |
| p34_grdp_growth | PL.V03.01 | Real GRDP growth index | 2020-2025 |
| p34_income | PL.V14.11 | Income per capita by quintile | 2025 |
| p34_road_passengers / p34_road_freight | PL.V12.03 / PL.V12.07 | Road transport volumes | 2020-2025 |
| p63_* | V02.03-07, V03.12, V12.07, V12.17 | Same measures for the 63 former provinces (history) | 2000/2011-2025 |
| nat_industrial | V07.05 | Assembled motorbikes and cars | 1995-2025 |

`p34_*` tables use the 34 provinces in force since 1 July 2025; `p63_*` tables are rolled up to the 34 with
[data/reference/province_63_to_34.csv](data/reference/province_63_to_34.csv). The roll-up is validated
against the official 34-province figures (0.00% difference for population, freight and GRDP per capita).

**No personal data, no employer data.** All figures are province-level aggregates.

## Method in one paragraph

NSO publishes cars and motorbikes as one combined count per province. Each Monte Carlo draw splits that
count into passenger cars, commercial vehicles and motorbikes using national registration anchors, provincial
GRDP per capita and road freight. It then converts each fleet into litres:
`fleet x active share x annual km / oil-change interval x litres per change x other-fluids factor`. Every
assumption has a documented low / most-likely / high range
([lubricant_assumptions.csv](data/reference/lubricant_assumptions.csv),
[fleet_split_assumptions.csv](data/reference/fleet_split_assumptions.csv)), so the outputs carry 95%
intervals. Fleets are projected to 2028 from back-tested population and freight forecasts and from real income
growth. See [docs/methodology.md](docs/methodology.md).

## Repository layout

```
src/vnlube/        ingest, nso_client, jsonstat, transform, statistics, forecast, demand, figures, report, pipeline
sql/               01_reference.sql, 02_clean.sql, 03_marts.sql (all cleaning & harmonisation)
notebooks/         01_preliminary_model.ipynb (executed) + build_notebook.py (generates it)
deliverables/      technical_report.pdf, executive_presentation.pptx + the scripts that generate them
data/raw/          NSO downloads: original JSON-stat + flat CSV per table, manifest.csv, README.md
data/reference/    hand-maintained reference tables with sources
dashboard/         app.py (Streamlit) + data/ (CSV star schema for Streamlit / Power BI)
reports/           findings.md, figures/, profiling/, run_log.csv
docs/              methodology.md, data_dictionary.md, powerbi_guide.md
tests/             pytest suite
scripts/           run_pipeline.ps1, register_scheduled_task.ps1
```

## Changes from the proposal

| Proposal said | What was built | Why |
|---|---|---|
| Vehicle counts from Vietnam Register / Traffic Police | Official NSO table PL.V14.59 (registered cars + motorbikes by province, 2025) | Same underlying registrations, but published as a machine-readable official table; vr.org.vn was unreachable |
| Separate car and motorbike counts per province | Combined count, split by a documented model with uncertainty | NSO does not publish the split by province |
| H2 "car density vs GRDP", H3 "PCMO growth outside HN/HCMC" | H2 total vehicle density vs GRDP (controlling for urbanisation); H3 catch-up growth vs density | Hypotheses must be tested on **observed** data; testing model outputs would be circular |
| Power BI dashboard | Streamlit app (runs now) + Power BI-ready star schema and build guide | A .pbix cannot be generated from code; Streamlit is the Scope Spec's distinction-level option |

## Key analytical findings so far

- Regions differ strongly in vehicle density (H1 confirmed).
- The pre-registered **linear** income effect (H2) is not supported once urbanisation is controlled.
  The assumption checks (RESET) show the linear form is wrong, though. An exploratory quadratic model finds an
  **inverted U**: density rises with income in poorer provinces and falls in the richest, where cars replace
  motorbikes. It also has the best leave-one-out error. Treat it as a hypothesis for the next data release.
- No catch-up effect (H3 not supported).
- The model differs from the population-share rule of thumb by 20% per province on average (up to 72%), and it
  changes 2 of the top-10 provinces.
- Freight forecasts under-predicted 2023-2025 by about 12%, so the heavy-duty oil growth forecast is conservative.

## Limitations

- The province split between cars, commercial vehicles and motorbikes is modelled. If province-level car
  registrations become available, replace the allocation in `demand.py`.
- Only one year (2025) of province vehicle counts exists in the 34-province series, so fleet growth is driven
  by population, income and freight forecasts rather than by a fleet time series.
- Market benchmarks (Expert Market Research, Mordor Intelligence, Lubes'n'Greases) are used only to sanity-check
  the total; they are not inputs.

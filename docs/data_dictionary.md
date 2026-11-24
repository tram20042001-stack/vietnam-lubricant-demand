# Data dictionary

Warehouse: `data/warehouse.duckdb`. Dashboard / Power BI exports: `dashboard/data/*.csv` (UTF-8 with BOM),
mirrored as Parquet in `data/processed/` and as `res_*` tables in the warehouse.

## Marts (DuckDB)

| Table | Grain | Key columns |
|---|---|---|
| `mart_dim_province` | province (34) | `province_code` (P01-P34), `province_vi`, `province_en`, `region_vi`, `region_en`, `merged_from_count`, `area_km2`, `is_hn_hcmc` |
| `mart_province_year` | province x year 2011-2025 | `population_k` (thousand), `urban_k`, `urban_share`, `grdp_pc_mvnd` (million VND, current prices), `real_grdp_index` (prev. year = 100), `road_freight_kt` (thousand tonnes), `road_passengers_m` (million trips), `income_pc_kvnd_month`, `geography_source` (official_34 / rollup_63), `non_official_measures`, `has_imputed_values`, `rollup_complete` |
| `mart_vehicles_2025` | province | `vehicles_k` (registered cars + motorbikes, thousand), `vehicles_per_1000`, `accidents_per_10k`, `deaths_per_10k`, `injuries_per_10k`, `accidents`, `deaths`, `accident_count_consistency` |
| `mart_urban_share_model` | province | `urban_share_model` (2024), `had_2025_break` |
| `mart_national_production` | year | `motorbikes_assembled_k`, `cars_assembled_k` |
| `dq_*` | - | `dq_unmatched_geography`, `dq_missingness`, `dq_reconciliation`, `dq_series_breaks`, `dq_vehicle_totals`, `dq_bad_years` |

## Model outputs (`dashboard/data/`)

| File | Grain | Columns |
|---|---|---|
| `fact_demand.csv` | province x segment x year (2025-2028) | `litres_mean`, `litres_p025`, `litres_p10`, `litres_p50`, `litres_p90`, `litres_p975`, `fleet_registered_p50` |
| `national_demand.csv` | segment (incl. TOTAL) x year | `litres_mean`, `litres_p025`, `litres_p50`, `litres_p975` |
| `priority.csv` | province | `priority_rank`, `tier` (A/B/C), `litres_2025_p50`, `litres_2028_p50`, `increment_2025_2028_p50`, `cagr_2025_2028_p50`, `priority_score_p50`, `prob_top10`, `growth_focus_segment`, `mco/pcmo/hdmo_share_2025`, `litres_per_capita_2025` |
| `fact_drivers_forecast.csv` | province x year | `population_k`, `road_freight_kt`, `is_forecast` |
| `fact_growth.csv` | province | `real_gdp_growth`, `pop_growth`, `real_gdp_pc_growth_raw`, `real_gdp_pc_growth` (shrunk) |
| `hypothesis_tests.csv` | test | `statistic`, `p_value`, `p_holm`, `reject_h0`, `effect_name`, `effect_size`, `ci95` |
| `backtest.csv` / `backtest_summary.csv` | province x variable / variable | MAPE per method, chosen method, national MAPE |
| `sensitivity.csv` | parameter | `spearman_with_total_2025` |
| `outliers.csv` | province | robust z-scores and flag |
| `assumptions_*.csv`, `market_benchmarks.csv` | - | copies of the reference tables used in the run |
| `run_metadata.json` | run | time, outcome, per-source download status |

Segments: **MCO** = motorcycle oil (motorbikes), **PCMO** = passenger-car motor oil (cars with 9 seats or
fewer), **HDMO** = heavy-duty oil (trucks, buses, pickups, special vehicles).

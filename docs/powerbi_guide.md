# Building the Power BI report (about 45 minutes, Power BI Desktop)

The pipeline writes a star schema to `dashboard/data/`. Power BI reads it directly, and **Home -> Refresh** picks
up every scheduled pipeline run.

## 1. Load

*Get data -> Text/CSV*, then load these tables (file origin 65001: UTF-8):
`dim_province`, `fact_demand`, `priority`, `fact_vehicles_2025`, `fact_province_year`, `national_demand`,
`hypothesis_tests`, `sensitivity`.

Tip: *Transform data -> Manage parameters*, create `DataFolder` = the full path of `dashboard\data\`, and use it
in each source step so the report moves with the repository.

## 2. Model (relationships, single direction)

| From | To | Cardinality |
|---|---|---|
| `dim_province[province_code]` | `fact_demand[province_code]` | 1 : * |
| `dim_province[province_code]` | `priority[province_code]` | 1 : 1 |
| `dim_province[province_code]` | `fact_vehicles_2025[province_code]` | 1 : 1 |
| `dim_province[province_code]` | `fact_province_year[province_code]` | 1 : * |

Add a small table `Segment` with the columns `segment` (MCO, PCMO, HDMO) and `label`, related 1 : * to
`fact_demand[segment]`.

## 3. Measures (DAX)

```DAX
Demand ML        = DIVIDE ( SUM ( fact_demand[litres_p50] ), 1e6 )
Demand ML low    = DIVIDE ( SUM ( fact_demand[litres_p025] ), 1e6 )
Demand ML high   = DIVIDE ( SUM ( fact_demand[litres_p975] ), 1e6 )
Demand 2025 ML   = CALCULATE ( [Demand ML], fact_demand[year] = 2025 )
Demand 2028 ML   = CALCULATE ( [Demand ML], fact_demand[year] = 2028 )
Growth 25-28 %   = DIVIDE ( [Demand 2028 ML], [Demand 2025 ML] ) - 1
Litres per capita =
    DIVIDE ( CALCULATE ( SUM ( fact_demand[litres_p50] ), fact_demand[year] = 2025 ),
             SUM ( fact_vehicles_2025[population_k] ) * 1000 )
Vehicles per 1000 =
    DIVIDE ( SUM ( fact_vehicles_2025[vehicles_k] ), SUM ( fact_vehicles_2025[population_k] ) ) * 1000
```

Note: summing province medians gives a slightly different number from the national median in
`national_demand`. Use `national_demand` for the single national headline figure.

## 4. Pages

1. **Overview** - cards (Demand 2025, Growth 25-28 %, tier-A count); slicers for region, segment and year in one
   row; stacked bar of `Demand ML` by province and segment (colours MCO `#2a78d6`, PCMO `#eb6834`,
   HDMO `#1baf7a`).
2. **Province detail** - line chart of `Demand ML` by year and segment, with error bars from `Demand ML low` /
   `Demand ML high`; a table of the province's fleet, population, GRDP and freight.
3. **Priority** - scatter of `litres_2025_p50` against `increment_2025_2028_p50`, coloured by `tier`; a table
   sorted by `priority_rank` with `prob_top10` shown as data bars.
4. **Evidence** - `hypothesis_tests` table and a `sensitivity` bar chart.

Save the file as `dashboard/lubricant_demand.pbix`.

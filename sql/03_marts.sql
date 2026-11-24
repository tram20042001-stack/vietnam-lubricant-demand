-- 03 Marts: analysis-ready tables on the 34-province geography --------------------------

-- 3.1 Random gaps inside a historical series are linearly interpolated (and flagged).
CREATE OR REPLACE TABLE int_p63_series AS
WITH base AS (
    SELECT sid, province_63_vi, province_34_code, indicator, year, data_status, value, missing_type
    FROM cln_observation
    WHERE geography = 'p63' AND geo_level = 'province' AND NOT bad_year
), w AS (
    SELECT *,
        last_value(CASE WHEN value IS NOT NULL THEN year END IGNORE NULLS) OVER prev AS y0,
        last_value(value IGNORE NULLS) OVER prev                                     AS v0,
        first_value(CASE WHEN value IS NOT NULL THEN year END IGNORE NULLS) OVER nxt AS y1,
        first_value(value IGNORE NULLS) OVER nxt                                     AS v1
    FROM base
    WINDOW prev AS (PARTITION BY sid, province_63_vi, indicator ORDER BY year
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
           nxt  AS (PARTITION BY sid, province_63_vi, indicator ORDER BY year
                    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)
)
SELECT sid, province_63_vi, province_34_code, indicator, year, data_status,
       CASE WHEN missing_type = 'random' THEN v0 + (v1 - v0) * (year - y0) / (y1 - y0) ELSE value END AS value,
       missing_type = 'random' AS imputed
FROM w;

-- 3.2 Roll the 63 former provinces up to the 34 current ones (additive measures), 2008+.
--     2008 is the first year with stable boundaries (Ha Tay merged into Ha Noi in Aug 2008;
--     Dak Nong, Hau Giang, Dien Bien/Lai Chau were split in 2004).
CREATE OR REPLACE TABLE int_p63_to_34 AS
WITH expected AS (
    SELECT province_34_code, count(*) AS n_expected
    FROM ref_province_63
    WHERE province_63_vi <> 'Hà Tây' AND coalesce(note, '') NOT LIKE 'alias%'
    GROUP BY 1
), pop AS (
    SELECT province_63_vi, year, value AS pop_k FROM int_p63_series
    WHERE sid = 'p63_population' AND indicator = 'Tổng số'
), additive AS (
    SELECT sid, province_34_code, indicator, year,
           sum(value) AS value, count(value) AS n_reported, bool_or(imputed) AS any_imputed
    FROM int_p63_series
    WHERE year >= 2008 AND sid IN ('p63_population', 'p63_road_freight', 'p63_road_passengers')
    GROUP BY ALL
), grdp AS (   -- per-capita measure: population-weighted mean
    SELECT 'p63_grdp_pc' AS sid, g.province_34_code, '' AS indicator, g.year,
           sum(g.value * p.pop_k) / sum(p.pop_k) AS value, count(g.value) AS n_reported, bool_or(g.imputed) AS any_imputed
    FROM int_p63_series g JOIN pop p USING (province_63_vi, year)
    WHERE g.sid = 'p63_grdp_pc' GROUP BY ALL
)
SELECT a.*, e.n_expected, a.n_reported = e.n_expected AS complete
FROM (SELECT * FROM additive UNION ALL SELECT * FROM grdp) a
JOIN expected e USING (province_34_code);

-- 3.3 Official 34-province observations, pivoted.
CREATE OR REPLACE TABLE int_p34 AS
SELECT province_34_code AS province_code, year,
    max(value) FILTER (WHERE sid = 'p34_population' AND indicator = 'Tổng số')     AS population_k,
    max(value) FILTER (WHERE sid = 'p34_population' AND indicator = 'Thành thị')   AS urban_k,
    max(value) FILTER (WHERE sid = 'p34_population' AND indicator = 'Nông thôn')   AS rural_k,
    max(value) FILTER (WHERE sid = 'p34_grdp_pc')                                   AS grdp_pc_mvnd,
    max(value) FILTER (WHERE sid = 'p34_grdp_growth')                               AS real_grdp_index,
    max(value) FILTER (WHERE sid = 'p34_road_freight')                              AS road_freight_kt,
    max(value) FILTER (WHERE sid = 'p34_road_passengers')                           AS road_passengers_m,
    max(value) FILTER (WHERE sid = 'p34_income' AND indicator = 'Bình quân chung')  AS income_pc_kvnd_month,
    max(value) FILTER (WHERE sid = 'p34_area' AND indicator LIKE 'Diện tích%')      AS area_km2,
    string_agg(DISTINCT data_status, ',') FILTER (WHERE data_status <> 'official')  AS non_official
FROM cln_observation
WHERE geography = 'p34' AND geo_level = 'province'
GROUP BY ALL;

-- 3.4 Reconciliation: does the 63->34 roll-up reproduce the official 34-province figures?
CREATE OR REPLACE TABLE dq_reconciliation AS
WITH agg AS (
    SELECT province_34_code AS province_code, year,
        max(value) FILTER (WHERE sid = 'p63_population' AND indicator = 'Tổng số') AS pop_rollup,
        max(value) FILTER (WHERE sid = 'p63_road_freight')                        AS freight_rollup,
        max(value) FILTER (WHERE sid = 'p63_grdp_pc')                             AS grdp_pc_rollup
    FROM int_p63_to_34 GROUP BY ALL
)
SELECT o.province_code, o.year,
    o.population_k, a.pop_rollup, 100 * (a.pop_rollup / o.population_k - 1)          AS pop_diff_pct,
    o.road_freight_kt, a.freight_rollup, 100 * (a.freight_rollup / o.road_freight_kt - 1) AS freight_diff_pct,
    o.grdp_pc_mvnd, a.grdp_pc_rollup, 100 * (a.grdp_pc_rollup / o.grdp_pc_mvnd - 1)   AS grdp_pc_diff_pct
FROM int_p34 o JOIN agg a USING (province_code, year)
WHERE o.year BETWEEN 2020 AND 2025;

-- 3.5 Dimension
CREATE OR REPLACE TABLE mart_dim_province AS
SELECT DISTINCT ON (r.province_code)
    r.province_code, r.province_vi, r.province_en, r.region_vi, r.region_en, r.merged_from_count,
    p.area_km2,
    r.province_code IN ('P01', 'P29') AS is_hn_hcmc
FROM ref_province_34 r
LEFT JOIN int_p34 p ON p.province_code = r.province_code AND p.year = 2025
ORDER BY r.province_code;

-- 3.6 Province x year fact table, 2011-2025: official 34-province series where available
--     (2020+), historical roll-up of the 63 former provinces before that.
CREATE OR REPLACE TABLE mart_province_year AS
WITH hist AS (
    SELECT province_34_code AS province_code, year,
        max(value) FILTER (WHERE sid = 'p63_population' AND indicator = 'Tổng số')   AS population_k,
        max(value) FILTER (WHERE sid = 'p63_population' AND indicator = 'Thành thị') AS urban_k,
        max(value) FILTER (WHERE sid = 'p63_road_freight')                          AS road_freight_kt,
        max(value) FILTER (WHERE sid = 'p63_road_passengers')                       AS road_passengers_m,
        max(value) FILTER (WHERE sid = 'p63_grdp_pc')                               AS grdp_pc_mvnd,
        bool_and(complete) AS complete, bool_or(any_imputed) AS any_imputed
    FROM int_p63_to_34 GROUP BY ALL
), grid AS (
    SELECT province_code, y.year
    FROM mart_dim_province, range(2011, 2026) y(year)
)
SELECT g.province_code, g.year,
    coalesce(o.population_k, h.population_k)          AS population_k,
    coalesce(o.urban_k, h.urban_k)                    AS urban_k,
    coalesce(o.urban_k, h.urban_k) / coalesce(o.population_k, h.population_k) AS urban_share,
    coalesce(o.grdp_pc_mvnd, h.grdp_pc_mvnd)          AS grdp_pc_mvnd,
    o.real_grdp_index,
    coalesce(o.road_freight_kt, h.road_freight_kt)    AS road_freight_kt,
    coalesce(o.road_passengers_m, h.road_passengers_m) AS road_passengers_m,
    o.income_pc_kvnd_month,
    CASE WHEN o.population_k IS NOT NULL THEN 'official_34' ELSE 'rollup_63' END AS geography_source,
    coalesce(o.non_official, '')                      AS non_official_measures,
    coalesce(h.any_imputed, false)                    AS has_imputed_values,
    coalesce(h.complete, true)                        AS rollup_complete
FROM grid g
LEFT JOIN int_p34 o USING (province_code, year)
LEFT JOIN hist h USING (province_code, year)
ORDER BY 1, 2;

-- 3.7 Vehicles (official, 2025)
CREATE OR REPLACE TABLE mart_vehicles_2025 AS
WITH v AS (
    SELECT province_34_code AS province_code,
        max(value) FILTER (WHERE sid = 'p34_vehicles' AND indicator LIKE 'Tổng phương tiện%')      AS vehicles_k,
        max(value) FILTER (WHERE sid = 'p34_vehicles' AND indicator LIKE 'Số vụ tai nạn%')          AS accidents_per_10k,
        max(value) FILTER (WHERE sid = 'p34_vehicles' AND indicator LIKE 'Số người chết%')          AS deaths_per_10k,
        max(value) FILTER (WHERE sid = 'p34_vehicles' AND indicator LIKE 'Số người bị thương%')     AS injuries_per_10k,
        max(value) FILTER (WHERE sid = 'p34_accidents' AND indicator LIKE 'Số Vụ%')                 AS accidents,
        max(value) FILTER (WHERE sid = 'p34_accidents' AND indicator LIKE 'Số người chết%')         AS deaths
    FROM cln_observation
    WHERE geo_level = 'province' AND sid IN ('p34_vehicles', 'p34_accidents') AND year = 2025
    GROUP BY 1
)
SELECT v.*, p.population_k, p.urban_share, p.grdp_pc_mvnd, p.road_freight_kt,
    1000 * v.vehicles_k / p.population_k                               AS vehicles_per_1000,
    v.accidents / (v.accidents_per_10k * v.vehicles_k / 10)            AS accident_count_consistency
FROM v JOIN mart_province_year p ON p.province_code = v.province_code AND p.year = 2025;

-- 3.8 National new-vehicle assembly (inflow proxy)
CREATE OR REPLACE TABLE mart_national_production AS
SELECT year,
    max(value) FILTER (WHERE indicator LIKE 'Xe mô tô, xe máy lắp ráp%') AS motorbikes_assembled_k,
    max(value) FILTER (WHERE indicator LIKE 'Ô tô lắp ráp%')             AS cars_assembled_k,
    any_value(data_status) AS data_status
FROM cln_observation WHERE sid = 'nat_industrial' AND NOT bad_year
GROUP BY 1 ORDER BY 1;

-- 3.9 Series breaks: the 2025 commune-level reform reclassified urban/rural areas, so a
--     jump in urban share in 2025 is an administrative artefact, not a real change.
CREATE OR REPLACE TABLE dq_series_breaks AS
SELECT province_code, year, urban_share,
       lag(urban_share) OVER w AS prev_urban_share,
       urban_share - lag(urban_share) OVER w AS change_pp,
       abs(urban_share - lag(urban_share) OVER w) > 0.03 AS is_break
FROM mart_province_year
WINDOW w AS (PARTITION BY province_code ORDER BY year)
QUALIFY year >= 2012 AND is_break;

-- Urban share used for modelling = 2024, the last year before the 2025 reform. Earlier breaks
-- are genuine reclassifications (new towns upgraded to urban) and are kept.
CREATE OR REPLACE TABLE mart_urban_share_model AS
SELECT province_code, urban_share AS urban_share_model,
       province_code IN (SELECT province_code FROM dq_series_breaks WHERE year = 2025) AS had_2025_break
FROM mart_province_year WHERE year = 2024;

-- 3.10 Check: provinces add up to the published regional and national vehicle totals
CREATE OR REPLACE TABLE dq_vehicle_totals AS
SELECT 'national' AS level, 'CẢ NƯỚC' AS unit,
    (SELECT value FROM cln_observation WHERE sid = 'p34_vehicles' AND geo_level = 'national'
        AND indicator LIKE 'Tổng phương tiện%') AS published_k,
    (SELECT sum(vehicles_k) FROM mart_vehicles_2025) AS sum_of_provinces_k
UNION ALL
SELECT 'region', d.region_vi,
    max(c.value), (SELECT sum(vehicles_k) FROM mart_vehicles_2025 m JOIN mart_dim_province x USING (province_code)
                   WHERE x.region_vi = d.region_vi)
FROM (SELECT DISTINCT region_vi FROM mart_dim_province) d
JOIN cln_observation c ON c.sid = 'p34_vehicles' AND c.geo_level = 'region'
     AND name_key(c.geo_raw) = name_key(d.region_vi) AND c.indicator LIKE 'Tổng phương tiện%'
GROUP BY ALL;

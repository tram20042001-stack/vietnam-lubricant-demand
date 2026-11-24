-- 02 Clean: typed years, data status, geography resolution, missingness classification -----

CREATE OR REPLACE TABLE cln_observation AS
WITH typed AS (
    SELECT
        s.*,
        TRY_CAST(regexp_extract(period_raw, '(\d{4})', 1) AS INTEGER) AS year,
        CASE WHEN period_raw ILIKE 'Sơ bộ%'   THEN 'preliminary'
             WHEN period_raw ILIKE 'Ước tính%' THEN 'estimate'
             ELSE 'official' END                                     AS data_status,
        name_key(geo_raw)                                            AS geo_key,
        trim(regexp_replace(indicator_raw, '\s+', ' ', 'g'))          AS indicator
    FROM stg_observation s
), resolved AS (
    SELECT t.*,
        CASE
            WHEN t.geo_key IN ('canuoc', 'tongso')        THEN 'national'
            WHEN r.key IS NOT NULL                        THEN 'region'
            WHEN t.geo_key = 'khac'                       THEN 'unallocated'
            WHEN t.geography = 'p34' AND p34.key IS NOT NULL THEN 'province'
            WHEN t.geography = 'p63' AND p63.key IS NOT NULL THEN 'province'
            WHEN t.geography = 'national'                 THEN 'national'
            ELSE 'unmatched'
        END                                              AS geo_level,
        coalesce(p34.province_code, p63.province_34_code) AS province_34_code,
        CASE WHEN t.geography = 'p63' THEN p63.province_63_vi END AS province_63_vi
    FROM typed t
    LEFT JOIN ref_region r       ON r.key = t.geo_key
    LEFT JOIN ref_province_34 p34 ON p34.key = t.geo_key AND t.geography = 'p34'
    LEFT JOIN ref_province_63 p63 ON p63.key = t.geo_key AND t.geography = 'p63'
)
SELECT
    sid, geography, geo_raw, geo_level, province_34_code, province_63_vi, geo_order,
    year, data_status, period_raw, indicator, value, flag,
    year IS NULL OR year NOT BETWEEN 1990 AND 2035 AS bad_year
FROM resolved;

-- Missingness: a gap before the first / after the last reported year of a series is
-- STRUCTURAL (the administrative unit did not exist yet, e.g. Dak Nong before 2004, or no
-- longer existed, e.g. Ha Tay after 2008). Gaps inside a series are RANDOM and imputed later.
CREATE OR REPLACE TABLE cln_series_bounds AS
SELECT sid, geo_raw, indicator,
       min(year) FILTER (WHERE value IS NOT NULL) AS first_year,
       max(year) FILTER (WHERE value IS NOT NULL) AS last_year
FROM cln_observation GROUP BY ALL;

CREATE OR REPLACE TABLE cln_observation AS
SELECT o.*,
    CASE WHEN o.value IS NOT NULL THEN NULL
         WHEN b.first_year IS NULL OR o.year < b.first_year OR o.year > b.last_year THEN 'structural'
         ELSE 'random' END AS missing_type
FROM cln_observation o
JOIN cln_series_bounds b USING (sid, geo_raw, indicator);

-- Data-quality tables ------------------------------------------------------------------
CREATE OR REPLACE TABLE dq_unmatched_geography AS
SELECT sid, geo_raw, count(*) AS n FROM cln_observation
WHERE geo_level = 'unmatched' GROUP BY ALL;

CREATE OR REPLACE TABLE dq_missingness AS
SELECT sid, geo_level, missing_type, count(*) AS n_cells,
       min(year) AS min_year, max(year) AS max_year,
       string_agg(DISTINCT geo_raw, ', ') AS units
FROM cln_observation WHERE value IS NULL GROUP BY ALL;

CREATE OR REPLACE TABLE dq_bad_years AS
SELECT DISTINCT sid, period_raw FROM cln_observation WHERE bad_year;

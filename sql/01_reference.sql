-- 01 Reference data and the name-normalisation macro --------------------------------------
-- Province names arrive in several spellings: "Đ" (U+0110) vs the look-alike "Ð" (U+00D0)
-- used in older NSO tables, "TP. Hồ Chí Minh" vs "Thành phố Hồ Chí Minh", "Thừa Thiên Huế"
-- vs "Huế", decomposed vs precomposed diacritics. Everything is matched on an ASCII key.

CREATE OR REPLACE MACRO name_key(s) AS
    regexp_replace(
        regexp_replace(
            lower(strip_accents(replace(replace(replace(replace(trim(s), 'Ð', 'D'), 'Đ', 'D'), 'đ', 'd'), 'ð', 'd'))),
            '^(tp\.\s*|tp\s+|thanh pho\s+)', ''),
        '[^a-z]', '', 'g');

CREATE OR REPLACE TABLE ref_province_34 AS
SELECT *, name_key(province_vi) AS key
FROM read_csv('data/reference/province_34.csv', header = true);

CREATE OR REPLACE TABLE ref_province_63 AS
SELECT m.province_63_vi, name_key(m.province_63_vi) AS key, m.province_34_code, m.note
FROM read_csv('data/reference/province_63_to_34.csv', header = true, all_varchar = true) m;

-- extra alias: the new-series name of the former Thua Thien Hue
INSERT INTO ref_province_34
SELECT province_code, province_vi, province_en, region_vi, region_en, merged_from_count, 'thuathienhue'
FROM ref_province_34 WHERE province_code = 'P20';

CREATE OR REPLACE TABLE ref_region AS
SELECT DISTINCT region_vi, region_en, name_key(region_vi) AS key FROM ref_province_34
UNION ALL SELECT 'Bắc Trung Bộ và Duyên hải miền Trung', 'North Central and Central Coast (pre-2025)',
                 name_key('Bắc Trung Bộ và Duyên hải miền Trung')
UNION ALL SELECT 'Tây Nguyên', 'Central Highlands (pre-2025)', name_key('Tây Nguyên');

CREATE OR REPLACE TABLE ref_lubricant_assumptions AS
SELECT * FROM read_csv('data/reference/lubricant_assumptions.csv', header = true);

CREATE OR REPLACE TABLE ref_fleet_split_assumptions AS
SELECT * FROM read_csv('data/reference/fleet_split_assumptions.csv', header = true);

CREATE OR REPLACE TABLE ref_market_benchmarks AS
SELECT * FROM read_csv('data/reference/market_benchmarks.csv', header = true);

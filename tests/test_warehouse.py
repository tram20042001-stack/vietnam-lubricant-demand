"""Data-quality gates on the built warehouse (run `python -m vnlube.pipeline --offline` first)."""
import pytest

from vnlube import data_access as da
from vnlube.config import WAREHOUSE

pytestmark = pytest.mark.skipif(not WAREHOUSE.exists(), reason="warehouse not built")


def test_all_geographies_resolved():
    assert da.query("SELECT count(*) n FROM dq_unmatched_geography").n[0] == 0


def test_34_provinces_with_vehicle_counts():
    v = da.query("SELECT * FROM mart_vehicles_2025")
    assert len(v) == 34 and v.vehicles_k.notna().all() and (v.vehicles_k > 0).all()


def test_provinces_add_up_to_published_totals():
    t = da.query("SELECT * FROM dq_vehicle_totals")
    assert ((t.published_k - t.sum_of_provinces_k).abs() < 0.5).all()


def test_63_to_34_mapping_reproduces_official_figures():
    r = da.query("SELECT * FROM dq_reconciliation")
    assert r.pop_diff_pct.abs().max() < 0.01
    assert r.freight_diff_pct.abs().max() < 0.01
    assert r.grdp_pc_diff_pct.abs().max() < 0.01


def test_every_former_province_is_mapped_once():
    m = da.query("SELECT province_63_vi, note FROM ref_province_63")
    physical = m[~m.note.fillna("").str.startswith("alias") & (m.province_63_vi != "Hà Tây")]
    assert len(physical) == 63 and physical.province_63_vi.is_unique


def test_only_structural_or_interpolated_gaps():
    mart = da.query("SELECT * FROM mart_province_year WHERE year >= 2020")
    assert mart[["population_k", "grdp_pc_mvnd", "road_freight_kt"]].notna().all().all()

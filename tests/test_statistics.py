import pandas as pd
import pytest

from vnlube import data_access as da
from vnlube import statistics as st
from vnlube.config import WAREHOUSE

pytestmark = pytest.mark.skipif(not WAREHOUSE.exists(), reason="warehouse not built")


def test_robust_z_flags_planted_outlier():
    z = st.robust_z(pd.Series([10, 11, 9, 10, 12, 10, 100.0]))
    assert z.iloc[-1] > 3.5 and (z.iloc[:-1].abs() < 3.5).all()


def test_assumption_checks_complete():
    checks = st.assumption_checks(da.province_base())
    assert {"H1 Kruskal-Wallis", "H2 OLS"} <= set(checks["model"])
    assert checks["passed"].dtype == bool and checks["consequence"].notna().all()


def test_hypotheses_holm_adjusted():
    tests, details = st.run_all(da.province_base(), da.province_year())
    assert len(tests) == 3
    assert (tests["p_holm"] >= tests["p_value"] - 1e-12).all()   # Holm never lowers a p-value
    nl = details["H2"]["nonlinear"]
    assert len(nl["elasticity_at"]) == 3 and nl["turning_point_grdp_pc"] > 0

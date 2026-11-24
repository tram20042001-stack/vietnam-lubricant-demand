import json

from vnlube.jsonstat import parse_jsonstat

V2 = {
    "class": "dataset", "label": "test", "id": ["Địa phương", "Năm"], "size": [2, 2],
    "dimension": {
        "Địa phương": {"label": "Địa phương", "category": {"index": {"0": 0, "1": 1},
                                                           "label": {"0": "Hà Nội", "1": "Ðiện Biên"}}},
        "Năm": {"label": "Năm", "category": {"index": {"0": 0, "1": 1}, "label": {"0": "2024", "1": "Sơ bộ 2025"}}},
    },
    "value": [1.0, 2.0, None, 4.0],
}


def test_v2_shape_and_order():
    df, meta = parse_jsonstat(json.dumps(V2))
    assert list(df.columns) == ["Địa phương", "Năm", "value", "flag"]
    assert len(df) == 4
    assert df.iloc[1].tolist()[:3] == ["Hà Nội", "Sơ bộ 2025", 2.0]
    assert df["value"].isna().sum() == 1
    assert meta["dimensions"] == ["Địa phương", "Năm"]


def test_v1_bundle_and_sparse_values():
    v1 = {"dataset": {k: v for k, v in V2.items() if k not in {"class", "id", "size"}}}
    v1["dataset"]["dimension"]["id"] = V2["id"]
    v1["dataset"]["dimension"]["size"] = V2["size"]
    v1["dataset"]["value"] = {"0": 1.0, "3": 4.0}
    df, _ = parse_jsonstat(json.dumps(v1))
    assert df["value"].tolist()[0] == 1.0 and df["value"].isna().sum() == 2

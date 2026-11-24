"""Convert JSON-stat (version 1 'bundle' or version 2 'dataset') into a tidy long DataFrame.

JSON-stat stores a data cube compactly:
* ``id`` / ``size``  - the dimension names and how many categories each has,
* ``dimension``      - for each dimension, the category order (``index``) and display labels,
* ``value``          - ONE flat list of cell values in row-major order (last dimension changes fastest),
* ``status``         - optional per-cell flags (e.g. ".." for "not available").

The NSO form route returns JSON-stat 1.x (wrapped in ``{"dataset": {...}}``) while the
API returns 2.0; both are handled. The output has one column per dimension plus
``value`` and ``flag`` - one row per cell of the cube.
"""
from __future__ import annotations

import json
import unicodedata
from itertools import product
from pathlib import Path

import pandas as pd


def _nfc(s: str) -> str:
    """Normalise Unicode to composed form (NFC).

    Vietnamese letters can arrive either precomposed ("ộ") or as base letter + combining
    marks; NFC makes identical-looking strings compare equal.
    """
    return unicodedata.normalize("NFC", s).strip()


def parse_jsonstat(raw: bytes | str) -> tuple[pd.DataFrame, dict]:
    """Parse JSON-stat bytes/text into (long DataFrame, metadata dict)."""
    obj = json.loads(raw)
    if obj.get("class") != "dataset":          # JSON-stat 1.x bundle: {"dataset": {...}}
        obj = obj["dataset"] if "dataset" in obj else next(iter(obj.values()))

    # v2 keeps id/size at the top level, v1 inside "dimension"
    dims = obj.get("id") or obj["dimension"]["id"]
    sizes = obj.get("size") or obj["dimension"]["size"]

    # category labels for each dimension, in the cube's storage order
    labels = []
    for d in dims:
        cat = obj["dimension"][d]["category"]
        index = cat["index"]
        # index is either {"code": position} or a plain list of codes
        order = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
        labels.append([_nfc(cat.get("label", {}).get(k, k)) for k in order])

    values = obj["value"]
    n = 1
    for s in sizes:
        n *= s
    if isinstance(values, dict):              # sparse representation: {"cell index": value}
        values = [values.get(str(i)) for i in range(n)]
    status = obj.get("status") or {}
    if isinstance(status, list):              # status may be a list or a sparse dict
        status = {str(i): v for i, v in enumerate(status)}

    # Cartesian product of the labels reproduces the row-major cell order of "value"
    rows = list(product(*labels))
    if len(rows) != len(values):
        raise ValueError(f"JSON-stat size mismatch: {len(rows)} cells vs {len(values)} values")

    df = pd.DataFrame(rows, columns=[_nfc(obj["dimension"][d].get("label", d)) for d in dims])
    # missing cells come as null (or as text tokens such as ".."); coerce them to NaN
    df["value"] = pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce")
    df["flag"] = [status.get(str(i)) for i in range(len(values))]
    meta = {"label": _nfc(obj.get("label", "")), "updated": obj.get("updated"),
            "source": obj.get("source"), "dimensions": list(df.columns[:-2])}
    return df, meta


def read_jsonstat(path: str | Path) -> tuple[pd.DataFrame, dict]:
    """Parse a JSON-stat file from disk."""
    return parse_jsonstat(Path(path).read_bytes())

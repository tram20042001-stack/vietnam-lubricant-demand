"""Ingest: download every source, archive it with a checksum, detect new releases.

For every NSO table in ``config.SOURCES`` this module

1. downloads the table as JSON-stat (``nso_client.fetch``),
2. parses it once to make sure the file is valid before anything is overwritten,
3. compares its SHA-256 hash with the last archived version,
4. archives it under ``data/raw/<sid>/<sid>.json`` (the untouched original download) and writes a
   human-readable copy ``data/raw/<sid>/<sid>.csv`` (one row per cell, original Vietnamese labels),
5. appends a line to ``data/raw/manifest.csv`` (source URL, time, hash, size, status).

A raw file is only replaced when its hash changed; the previous release is kept as
``<sid>.<date>.prev.json`` so every change made by the NSO can be audited later.
The returned status per source ("new" / "changed" / "unchanged" / "failed") lets the
pipeline skip the rebuild when nothing changed.

    python -m vnlube.ingest                 # download all sources
    python -m vnlube.ingest --only p34_vehicles
    python -m vnlube.ingest --csv-only      # no download; rewrite the CSV copies from the archived JSON
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import logging
from pathlib import Path

from .config import MANIFEST, RAW, SOURCES, SOURCE_BY_ID, Source
from .jsonstat import parse_jsonstat, read_jsonstat
from .nso_client import NsoError, fetch

log = logging.getLogger(__name__)

# Columns of data/raw/manifest.csv (one row per download attempt, never rewritten)
FIELDS = ["sid", "table", "database", "geography", "route", "source_url", "downloaded_at_utc",
          "sha256", "bytes", "cells", "nso_updated", "status"]


def raw_path(sid: str) -> Path:
    """Location of the archived original download for one source."""
    return RAW / sid / f"{sid}.json"


def raw_csv_path(sid: str) -> Path:
    """Location of the human-readable CSV copy of one source."""
    return RAW / sid / f"{sid}.csv"


def write_raw_csv(sid: str) -> Path:
    """Write the tidy CSV copy of an archived raw file.

    The CSV keeps the NSO labels exactly as published (no cleaning) so reviewers can open the
    raw data in Excel. UTF-8 with BOM so Excel shows Vietnamese characters correctly.
    """
    df, _ = read_jsonstat(raw_path(sid))
    path = raw_csv_path(sid)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _last_hashes() -> dict[str, str]:
    """Hash of the latest successfully archived version of each source (from the manifest)."""
    if not MANIFEST.exists():
        return {}
    last = {}
    with MANIFEST.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # failed attempts carry no hash and must not reset the comparison baseline
            if row["status"] in {"new", "changed", "unchanged"}:
                last[row["sid"]] = row["sha256"]
    return last


def _append(row: dict) -> None:
    """Append one row to the manifest (creating it with a header on first use)."""
    new = not MANIFEST.exists()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def ingest_one(src: Source, last: dict[str, str]) -> str:
    """Download, validate and archive one source. Returns its status string."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = {"sid": src.sid, "table": src.table, "database": src.db, "geography": src.geography,
            "source_url": src.page_url, "downloaded_at_utc": now}
    try:
        raw, route = fetch(src)
        df, meta = parse_jsonstat(raw)          # validate BEFORE touching the archive
    except (NsoError, ValueError, KeyError) as exc:
        # keep the previously archived file; the pipeline continues with it
        log.error("%s: download failed: %s", src.sid, exc)
        _append({**base, "route": "", "sha256": "", "bytes": 0, "cells": 0, "nso_updated": "",
                 "status": f"failed: {str(exc)[:120]}"})
        return "failed"

    digest = hashlib.sha256(raw).hexdigest()
    status = "new" if src.sid not in last else ("unchanged" if last[src.sid] == digest else "changed")
    target = raw_path(src.sid)
    if status != "unchanged":
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():                      # keep the superseded release for audit
            target.replace(target.with_name(f"{src.sid}.{now[:10]}.prev.json"))
        target.write_bytes(raw)
        write_raw_csv(src.sid)
    elif not raw_csv_path(src.sid).exists():     # backfill the CSV copy if it is missing
        write_raw_csv(src.sid)

    _append({**base, "route": route, "sha256": digest, "bytes": len(raw), "cells": len(df),
             "nso_updated": meta.get("updated") or "", "status": status})
    log.info("%-22s %-9s cells=%-6d route=%s", src.sid, status, len(df), route)
    return status


def run(only: list[str] | None = None) -> dict[str, str]:
    """Ingest all sources (or the ones listed in ``only``); return {sid: status}."""
    last = _last_hashes()
    targets = [SOURCE_BY_ID[s] for s in only] if only else SOURCES
    return {src.sid: ingest_one(src, last) for src in targets}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="*", help="source ids to ingest (default: all)")
    p.add_argument("--csv-only", action="store_true", help="rewrite the raw CSV copies, no download")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.csv_only:
        for src in SOURCES:
            log.info("wrote %s", write_raw_csv(src.sid))
        return
    result = run(args.only)
    if any(v == "failed" for v in result.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

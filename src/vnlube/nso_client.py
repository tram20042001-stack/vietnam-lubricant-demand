"""Download tables from the Vietnam National Statistics Office (NSO) PX-Web service.

Tables are requested as JSON-stat (UTF-8). The PX download format is *not* used: the
NSO server writes PX files in ISO-8859-15 and silently replaces Vietnamese letters
with "?", which would destroy province names.

Two routes, because the NSO only exposes part of its catalogue through the JSON API:

* ``api``  - PX-Web API v1: read the metadata, POST a query selecting every value.
* ``form`` - the ASP.NET PX-Web user interface: select every value in every list box
  and submit the form with the ``FileTypeJsonStat`` output format.

The NSO host has intermittent DNS failures and sometimes serves an incomplete TLS
chain, so certificates are verified against the Windows/OS trust store (truststore)
and every request is retried with back-off.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse

import requests
import truststore

from .config import PXWEB_API, USER_AGENT, Source

truststore.inject_into_ssl()
log = logging.getLogger(__name__)
_q = urllib.parse.quote


class NsoError(RuntimeError):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _retry(fn, attempts: int = 6, wait: float = 4.0):
    """Call fn() until it succeeds; linear back-off (4 s, 8 s, 12 s ...) covers DNS outages of ~1 minute."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except (requests.RequestException, NsoError, ValueError) as exc:
            last = exc
            resp = getattr(exc, "response", None)
            if resp is not None and 400 <= resp.status_code < 500:
                break  # client errors (404 etc.) will not fix themselves
            log.warning("attempt %d/%d failed: %s", i + 1, attempts, str(exc)[:160])
            time.sleep(wait * (i + 1))
    raise NsoError(str(last))


def _check_json(content: bytes, sid: str) -> bytes:
    """Validate that the response is JSON-stat and return it as clean UTF-8 bytes."""
    # the NSO form route pads the JSON with a trailing NUL byte
    text = content.decode("utf-8-sig").strip().rstrip("\x00").strip()
    obj = json.loads(text)  # raises ValueError if the server returned HTML
    if "dataset" not in obj and obj.get("class") != "dataset":
        raise NsoError(f"{sid}: response is not a JSON-stat dataset")
    return text.encode("utf-8")


def fetch_api(src: Source, session: requests.Session | None = None) -> bytes:
    """PX-Web API v1 route: GET the variable list, then POST a query selecting everything."""
    s = session or _session()
    url = f"{PXWEB_API}/{_q(src.db)}/{_q(src.table)}"

    def run() -> bytes:
        meta = s.get(url, timeout=90)
        meta.raise_for_status()
        # "all" + ["*"] selects every value of every variable -> the complete table
        query = {
            "query": [{"code": v["code"], "selection": {"filter": "all", "values": ["*"]}}
                      for v in meta.json()["variables"]],
            "response": {"format": "json-stat2"},
        }
        r = s.post(url, json=query, timeout=180)
        r.raise_for_status()
        return _check_json(r.content, src.sid)

    return _retry(run)


def _hidden_fields(html: str) -> list[tuple[str, str]]:
    """Collect ASP.NET hidden inputs (__VIEWSTATE, __EVENTVALIDATION ...) that every postback must echo."""
    fields = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', html):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields.append((name.group(1), value.group(1) if value else ""))
    return fields


def fetch_form(src: Source, session: requests.Session | None = None) -> bytes:
    """Web-form route: reproduce what a user does in the browser (select all -> download JSON-stat)."""
    s = session or _session()
    url = src.page_url

    def run() -> bytes:
        page = s.get(url, timeout=90)
        page.raise_for_status()
        html = page.text
        # one multi-select list box per table variable (province, year, indicator ...)
        boxes = re.findall(r'<select[^>]*name="([^"]+ValuesListBox)"[^>]*>(.*?)</select>', html, re.S)
        if not boxes:
            raise NsoError(f"{src.sid}: no variable list boxes on {url}")
        data = _hidden_fields(html)
        for name, body in boxes:
            # repeating the field name once per option = selecting every value in the box
            data += [(name, v) for v in re.findall(r'<option[^>]*value="([^"]*)"', body)]
        fmt = re.search(r'name="([^"]+OutputFormatDropDownList)"', html).group(1)
        button = re.search(r'name="([^"]+ButtonViewTable)"[^>]*value="([^"]*)"', html)
        # JSON-stat, not PX: the PX export is ISO-8859-15 and loses Vietnamese letters
        data += [(fmt, "FileTypeJsonStat"), (button.group(1), button.group(2))]
        r = s.post(url, data=data, timeout=180)
        r.raise_for_status()
        return _check_json(r.content, src.sid)

    return _retry(run)


def fetch(src: Source) -> tuple[bytes, str]:
    """Return (json_stat_bytes, route). Tries the API first when the table is exposed there."""
    if src.api:
        try:
            return fetch_api(src), "api"
        except NsoError as exc:
            log.warning("API route failed for %s (%s); falling back to form", src.sid, exc)
    return fetch_form(src), "form"

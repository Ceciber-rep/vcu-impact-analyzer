"""Parse the Excel test register and its workshop notes.

The register is a working file: title rows above the header, empty or ``TBD``
links, legacy IDs and free-text results. This module only extracts facts; it
never decides whether a test is affected.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from vcu_impact.models import (
    LinkStatus,
    Measurement,
    RequirementLink,
    SpecDocument,
    TestCase,
    TestRegister,
    WorkshopNote,
)
from vcu_impact.spec_parser import REQ_ID_PATTERN

# Column keys -> header keywords (matched case-insensitively, first match wins).
_TEST_COLUMNS = {
    "test_id": ("test case", "test id", "tc id", "id"),
    "name": ("test name", "name", "title"),
    "procedure": ("procedure", "expected", "description"),
    "reference": ("req", "requirement", "trace"),
    "result": ("result", "verdict", "status"),
    "owner": ("owner", "responsible"),
    "last_run": ("last run", "date", "executed"),
    "comment": ("comment", "issue", "remark"),
}
_NOTE_COLUMNS = {
    "date": ("date",),
    "author": ("who", "author", "by"),
    "observation": ("observation", "open point", "finding"),
    "next_step": ("next step", "action"),
}
_REQ_ID_RE = re.compile(REQ_ID_PATTERN)
# A value or a range ("75–95%") followed by a unit.
_MEASURE_RE = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[–-]\s*(\d+(?:\.\d+)?))?\s*(ms|s|%)(?![a-z])", re.IGNORECASE)
_VERDICT_RE = re.compile(r"\b(NOT\s+RUN|PASS|FAIL|BLOCKED|INCONCLUSIVE)\b", re.IGNORECASE)


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return re.sub(r"\s+", " ", str(value)).strip()


def _find_header(ws: Worksheet, columns: dict, required: tuple[str, ...], scan_rows: int = 20):
    """Return (header_row_index, {key: column_index}) for the first row that matches."""
    for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=scan_rows, values_only=True), 1):
        headers = [_cell(v).lower() for v in row]
        mapping: dict[str, int] = {}
        for key, keywords in columns.items():
            for c_idx, h in enumerate(headers):
                if h and c_idx not in mapping.values() and any(k in h for k in keywords):
                    mapping[key] = c_idx
                    break
        if all(k in mapping for k in required):
            return r_idx, mapping
    return None, {}


def classify_links(raw: str, revised: SpecDocument | None, baseline: SpecDocument | None) -> list[RequirementLink]:
    raw = raw.strip()
    if not raw:
        return [RequirementLink(raw="", req_id=None, status=LinkStatus.MISSING)]
    if re.fullmatch(r"(?i)tbd|tbc|n/?a|\?+|-+", raw):
        return [RequirementLink(raw=raw, req_id=None, status=LinkStatus.TBD)]
    links = []
    revised_ids = set(revised.requirement_ids) if revised else set()
    baseline_ids = set(baseline.requirement_ids) if baseline else set()
    parts = []
    for chunk in (p.strip() for p in re.split(r"[;,/\n]+", raw) if p.strip()):
        found = _REQ_ID_RE.findall(chunk)
        # Several IDs in one chunk (separated by a space or "and"): one link each.
        parts += found if len(found) > 1 else [chunk]
    for part in parts:
        m = _REQ_ID_RE.search(part)
        if not m:
            status = LinkStatus.TBD if re.search(r"(?i)tbd|tbc", part) else LinkStatus.UNKNOWN
            links.append(RequirementLink(raw=part, req_id=None, status=status))
            continue
        req_id = m.group(0)
        if req_id in revised_ids:
            status = LinkStatus.VALID
        elif req_id in baseline_ids:
            status = LinkStatus.REMOVED
        else:
            status = LinkStatus.UNKNOWN
        links.append(RequirementLink(raw=part, req_id=req_id, status=status))
    return links


def _measurements(**fields: str) -> list[Measurement]:
    out = []
    for source, text in fields.items():
        for m in _MEASURE_RE.finditer(text or ""):
            unit = m.group(3).lower()
            for value in filter(None, (m.group(1), m.group(2))):
                out.append(Measurement(value=float(value), unit=unit, source=source))
    return out


def _verdict(result: str) -> str:
    m = _VERDICT_RE.search(result or "")
    return re.sub(r"\s+", " ", m.group(1).upper()) if m else ("UNKNOWN" if result else "EMPTY")


def parse_register(
    source: str | Path | BinaryIO | bytes,
    revised: SpecDocument | None = None,
    baseline: SpecDocument | None = None,
    source_name: str | None = None,
) -> TestRegister:
    if isinstance(source, bytes):
        source = BytesIO(source)
    if source_name is None:
        source_name = Path(source).name if isinstance(source, (str, Path)) else "uploaded.xlsx"
    wb = load_workbook(source, data_only=True, read_only=True)

    tests: list[TestCase] = []
    notes: list[WorkshopNote] = []
    title_lines: list[str] = []
    for ws in wb.worksheets:
        hdr, cols = _find_header(ws, _TEST_COLUMNS, ("test_id", "reference"))
        if hdr and not tests:
            for row in ws.iter_rows(min_row=1, max_row=hdr - 1, values_only=True):
                title_lines += [_cell(v) for v in row if _cell(v)]
            tests = _parse_tests(ws, hdr, cols, revised, baseline)
            continue
        hdr, cols = _find_header(ws, _NOTE_COLUMNS, ("date", "observation"))
        if hdr:
            notes += _parse_notes(ws, hdr, cols)
    wb.close()
    if not tests:
        raise ValueError("No test table found: expected a header row with 'Test case' and 'Req reference' columns.")
    return TestRegister(source_name=source_name, title_lines=title_lines, tests=tests, notes=notes)


def _raw_cell(row, cols, key: str) -> str:
    """Cell text with line breaks kept (a link cell may list one requirement per line)."""
    if key not in cols or cols[key] >= len(row) or row[cols[key]] is None:
        return ""
    value = row[cols[key]]
    return str(value).strip() if not isinstance(value, (datetime, date)) else _cell(value)


def _parse_tests(ws, hdr, cols, revised, baseline) -> list[TestCase]:
    tests = []
    get = lambda row, key: _cell(row[cols[key]]) if key in cols and cols[key] < len(row) else ""  # noqa: E731
    for row in ws.iter_rows(min_row=hdr + 1, values_only=True):
        test_id = get(row, "test_id")
        if not test_id:
            continue
        procedure, result, comment = get(row, "procedure"), get(row, "result"), get(row, "comment")
        tests.append(
            TestCase(
                test_id=test_id,
                name=get(row, "name"),
                procedure=procedure,
                raw_reference=get(row, "reference"),
                links=classify_links(_raw_cell(row, cols, "reference"), revised, baseline),
                result_raw=result,
                result_verdict=_verdict(result),
                measurements=_measurements(result=result, procedure=procedure, comment=comment),
                owner=get(row, "owner"),
                last_run=get(row, "last_run"),
                comment=comment,
            )
        )
    seen: set[str] = set()
    for t in tests:
        if t.test_id in seen:
            raise ValueError(f"Duplicate test ID in the register: {t.test_id}. Test IDs must be unique.")
        seen.add(t.test_id)
    return tests


def _parse_notes(ws, hdr, cols) -> list[WorkshopNote]:
    notes = []
    get = lambda row, key: _cell(row[cols[key]]) if key in cols and cols[key] < len(row) else ""  # noqa: E731
    for row in ws.iter_rows(min_row=hdr + 1, values_only=True):
        if get(row, "observation"):
            notes.append(
                WorkshopNote(
                    date=get(row, "date"),
                    author=get(row, "author"),
                    observation=get(row, "observation"),
                    next_step=get(row, "next_step"),
                )
            )
    return notes

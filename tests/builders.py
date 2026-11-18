"""Builders for synthetic specification and register files used by the robustness tests."""

from __future__ import annotations

from io import BytesIO

import openpyxl
from docx import Document
from docx.oxml import parse_xml

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
V = 'xmlns:v="urn:schemas-microsoft-com:vml"'


def make_spec(reqs: list[tuple[str, str, str]], sections: dict[str, str] | None = None, title="Test spec") -> bytes:
    """reqs: (id, title, body). Body paragraphs are separated by a blank line. Returns .docx bytes."""
    doc = Document()
    doc.add_paragraph(title, style="Title")
    doc.add_paragraph("Revision X | test")
    for req_id, req_title, body in reqs:
        doc.add_paragraph(f"{req_id}  {req_title}".rstrip())
        for para in filter(None, body.split("\n\n")):
            doc.add_paragraph(para)
    for name, text in (sections or {}).items():
        doc.add_heading(name, level=1)
        doc.add_paragraph(text)
    return to_bytes(doc)


def to_bytes(doc) -> bytes:
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def with_tracked_change(doc_bytes: bytes, req_id: str, deleted: str, inserted: str) -> bytes:
    """Replace the body paragraph of ``req_id`` by: [kept] <w:del>deleted</w:del> <w:ins>inserted</w:ins>."""
    doc = Document(BytesIO(doc_bytes))
    paras = doc.paragraphs
    i = next(n for n, p in enumerate(paras) if p.text.startswith(req_id))
    body = paras[i + 1]
    for r in list(body.runs):
        r._r.getparent().remove(r._r)
    body._p.append(parse_xml(f'<w:r {W}><w:t xml:space="preserve">The value is </w:t></w:r>'))
    body._p.append(
        parse_xml(
            f'<w:del {W} w:id="1" w:author="A" w:date="2026-01-01T00:00:00Z">'
            f"<w:r><w:delText>{deleted}</w:delText></w:r></w:del>"
        )
    )
    body._p.append(
        parse_xml(
            f'<w:ins {W} w:id="2" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:t>{inserted}</w:t></w:r></w:ins>'
        )
    )
    return to_bytes(doc)


def with_text_box(doc_bytes: bytes, text: str) -> bytes:
    doc = Document(BytesIO(doc_bytes))
    p = doc.add_paragraph()
    p._p.append(
        parse_xml(
            f"<w:r {W} {V}><w:pict><v:shape><v:textbox><w:txbxContent><w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
            "</w:txbxContent></v:textbox></v:shape></w:pict></w:r>"
        )
    )
    return to_bytes(doc)


def with_comment_and_header(doc_bytes: bytes, header: str) -> bytes:
    doc = Document(BytesIO(doc_bytes))
    doc.sections[0].header.paragraphs[0].text = header
    return to_bytes(doc)


def with_table_requirement(doc_bytes: bytes, row: tuple[str, str]) -> bytes:
    doc = Document(BytesIO(doc_bytes))
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = row
    return to_bytes(doc)


HEADERS = [
    "Test case",
    "Test name",
    "Procedure / expected outcome",
    "Req reference(s)",
    "Result (prev.)",
    "Owner",
    "Last run",
    "Comment / issue",
]


def make_register(rows: list[list], headers=HEADERS, notes: list[list] | None = None, extra=None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test register"
    ws.append(["Title row"])
    ws.append([])
    ws.append(headers)
    for r in rows:
        ws.append(r)
    if extra:
        extra(wb, ws)
    ns = wb.create_sheet("Workshop notes")
    ns.append(["Date", "Who", "Observation / open point", "Next step"])
    for n in notes or []:
        ns.append(n)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_test(
    n: int,
    link="VCU-DR-01",
    name=None,
    procedure="Step demand to 75%; expect 100 ms.",
    result="PASS (94 ms)",
    comment="",
):
    return [f"TV-{n:03d}", name or f"Test {n}", procedure, link, result, "A.", "2026-10-05", comment]

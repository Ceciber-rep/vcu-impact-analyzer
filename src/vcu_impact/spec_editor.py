"""Apply small edits to a specification .docx while keeping its formatting.

Used by the evaluation scenarios and by the UI ("edit a requirement").
The edited document is parsed again by the normal parser, so edits go through
exactly the same path as an uploaded file.
"""

from __future__ import annotations

import copy
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.text.paragraph import Paragraph

from vcu_impact.spec_parser import _HEADING_RE, _MAX_HEADING_LEN, _is_section_heading


def _set_text(p: Paragraph, text: str) -> None:
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def _locate(doc: DocxDocument, req_id: str) -> tuple[Paragraph, list[Paragraph]]:
    """Return the heading paragraph and the body paragraphs of a requirement."""
    paras = doc.paragraphs
    for i, p in enumerate(paras):
        m = _HEADING_RE.match(p.text.strip())
        if m and m.group("id") == req_id and len(p.text.strip()) <= _MAX_HEADING_LEN:
            body = []
            for q in paras[i + 1 :]:
                t = q.text.strip()
                if _is_section_heading(q) or (_HEADING_RE.match(t) and len(t) <= _MAX_HEADING_LEN):
                    break
                if t:
                    body.append(q)
            return p, body
    raise KeyError(f"Requirement {req_id} not found in document")


def load(source: str | Path | bytes) -> DocxDocument:
    return Document(BytesIO(source) if isinstance(source, bytes) else source)


def to_bytes(doc: DocxDocument) -> bytes:
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def set_requirement(doc: DocxDocument, req_id: str, text: str | None = None, title: str | None = None) -> None:
    heading, body = _locate(doc, req_id)
    if title is not None:
        _set_text(heading, f"{req_id}  {title}")
    if text is not None:
        if not body:
            raise ValueError(f"Requirement {req_id} has no body paragraph to edit")
        _set_text(body[0], text)
        for extra in body[1:]:
            extra._p.getparent().remove(extra._p)


def replace_in_requirement(doc: DocxDocument, req_id: str, old: str, new: str) -> None:
    _, body = _locate(doc, req_id)
    full = "\n".join(p.text for p in body)
    if old not in full:
        raise ValueError(f"Text {old!r} not found in {req_id}")
    set_requirement(doc, req_id, text=full.replace(old, new))


def remove_requirement(doc: DocxDocument, req_id: str) -> None:
    heading, body = _locate(doc, req_id)
    for p in [heading, *body]:
        p._p.getparent().remove(p._p)


def add_requirement(doc: DocxDocument, after_id: str, req_id: str, title: str, text: str) -> None:
    """Insert a new requirement after an existing one, copying its formatting."""
    heading, body = _locate(doc, after_id)
    anchor = body[-1] if body else heading
    new_body = copy.deepcopy(body[0]._p if body else heading._p)
    new_heading = copy.deepcopy(heading._p)
    anchor._p.addnext(new_body)
    anchor._p.addnext(new_heading)
    _set_text(Paragraph(new_heading, anchor._parent), f"{req_id}  {title}")
    _set_text(Paragraph(new_body, anchor._parent), text)


def replace_everywhere(doc: DocxDocument, old: str, new: str) -> int:
    """Replace text in all paragraphs and table cells (e.g. the revision label)."""
    count = 0
    paragraphs = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)
    for p in paragraphs:
        if old in p.text:
            _set_text(p, p.text.replace(old, new))
            count += 1
    return count

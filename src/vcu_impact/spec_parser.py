"""Parse a Word specification into requirements and non-requirement sections.

Detection is based on the requirement-ID pattern at the start of a short paragraph
(e.g. ``VCU-DR-01  Driver torque response``), not on colours or styles, so the
parser keeps working when a document is edited and re-saved in Word.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from vcu_impact.models import Requirement, SpecDocument, SpecSection

# An ID is 2+ dash-separated upper-case tokens ending in a number: VCU-DR-01, VCU-THM-07.
REQ_ID_PATTERN = r"[A-Z][A-Z0-9]{1,9}(?:-[A-Z0-9]{1,10})*-\d{1,4}"
_HEADING_RE = re.compile(rf"^\s*(?P<id>{REQ_ID_PATTERN})(?![\w-])[\s:.–—-]*(?P<title>.*)$")
_MAX_HEADING_LEN = 120
_REVISION_RE = re.compile(r"\bRevision\s+[A-Z0-9]+\b[^·•\n]*", re.IGNORECASE)

FRONT_MATTER = "Front matter"
DOCUMENT_RECORD = "Document record"


def _normalize(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", text).strip()


def _paragraph_text(p: Paragraph) -> str:
    """Paragraph text as if all tracked changes were accepted.

    python-docx ignores runs inside ``w:ins`` and ``w:del``; reading them would lose an inserted limit entirely.
    Insertions are kept, deletions (``w:del``, ``w:moveFrom``) are dropped, text boxes are left out (they would be
    duplicated by Word's fallback copies).
    """
    parts: list[str] = []
    for node in p._p.iter():
        if node.tag == qn("w:t"):
            if not node.xpath("ancestor::w:del | ancestor::w:moveFrom | ancestor::w:txbxContent"):
                parts.append(node.text or "")
        elif node.tag == qn("w:tab"):
            parts.append("\t")
        elif node.tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
    return "".join(parts)


def _tracked_changes_warning(doc, source_name: str) -> list[str]:
    n_ins = len(doc.element.body.xpath(".//w:ins[w:r]"))
    n_del = len(doc.element.body.xpath(".//w:del[w:r]"))
    if not (n_ins or n_del):
        return []
    return [
        f"{source_name} contains tracked changes ({n_ins} insertion(s), {n_del} deletion(s)). It is read as if all "
        "of them were accepted; accept or reject them in Word if that is not what you want."
    ]


def _style_name(p: Paragraph) -> str:
    try:
        return (p.style.name or "") if p.style is not None else ""
    except (KeyError, ValueError):
        return ""


def _is_section_heading(p: Paragraph) -> bool:
    name = _style_name(p).lower()
    return name.startswith("heading") or name == "title"


def parse_spec(source: str | Path | BinaryIO | bytes, source_name: str | None = None) -> SpecDocument:
    if isinstance(source, bytes):
        source = BytesIO(source)
    if source_name is None:
        source_name = Path(source).name if isinstance(source, (str, Path)) else "uploaded.docx"
    doc = Document(source)

    title = ""
    revision = ""
    requirements: list[Requirement] = []
    sections: dict[str, list[str]] = {}
    current_section = FRONT_MATTER
    current_req: dict | None = None

    def close_req() -> None:
        nonlocal current_req
        if current_req is not None:
            requirements.append(
                Requirement(
                    req_id=current_req["id"],
                    title=current_req["title"],
                    text="\n".join(current_req["body"]).strip(),
                )
            )
            current_req = None

    for block in doc.iter_inner_content():
        if isinstance(block, Table):
            close_req()
            rows = []
            for row in block.rows:
                cells = [_normalize(c.text) for c in row.cells]
                rows.append(" | ".join(cells))
                if len(cells) >= 2 and cells[0].lower() in {"document state", "revision"}:
                    revision = revision or cells[1]
            sections.setdefault(DOCUMENT_RECORD, []).extend(rows)
            continue

        text = _normalize(_paragraph_text(block))
        if not text:
            continue
        style = _style_name(block).lower()

        if style == "title":
            title = title or text
            sections.setdefault(FRONT_MATTER, []).append(text)
            continue

        match = _HEADING_RE.match(text)
        if match and (len(text) <= _MAX_HEADING_LEN or _is_section_heading(block)):
            close_req()
            current_req = {"id": match.group("id"), "title": match.group("title").strip(), "body": []}
            continue
        if match:
            # Long paragraph starting with an ID: a requirement without a separate title line.
            close_req()
            current_req = {"id": match.group("id"), "title": "", "body": [match.group("title").strip()]}
            continue

        if _is_section_heading(block):
            close_req()
            current_section = text
            sections.setdefault(current_section, [])
            continue

        if current_req is not None:
            current_req["body"].append(text)
        else:
            sections.setdefault(current_section, []).append(text)
            if not revision and current_section == FRONT_MATTER:
                m = _REVISION_RE.search(text)
                if m:
                    revision = _normalize(m.group(0))

    close_req()
    _check_duplicates(requirements)
    return SpecDocument(
        source_name=source_name,
        title=title,
        revision=revision,
        requirements=requirements,
        sections=[SpecSection(name=k, text="\n".join(v)) for k, v in sections.items()],
        warnings=_tracked_changes_warning(doc, source_name),
    )


def _check_duplicates(requirements: list[Requirement]) -> None:
    seen: set[str] = set()
    for r in requirements:
        if r.req_id in seen:
            raise ValueError(f"Duplicate requirement ID in specification: {r.req_id}")
        seen.add(r.req_id)

"""Deterministic, requirement-level diff between two parsed specifications."""

from __future__ import annotations

import difflib
import re
from collections import defaultdict

from vcu_impact.models import (
    ChangeType,
    NumericChange,
    RequirementChange,
    SectionChange,
    SpecDiff,
    SpecDocument,
)

_UNIT_ALIASES = {
    "ms": "ms",
    "millisecond": "ms",
    "milliseconds": "ms",
    "s": "s",
    "sec": "s",
    "second": "s",
    "seconds": "s",
    "%": "%",
    "percent": "%",
    "hz": "Hz",
    "khz": "kHz",
    "v": "V",
    "a": "A",
    "nm": "Nm",
    "km/h": "km/h",
    "kph": "km/h",
    "rpm": "rpm",
    "°c": "°C",
    "degc": "°C",
}
_NUMBER_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>%|°C|km/h|[A-Za-z]+)?", re.UNICODE)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_quantities(text: str) -> list[tuple[str, float, str]]:
    """Return (unit, value, matched_text) for every number in the text.

    Numbers without a recognised unit get the unit ``""`` so that a change of a
    bare count is still reported.
    """
    out = []
    for m in _NUMBER_RE.finditer(text):
        raw_unit = (m.group("unit") or "").lower()
        unit = _UNIT_ALIASES.get(raw_unit, "")
        matched = m.group(0) if unit else m.group("num")
        out.append((unit, float(m.group("num").replace(",", ".")), matched.strip()))
    return out


def numeric_changes(old: str, new: str) -> list[NumericChange]:
    """Pair numbers by unit and order of appearance; report the ones that differ."""
    old_by_unit: dict[str, list] = defaultdict(list)
    new_by_unit: dict[str, list] = defaultdict(list)
    for unit, value, text in extract_quantities(old):
        old_by_unit[unit].append((value, text))
    for unit, value, text in extract_quantities(new):
        new_by_unit[unit].append((value, text))

    changes = []
    for unit in list(dict.fromkeys([*old_by_unit, *new_by_unit])):
        olds, news = old_by_unit.get(unit, []), new_by_unit.get(unit, [])
        for i in range(max(len(olds), len(news))):
            o = olds[i] if i < len(olds) else None
            n = news[i] if i < len(news) else None
            if o and n and o[0] == n[0]:
                continue
            changes.append(
                NumericChange(
                    unit=unit,
                    old_value=o[0] if o else None,
                    new_value=n[0] if n else None,
                    old_text=o[1] if o else None,
                    new_text=n[1] if n else None,
                )
            )
    return changes


def word_diff(old: str, new: str) -> list[tuple[str, str]]:
    """Word-level diff as a list of (op, text) with op in {'equal', 'delete', 'insert'}.

    Neighbouring changes separated only by whitespace are merged, so a replaced phrase
    reads as one deleted and one inserted block instead of alternating words.
    """
    a, b = re.findall(r"\S+|\s+", old or ""), re.findall(r"\S+|\s+", new or "")
    raw: list[tuple[str, str, str]] = []  # (tag, old_text, new_text)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        raw.append((tag, "".join(a[i1:i2]), "".join(b[j1:j2])))

    merged: list[list[str]] = []  # [tag, old, new]
    for k, (tag, o, n) in enumerate(raw):
        between_changes = 0 < k < len(raw) - 1 and raw[k - 1][0] != "equal" and raw[k + 1][0] != "equal"
        if tag == "equal" and not (o.isspace() and between_changes):
            merged.append(["equal", o, n])
        elif merged and merged[-1][0] == "change":
            merged[-1][1] += o
            merged[-1][2] += n
        else:
            merged.append(["change", o, n])

    segments: list[tuple[str, str]] = []
    for tag, o, n in merged:
        if tag == "equal":
            segments.append(("equal", o))
            continue
        if o:
            segments.append(("delete", o))
        if n:
            segments.append(("insert", n))
    return segments


def is_rewrite(segments: list[tuple[str, str]], threshold: float = 0.5) -> bool:
    """True when less than ``threshold`` of the text is unchanged: show old and new separately."""
    equal = sum(len(t) for op, t in segments if op == "equal" and t.strip())
    total = equal + sum(len(t) for op, t in segments if op != "equal")
    return total > 0 and equal / total < threshold


def diff_specs(baseline: SpecDocument, revised: SpecDocument) -> SpecDiff:
    old_reqs = {r.req_id: r for r in baseline.requirements}
    new_reqs = {r.req_id: r for r in revised.requirements}
    changes: list[RequirementChange] = []
    unchanged: list[str] = []

    # Keep the revised document order, then append removed requirements.
    for req_id in [*new_reqs, *[i for i in old_reqs if i not in new_reqs]]:
        old, new = old_reqs.get(req_id), new_reqs.get(req_id)
        if old is None:
            changes.append(
                RequirementChange(
                    req_id=req_id,
                    change_type=ChangeType.ADDED,
                    new=new,
                    numeric_changes=numeric_changes("", new.text),
                )
            )
        elif new is None:
            changes.append(RequirementChange(req_id=req_id, change_type=ChangeType.REMOVED, old=old))
        elif _norm(old.text) != _norm(new.text) or _norm(old.title) != _norm(new.title):
            changes.append(
                RequirementChange(
                    req_id=req_id,
                    change_type=ChangeType.MODIFIED,
                    old=old,
                    new=new,
                    title_changed=_norm(old.title) != _norm(new.title),
                    numeric_changes=numeric_changes(old.text, new.text),
                )
            )
        else:
            unchanged.append(req_id)

    old_secs = {s.name: s.text for s in baseline.sections}
    new_secs = {s.name: s.text for s in revised.sections}
    section_changes = [
        SectionChange(name=name, old_text=old_secs.get(name), new_text=new_secs.get(name))
        for name in dict.fromkeys([*old_secs, *new_secs])
        if _norm(old_secs.get(name) or "") != _norm(new_secs.get(name) or "")
    ]

    return SpecDiff(
        baseline_name=baseline.source_name,
        revised_name=revised.source_name,
        baseline_revision=baseline.revision,
        revised_revision=revised.revision,
        requirement_changes=changes,
        unchanged_requirement_ids=unchanged,
        section_changes=section_changes,
    )

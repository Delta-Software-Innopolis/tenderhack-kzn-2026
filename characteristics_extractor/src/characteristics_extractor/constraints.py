"""Recognize numeric intervals without relying on the model's scalar output."""

import re

from .schemas import SourceSpan
from .units import EXTRA_INPUT_UNITS, OKEI


_NUMBER = r"[+\-−]?\d+(?:[.,]\d+)?"
_UNIT = "(?:" + "|".join(
    re.escape(alias)
    for alias in sorted({alias for spec in (*OKEI.values(), *EXTRA_INPUT_UNITS)
                         for alias in spec.aliases}, key=lambda value: (-len(value), value))
) + ")"
_VALUE = rf"{_NUMBER}(?:\s*{_UNIT}(?!\w))?"
# Boundaries exclude fragments of article numbers, dates and dimensions.
# No assumptions about which characteristic an interval belongs to are made.
_RANGE = re.compile(
    rf"(?<![\w.,/+\-−–—])(?:от\s+{_VALUE}\s+до\s+{_VALUE}|"
    rf"{_VALUE}\s*[-–—]\s*{_VALUE})(?!\w|[.,]\d|[-–—/]\d)",
    re.IGNORECASE,
)


def numeric_range_spans(query: str) -> list[SourceSpan]:
    return [SourceSpan(start=match.start(), end=match.end()) for match in _RANGE.finditer(query)]


def overlaps(left: SourceSpan, right: SourceSpan) -> bool:
    return max(left.start, right.start) < min(left.end, right.end)

"""Normalization helpers for messy IDs and dates.

DB + mock APIs return mixed formats:
  IDs:  "c123" vs "C123" vs " C123 "
  Dates: "2026-08-14" vs "08/14/26" vs "Aug 14 2026" vs "11/30/25"

Candidate TODO: use these everywhere tool outputs are built so the model
always sees canonical forms (upper IDs, ISO dates). Extend as needed.
"""

from __future__ import annotations

import re
from datetime import date, datetime

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def normalize_id(value: str) -> str:
    return value.strip().upper()


def parse_date(value: str) -> date | None:
    """Parse the known mixed formats. Returns None if unparseable."""
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%b %d %Y", "%B %d %Y", "%b %d %y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # "Aug 14 2026" without comma is covered above; try month-name fallback.
    match = re.match(r"([A-Za-z]+)\s+(\d{1,2})\s+(\d{2,4})", text)
    if match:
        month = _MONTHS.get(match[1].lower())
        if month:
            year = int(match[3])
            if year < 100:
                year += 2000
            try:
                return date(year, month, int(match[2]))
            except ValueError:
                return None
    return None


def to_iso(value: str) -> str:
    """Best-effort to ISO (YYYY-MM-DD). Returns original if unparseable."""
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else value

import difflib
from datetime import date
from typing import Optional

from dateutil import parser as dateutil_parser


def normalize_string(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def string_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_string(a), normalize_string(b)).ratio()


def parse_date_loose(value: str) -> Optional[date]:
    try:
        return dateutil_parser.parse(value, fuzzy=False).date()
    except (ValueError, OverflowError, TypeError):
        return None


def is_numeric_close(a: float, b: float, *, abs_tolerance: float) -> bool:
    return abs(a - b) <= abs_tolerance

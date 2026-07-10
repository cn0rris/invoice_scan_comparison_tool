from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class MismatchType(str, Enum):
    MISSING_FIELD = "missing_field"
    EXTRA_FIELD = "extra_field"
    WRONG_VALUE = "wrong_value"
    NUMERIC_OFF = "numeric_off"
    DATE_MISMATCH = "date_mismatch"
    STRING_NEAR_MATCH = "string_near_match"
    MISSING_LINE_ITEM = "missing_line_item"
    EXTRA_LINE_ITEM = "extra_line_item"
    PARSE_FAILURE = "parse_failure"
    LINE_ITEMS_SUBTOTAL_MISMATCH = "line_items_subtotal_mismatch"
    SUBTOTAL_TAX_TOTAL_MISMATCH = "subtotal_tax_total_mismatch"


class Mismatch(BaseModel):
    field_path: str
    mismatch_type: MismatchType
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    message: str


class DiffResult(BaseModel):
    mismatches: list[Mismatch]
    mistake_count: int

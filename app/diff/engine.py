from typing import Any, Optional

from app.diff.types import DiffResult, Mismatch, MismatchType
from app.models.invoice import InvoiceExtraction, LineItem
from app.utils.textmatch import is_numeric_close, normalize_string, parse_date_loose, string_similarity

_STRING_FIELDS = ["invoice_number", "vendor_name", "client_name", "matter_number", "currency"]
_NUMERIC_FIELDS = ["subtotal", "tax", "total"]
_LINE_ITEM_MIN_PAIR_SCORE = 0.4


def _string_mismatch(
    field_path: str, expected: Optional[str], actual: Optional[str], threshold: float
) -> Optional[Mismatch]:
    if expected is None and actual is None:
        return None
    if expected is not None and actual is None:
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.MISSING_FIELD,
            expected=expected,
            actual=None,
            message=f"Missing field '{field_path}': ground truth expected '{expected}' but was not extracted.",
        )
    if expected is None and actual is not None:
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.EXTRA_FIELD,
            expected=None,
            actual=actual,
            message=f"Extra/hallucinated field '{field_path}': model returned '{actual}' but ground truth has no value.",
        )
    if normalize_string(str(expected)) == normalize_string(str(actual)):
        return None
    similarity = string_similarity(str(expected), str(actual))
    if similarity >= threshold:
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.STRING_NEAR_MATCH,
            expected=expected,
            actual=actual,
            message=f"Wrong value for '{field_path}': expected '{expected}', got '{actual}' (close match).",
        )
    return Mismatch(
        field_path=field_path,
        mismatch_type=MismatchType.WRONG_VALUE,
        expected=expected,
        actual=actual,
        message=f"Wrong value for '{field_path}': expected '{expected}', got '{actual}'.",
    )


def _numeric_mismatch(
    field_path: str, expected: Optional[float], actual: Optional[float], abs_tolerance: float
) -> Optional[Mismatch]:
    if expected is None and actual is None:
        return None
    if expected is not None and actual is None:
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.MISSING_FIELD,
            expected=expected,
            actual=None,
            message=f"Missing field '{field_path}': ground truth expected {expected} but was not extracted.",
        )
    if expected is None and actual is not None:
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.EXTRA_FIELD,
            expected=None,
            actual=actual,
            message=f"Extra/hallucinated field '{field_path}': model returned {actual} but ground truth has no value.",
        )
    try:
        expected_f, actual_f = float(expected), float(actual)
    except (TypeError, ValueError):
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.WRONG_VALUE,
            expected=expected,
            actual=actual,
            message=f"Wrong value for '{field_path}': expected {expected}, got non-numeric '{actual}'.",
        )
    if is_numeric_close(expected_f, actual_f, abs_tolerance=abs_tolerance):
        return None
    delta = abs(expected_f - actual_f)
    return Mismatch(
        field_path=field_path,
        mismatch_type=MismatchType.NUMERIC_OFF,
        expected=expected_f,
        actual=actual_f,
        message=(
            f"Numeric mismatch for {field_path}: expected {expected_f}, got {actual_f} "
            f"(off by {delta:.2f}, tolerance {abs_tolerance})."
        ),
    )


def _date_mismatch(field_path: str, expected: Optional[str], actual: Optional[str]) -> Optional[Mismatch]:
    if expected is None and actual is None:
        return None
    if expected is not None and actual is None:
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.MISSING_FIELD,
            expected=expected,
            actual=None,
            message=f"Missing field '{field_path}': ground truth expected '{expected}' but was not extracted.",
        )
    if expected is None and actual is not None:
        return Mismatch(
            field_path=field_path,
            mismatch_type=MismatchType.EXTRA_FIELD,
            expected=None,
            actual=actual,
            message=f"Extra/hallucinated field '{field_path}': model returned '{actual}' but ground truth has no value.",
        )
    expected_date = parse_date_loose(str(expected))
    actual_date = parse_date_loose(str(actual))
    if expected_date is not None and expected_date == actual_date:
        return None
    return Mismatch(
        field_path=field_path,
        mismatch_type=MismatchType.DATE_MISMATCH,
        expected=expected,
        actual=actual,
        message=f"Date mismatch for '{field_path}': expected '{expected}', got '{actual}'.",
    )


def _amount_pair_score(expected: LineItem, actual: dict[str, Any]) -> float:
    desc_score = string_similarity(expected.description, str(actual.get("description") or ""))
    exp_amt, act_amt = expected.amount, actual.get("amount")
    if exp_amt is None or act_amt is None:
        amount_score = 0.5
    else:
        try:
            exp_amt_f, act_amt_f = float(exp_amt), float(act_amt)
            if is_numeric_close(exp_amt_f, act_amt_f, abs_tolerance=0.01):
                amount_score = 1.0
            else:
                denom = max(abs(exp_amt_f), 1.0)
                amount_score = max(0.0, 1.0 - abs(exp_amt_f - act_amt_f) / denom)
        except (TypeError, ValueError):
            amount_score = 0.0
    return 0.6 * desc_score + 0.4 * amount_score


def _diff_line_items(
    expected_items: list[LineItem], actual_items: list[dict[str, Any]], numeric_abs_tolerance: float
) -> list[Mismatch]:
    mismatches: list[Mismatch] = []
    if not expected_items and not actual_items:
        return mismatches

    scored_pairs = []
    for i, exp in enumerate(expected_items):
        for j, act in enumerate(actual_items):
            scored_pairs.append((_amount_pair_score(exp, act), i, j))
    scored_pairs.sort(key=lambda t: t[0], reverse=True)

    matched_expected: dict[int, int] = {}
    used_actual: set[int] = set()
    for score, i, j in scored_pairs:
        if i in matched_expected or j in used_actual:
            continue
        if score < _LINE_ITEM_MIN_PAIR_SCORE:
            continue
        matched_expected[i] = j
        used_actual.add(j)

    for i, exp in enumerate(expected_items):
        if i not in matched_expected:
            mismatches.append(
                Mismatch(
                    field_path=f"line_items[{i}]",
                    mismatch_type=MismatchType.MISSING_LINE_ITEM,
                    expected=exp.model_dump(),
                    actual=None,
                    message=(
                        f"Missing line item: expected '{exp.description}' "
                        f"(amount {exp.amount}) was not found in extracted output."
                    ),
                )
            )
            continue
        act = actual_items[matched_expected[i]]
        prefix = f"line_items[{i}]"
        m = _string_mismatch(f"{prefix}.description", exp.description, act.get("description"), 0.85)
        if m:
            mismatches.append(m)
        for numeric_field in ("hours", "rate", "amount"):
            m = _numeric_mismatch(
                f"{prefix}.{numeric_field}",
                getattr(exp, numeric_field),
                act.get(numeric_field),
                numeric_abs_tolerance,
            )
            if m:
                mismatches.append(m)

    for j, act in enumerate(actual_items):
        if j not in used_actual:
            mismatches.append(
                Mismatch(
                    field_path=f"line_items[extra:{j}]",
                    mismatch_type=MismatchType.EXTRA_LINE_ITEM,
                    expected=None,
                    actual=act,
                    message=(
                        f"Extra/hallucinated line item: model returned "
                        f"'{act.get('description')}' (amount {act.get('amount')}) not present in ground truth."
                    ),
                )
            )

    return mismatches


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_arithmetic(actual: dict[str, Any], abs_tolerance: float) -> list[Mismatch]:
    """Cross-checks internal arithmetic consistency of the model's own extracted
    values — independent of ground truth. Only runs where the necessary fields are
    all present: many invoices only print a total with no subtotal/tax breakdown,
    and that's not an error under this check, just nothing to verify."""
    mismatches: list[Mismatch] = []
    line_items = actual.get("line_items")
    if not isinstance(line_items, list):
        line_items = []

    subtotal = _to_float(actual.get("subtotal"))
    tax = _to_float(actual.get("tax"))
    total = _to_float(actual.get("total"))

    if subtotal is not None and line_items:
        amounts = [_to_float(li.get("amount")) if isinstance(li, dict) else None for li in line_items]
        if all(a is not None for a in amounts):
            line_items_sum = sum(amounts)
            if not is_numeric_close(line_items_sum, subtotal, abs_tolerance=abs_tolerance):
                delta = abs(line_items_sum - subtotal)
                mismatches.append(
                    Mismatch(
                        field_path="subtotal",
                        mismatch_type=MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH,
                        expected=None,
                        actual=subtotal,
                        message=(
                            f"Arithmetic inconsistency: line items sum to {line_items_sum:.2f} "
                            f"but subtotal is {subtotal:.2f} (off by {delta:.2f})."
                        ),
                    )
                )

    if subtotal is not None and tax is not None and total is not None:
        computed_total = subtotal + tax
        if not is_numeric_close(computed_total, total, abs_tolerance=abs_tolerance):
            delta = abs(computed_total - total)
            mismatches.append(
                Mismatch(
                    field_path="total",
                    mismatch_type=MismatchType.SUBTOTAL_TAX_TOTAL_MISMATCH,
                    expected=None,
                    actual=total,
                    message=(
                        f"Arithmetic inconsistency: subtotal ({subtotal:.2f}) + tax ({tax:.2f}) "
                        f"= {computed_total:.2f}, but total is {total:.2f} (off by {delta:.2f})."
                    ),
                )
            )

    return mismatches


def diff_invoice(
    expected: InvoiceExtraction,
    actual: Optional[dict[str, Any]],
    *,
    numeric_abs_tolerance: float = 0.01,
    string_similarity_threshold: float = 0.85,
) -> DiffResult:
    if actual is None:
        populated_fields = sum(
            1 for f in _STRING_FIELDS + _NUMERIC_FIELDS + ["invoice_date"] if getattr(expected, f) is not None
        )
        penalty = 1 + populated_fields + len(expected.line_items)
        mismatch = Mismatch(
            field_path="<document>",
            mismatch_type=MismatchType.PARSE_FAILURE,
            expected=None,
            actual=None,
            message="Model output could not be parsed or validated as JSON matching the extraction schema.",
        )
        return DiffResult(mismatches=[mismatch], mistake_count=penalty)

    mismatches: list[Mismatch] = []

    for field in _STRING_FIELDS:
        m = _string_mismatch(field, getattr(expected, field), actual.get(field), string_similarity_threshold)
        if m:
            mismatches.append(m)

    m = _date_mismatch("invoice_date", expected.invoice_date, actual.get("invoice_date"))
    if m:
        mismatches.append(m)

    for field in _NUMERIC_FIELDS:
        m = _numeric_mismatch(field, getattr(expected, field), actual.get(field), numeric_abs_tolerance)
        if m:
            mismatches.append(m)

    actual_line_items = actual.get("line_items") or []
    if not isinstance(actual_line_items, list):
        actual_line_items = []
    mismatches.extend(_diff_line_items(expected.line_items, actual_line_items, numeric_abs_tolerance))

    mismatches.extend(_check_arithmetic(actual, numeric_abs_tolerance))

    return DiffResult(mismatches=mismatches, mistake_count=len(mismatches))

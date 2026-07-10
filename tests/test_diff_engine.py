from app.diff.engine import diff_invoice
from app.diff.types import MismatchType
from app.models.invoice import InvoiceExtraction

BASE = {
    "invoice_number": "INV-1",
    "invoice_date": "2024-01-15",
    "vendor_name": "Harrison & Cole LLP",
    "client_name": "Acme Corp",
    "matter_number": "M-1",
    "line_items": [
        {"description": "Legal research", "timekeeper": "AB", "hours": 3.5, "rate": 250.0, "amount": 875.0},
        {"description": "Draft letter", "timekeeper": "CD", "hours": 1.0, "rate": 250.0, "amount": 250.0},
    ],
    "subtotal": 1125.0,
    "tax": 0.0,
    "total": 1125.0,
    "currency": "USD",
}


def expected() -> InvoiceExtraction:
    return InvoiceExtraction.model_validate(BASE)


def test_perfect_match_has_no_mismatches():
    result = diff_invoice(expected(), dict(BASE))
    assert result.mismatches == []
    assert result.mistake_count == 0


def test_missing_field():
    actual = dict(BASE)
    del actual["matter_number"]
    result = diff_invoice(expected(), actual)
    assert result.mistake_count == 1
    assert result.mismatches[0].mismatch_type == MismatchType.MISSING_FIELD
    assert "matter_number" in result.mismatches[0].message


def test_extra_field():
    exp = InvoiceExtraction.model_validate({**BASE, "matter_number": None})
    actual = dict(BASE)  # still has matter_number
    result = diff_invoice(exp, actual)
    assert result.mistake_count == 1
    assert result.mismatches[0].mismatch_type == MismatchType.EXTRA_FIELD


def test_wrong_value():
    actual = {**BASE, "vendor_name": "Completely Different Firm Name"}
    result = diff_invoice(expected(), actual)
    assert any(m.mismatch_type == MismatchType.WRONG_VALUE for m in result.mismatches)


def test_string_near_match():
    actual = {**BASE, "vendor_name": "Harrison and Cole LLP"}  # "&" -> "and"
    result = diff_invoice(expected(), actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.STRING_NEAR_MATCH in types
    assert MismatchType.WRONG_VALUE not in types


def test_numeric_within_tolerance_is_ok():
    actual = {**BASE, "total": 1125.005}
    result = diff_invoice(expected(), actual)
    assert result.mistake_count == 0


def test_numeric_off():
    actual = {**BASE, "total": 1100.0}
    result = diff_invoice(expected(), actual)
    # Changing only "total" also makes subtotal+tax no longer equal the new total —
    # a second, legitimate finding from the new arithmetic cross-check.
    assert result.mistake_count == 2
    m = next(m for m in result.mismatches if m.mismatch_type == MismatchType.NUMERIC_OFF)
    assert "25.00" in m.message


def test_date_format_only_difference_is_ok():
    actual = {**BASE, "invoice_date": "01/15/2024"}
    result = diff_invoice(expected(), actual)
    assert result.mistake_count == 0


def test_date_mismatch():
    actual = {**BASE, "invoice_date": "2024-02-20"}
    result = diff_invoice(expected(), actual)
    assert result.mistake_count == 1
    assert result.mismatches[0].mismatch_type == MismatchType.DATE_MISMATCH


def test_missing_line_item():
    actual = dict(BASE)
    actual["line_items"] = [BASE["line_items"][0]]  # drop the second line item
    result = diff_invoice(expected(), actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.MISSING_LINE_ITEM in types
    # The remaining line item no longer sums to the (unchanged) subtotal — a second,
    # legitimate finding from the new arithmetic cross-check.
    assert MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH in types
    assert result.mistake_count == 2


def test_extra_line_item():
    actual = dict(BASE)
    actual["line_items"] = BASE["line_items"] + [
        {"description": "Hallucinated extra work", "hours": 2.0, "rate": 100.0, "amount": 200.0}
    ]
    result = diff_invoice(expected(), actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.EXTRA_LINE_ITEM in types
    assert MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH in types
    assert result.mistake_count == 2


def test_matched_line_item_field_mismatch():
    actual = dict(BASE)
    actual["line_items"] = [
        {"description": "Legal research", "timekeeper": "AB", "hours": 3.5, "rate": 250.0, "amount": 800.0},  # amount wrong
        BASE["line_items"][1],
    ]
    result = diff_invoice(expected(), actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH in types
    m = next(m for m in result.mismatches if m.field_path == "line_items[0].amount")
    assert m.mismatch_type == MismatchType.NUMERIC_OFF
    assert m.field_path == "line_items[0].amount"


def test_line_item_timekeeper_wrong_value():
    actual = dict(BASE)
    actual["line_items"] = [
        {**BASE["line_items"][0], "timekeeper": "XY"},  # wrong timekeeper
        BASE["line_items"][1],
    ]
    result = diff_invoice(expected(), actual)
    m = next(m for m in result.mismatches if m.field_path == "line_items[0].timekeeper")
    assert m.mismatch_type == MismatchType.WRONG_VALUE
    assert m.expected == "AB"
    assert m.actual == "XY"


def test_line_item_timekeeper_missing_is_flagged():
    actual = dict(BASE)
    actual["line_items"] = [
        {k: v for k, v in BASE["line_items"][0].items() if k != "timekeeper"},  # model omitted it
        BASE["line_items"][1],
    ]
    result = diff_invoice(expected(), actual)
    m = next(m for m in result.mismatches if m.field_path == "line_items[0].timekeeper")
    assert m.mismatch_type == MismatchType.MISSING_FIELD


def test_line_item_timekeeper_both_absent_is_ok():
    exp = InvoiceExtraction.model_validate(
        {**BASE, "line_items": [{k: v for k, v in li.items() if k != "timekeeper"} for li in BASE["line_items"]]}
    )
    actual = {**BASE, "line_items": [{k: v for k, v in li.items() if k != "timekeeper"} for li in BASE["line_items"]]}
    result = diff_invoice(exp, actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert not any(m.field_path.endswith(".timekeeper") for m in result.mismatches)


def test_parse_failure_none_actual():
    result = diff_invoice(expected(), None)
    assert result.mismatches[0].mismatch_type == MismatchType.PARSE_FAILURE
    # penalty = 1 + populated top-level fields (6: number, date, vendor, client, matter, subtotal, tax, total -> check count) + line items
    assert result.mistake_count > 1


def test_arithmetic_line_items_subtotal_mismatch():
    actual = dict(BASE)
    actual["subtotal"] = 1200.0  # line items still sum to 1125.0
    actual["total"] = 1200.0  # keep subtotal+tax==total consistent so only one mismatch fires
    result = diff_invoice(expected(), actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH in types
    m = next(m for m in result.mismatches if m.mismatch_type == MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH)
    assert "75.00" in m.message


def test_arithmetic_subtotal_tax_total_mismatch():
    actual = dict(BASE)
    actual["tax"] = 100.0
    # total stays 1125.0, but subtotal (1125) + tax (100) = 1225 != total
    result = diff_invoice(expected(), actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.SUBTOTAL_TAX_TOTAL_MISMATCH in types
    m = next(m for m in result.mismatches if m.mismatch_type == MismatchType.SUBTOTAL_TAX_TOTAL_MISMATCH)
    assert "100.00" in m.message


def test_arithmetic_skipped_when_subtotal_and_tax_absent():
    # Some invoices only print a total, with no subtotal/tax breakdown at all —
    # that's not an arithmetic error, just nothing to cross-check.
    actual = {**BASE, "subtotal": None, "tax": None}
    exp = InvoiceExtraction.model_validate({**BASE, "subtotal": None, "tax": None})
    result = diff_invoice(exp, actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH not in types
    assert MismatchType.SUBTOTAL_TAX_TOTAL_MISMATCH not in types


def test_arithmetic_skipped_when_a_line_item_amount_is_missing():
    actual = dict(BASE)
    actual["line_items"] = [
        {"description": "Legal research", "hours": 3.5, "rate": 250.0, "amount": None},
        BASE["line_items"][1],
    ]
    result = diff_invoice(expected(), actual)
    types = [m.mismatch_type for m in result.mismatches]
    assert MismatchType.LINE_ITEMS_SUBTOTAL_MISMATCH not in types

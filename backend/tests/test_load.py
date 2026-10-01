from datetime import date

from app.pipeline.load import in_period, is_other, join_returns

VENDORS = [{"vendor_id": "V1", "name": "Jaipur Prints"}]
SKUS = [
    {"sku_id": "S1", "vendor_id": "V1", "category": "womenswear", "is_live": True},
    {"sku_id": "S-PULLED", "vendor_id": "V1", "category": "kidswear", "is_live": False},
    {"sku_id": "S-NOVENDOR", "vendor_id": None, "category": "mens", "is_live": True},
    {"sku_id": "S-GHOSTVENDOR", "vendor_id": "V404", "category": "mens", "is_live": True},
]
ORDER_LINES = [
    {"order_line_id": "L1", "sku_id": "S1", "size": "M", "quantity": 1, "order_date": date(2026, 8, 10)},
    {"order_line_id": "L2", "sku_id": "S-PULLED", "size": "4Y", "quantity": 1, "order_date": date(2026, 8, 11)},
    {"order_line_id": "L3", "sku_id": "S-NOVENDOR", "size": "L", "quantity": 1, "order_date": date(2026, 8, 12)},
    {"order_line_id": "L4", "sku_id": "S-MISSING", "size": "L", "quantity": 1, "order_date": date(2026, 8, 12)},
    {"order_line_id": "L5", "sku_id": "S-GHOSTVENDOR", "size": "L", "quantity": 1, "order_date": date(2026, 8, 12)},
]


def ret(return_id, order_line_id, text="size chhota"):
    return {
        "return_id": return_id, "order_line_id": order_line_id, "other_text": text,
        "return_date": date(2026, 8, 20), "dropdown_reason": "Other",
    }


def join(returns):
    return {j.return_id: j for j in join_returns(returns, ORDER_LINES, SKUS, VENDORS)}


def test_matched_return_resolves_sku_vendor_and_order_details():
    j = join([ret("R1", "L1")])["R1"]
    assert j.matched
    assert (j.sku_id, j.vendor_id, j.category, j.size) == ("S1", "V1", "womenswear", "M")
    assert j.order_date == date(2026, 8, 10)
    assert j.text == "size chhota"


def test_pulled_sku_still_resolves_its_vendor():
    j = join([ret("R2", "L2")])["R2"]
    assert j.matched and j.vendor_id == "V1" and j.sku_id == "S-PULLED"


def test_unmatched_returns_are_kept_with_a_reason():
    joined = join([
        ret("R-NULL", None),
        ret("R-BLANK", "  "),
        ret("R-NOLINE", "L999"),
        ret("R-NOSKU", "L4"),
        ret("R-NOVENDOR", "L3"),
        ret("R-GHOST", "L5"),
    ])
    assert len(joined) == 6  # nothing dropped
    assert all(not j.matched and j.vendor_id is None for j in joined.values())
    assert "no order line" in joined["R-NULL"].unmatched_why
    assert "no order line" in joined["R-BLANK"].unmatched_why
    assert "not found in orders" in joined["R-NOLINE"].unmatched_why
    assert "SKU not found" in joined["R-NOSKU"].unmatched_why
    assert "no vendor" in joined["R-NOVENDOR"].unmatched_why
    assert "no vendor" in joined["R-GHOST"].unmatched_why


def test_is_other_ignores_case_and_spaces():
    assert is_other({"dropdown_reason": "Other"})
    assert is_other({"dropdown_reason": " other "})
    assert not is_other({"dropdown_reason": "Size issue"})
    assert not is_other({"dropdown_reason": None})


def test_period_uses_order_date_for_matched_returns():
    j = join([ret("R1", "L1")])["R1"]  # ordered 10 Aug, returned 20 Aug
    assert in_period(j, None, None)
    assert in_period(j, date(2026, 8, 1), date(2026, 8, 10))
    assert not in_period(j, date(2026, 8, 11), None)  # return date is inside, order date is not
    assert not in_period(j, None, date(2026, 8, 9))


def test_period_uses_return_date_for_unmatched_returns():
    j = join([ret("R-NULL", None)])["R-NULL"]  # returned 20 Aug, no order
    assert in_period(j, date(2026, 8, 15), date(2026, 8, 31))
    assert not in_period(j, date(2026, 9, 1), None)

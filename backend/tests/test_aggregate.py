"""Hand-computed fixture.

Womenswear:  V1 sold 100, V2 sold 300  -> category sold 400
  fit returns:     V1 = 12, V2 = 4     -> category 16 -> avg 16/400 = 0.04
    V1 rate 0.12 -> lift 3.0      V2 rate 0.0133 -> lift 0.333
  defect returns:  V1 = 1,  V2 = 3     -> category 4  -> avg 0.01
    V1 rate 0.01 -> lift 1.0      V2 rate 0.01 -> lift 1.0
  changed_mind:    V1 = 6               -> not vendor-caused, never flagged
Kidswear:    V1 sold 50 (2 fit returns), V3 sold 50 (0 returns) -> avg 2/100 = 0.02
    V1 rate 0.04 -> lift 2.0 but only 2 returns
"""

import pytest

from app.pipeline.aggregate import ClassifiedReturn, Sale, aggregate, top_skus

SALES = [
    Sale("V1", "womenswear", "W1", 60),
    Sale("V1", "womenswear", "W2", 40),
    Sale("V2", "womenswear", "W3", 300),
    Sale("V1", "kidswear", "K1", 50),
    Sale("V3", "kidswear", "K2", 50),
]


def returns_for(vendor, category, sku, reason, n, **kw):
    return [ClassifiedReturn(f"{vendor}-{sku}-{reason}-{i}", vendor, category, sku, reason, **kw) for i in range(n)]


RETURNS = (
    returns_for("V1", "womenswear", "W1", "fit", 9, fit_direction="runs_small")
    + returns_for("V1", "womenswear", "W2", "fit", 2, fit_direction="area_specific", fit_area="shoulders")
    + returns_for("V1", "womenswear", "W2", "fit", 1)
    + returns_for("V2", "womenswear", "W3", "fit", 4, fit_direction="runs_large")
    + returns_for("V1", "womenswear", "W1", "defect_quality", 1)
    + returns_for("V2", "womenswear", "W3", "defect_quality", 3)
    + returns_for("V1", "womenswear", "W1", "changed_mind", 6)
    + returns_for("V1", "kidswear", "K1", "fit", 2, fit_direction="runs_small")
)


def segments(min_returns=5, lift=2.0, sales=SALES, returns=RETURNS):
    result = aggregate(sales, returns, min_returns_to_flag=min_returns, lift_threshold=lift)
    return {(s.vendor_id, s.category): s for s in result}


def test_rates_category_average_and_lift():
    segs = segments()
    v1 = segs[("V1", "womenswear")]
    assert v1.units_sold == 100
    assert v1.cells["fit"].returns == 12
    assert v1.cells["fit"].rate == pytest.approx(0.12)
    assert v1.cells["fit"].category_avg == pytest.approx(0.04)
    assert v1.cells["fit"].lift == pytest.approx(3.0)
    assert v1.returns_total == 19

    v2 = segs[("V2", "womenswear")]
    assert v2.cells["fit"].rate == pytest.approx(4 / 300)
    assert v2.cells["fit"].lift == pytest.approx(1 / 3)
    assert v2.cells["defect_quality"].lift == pytest.approx(1.0)


def test_each_category_has_its_own_average():
    segs = segments()
    assert segs[("V1", "kidswear")].cells["fit"].category_avg == pytest.approx(0.02)
    assert segs[("V1", "kidswear")].cells["fit"].lift == pytest.approx(2.0)
    assert segs[("V1", "womenswear")].cells["fit"].category_avg == pytest.approx(0.04)


def test_flag_needs_both_volume_and_lift():
    segs = segments(min_returns=5, lift=2.0)
    assert segs[("V1", "womenswear")].cells["fit"].flagged  # 12 returns, 3.0x
    assert segs[("V1", "womenswear")].flagged
    assert not segs[("V1", "kidswear")].cells["fit"].flagged  # 2.0x but only 2 returns
    assert not segs[("V2", "womenswear")].flagged  # volume but no lift


def test_flag_thresholds_are_inclusive():
    assert segments(min_returns=12, lift=3.0)[("V1", "womenswear")].cells["fit"].flagged
    assert not segments(min_returns=13, lift=3.0)[("V1", "womenswear")].cells["fit"].flagged
    assert not segments(min_returns=12, lift=3.01)[("V1", "womenswear")].cells["fit"].flagged
    assert segments(min_returns=2, lift=2.0)[("V1", "kidswear")].cells["fit"].flagged


def test_non_vendor_reasons_are_never_flagged():
    # V1 has all 6 changed_mind returns: a huge lift, and plenty of volume.
    cell = segments(min_returns=1, lift=1.0)[("V1", "womenswear")].cells["changed_mind"]
    assert cell.returns == 6 and cell.lift == pytest.approx(4.0)
    assert not cell.flagged


def test_fit_breakdown():
    v1 = segments()[("V1", "womenswear")]
    assert v1.fit_directions == {"runs_small": 9, "area_specific": 2, "unclear": 1}
    assert v1.fit_areas == {"shoulders": 2}


def test_vendor_with_sales_but_no_returns_still_appears():
    v3 = segments()[("V3", "kidswear")]
    assert v3.units_sold == 50 and v3.returns_total == 0
    assert v3.cells["fit"].rate == 0 and v3.cells["fit"].lift == 0
    assert not v3.flagged


def test_no_division_by_zero():
    # Returns but nothing sold in the period, and a reason nobody in the category has.
    segs = segments(sales=[], returns=returns_for("V9", "mens", "M1", "fit", 3))
    cell = segs[("V9", "mens")].cells["fit"]
    assert cell.rate is None and cell.category_avg is None and cell.lift is None and not cell.flagged
    assert segments()[("V1", "womenswear")].cells["wrong_item"].lift is None  # category average is 0


def test_top_skus():
    stats = top_skus(SALES, RETURNS, "V1")
    assert [s.sku_id for s in stats] == ["W1", "W2", "K1"]
    w1 = stats[0]
    assert (w1.units_sold, w1.returns, w1.top_reason) == (60, 16, "fit")
    assert w1.rate == pytest.approx(16 / 60)

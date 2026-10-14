from datetime import date
from decimal import Decimal as D

import pytest

from twmarket.tick import (
    PRICE_LIMIT_10PCT_EFFECTIVE,
    Direction,
    PriceLimits,
    SecurityType,
    is_valid_price,
    price_limit_pct,
    price_limits,
    round_to_tick,
    tick_size,
)

STOCK = SecurityType.STOCK
ETF = SecurityType.ETF
BEFORE = date(2015, 5, 29)  # 7% 時期最後一個交易日（週五）
AFTER = date(2015, 6, 1)


class TestTickSize:
    @pytest.mark.parametrize(
        "price, tick",
        [
            ("0.01", "0.01"),
            ("9.99", "0.01"),
            ("10", "0.05"),  # 邊界：10 元屬 10～未滿 50
            ("49.95", "0.05"),
            ("50", "0.1"),
            ("99.9", "0.1"),
            ("100", "0.5"),
            ("499.5", "0.5"),
            ("500", "1"),
            ("999", "1"),
            ("1000", "5"),
            ("5000", "5"),
        ],
    )
    def test_stock_bands(self, price, tick):
        assert tick_size(D(price), STOCK) == D(tick)

    @pytest.mark.parametrize(
        "price, tick",
        [("0.01", "0.01"), ("49.99", "0.01"), ("50", "0.05"), ("1200", "0.05")],
    )
    def test_etf_bands(self, price, tick):
        assert tick_size(D(price), ETF) == D(tick)

    @pytest.mark.parametrize("bad", ["0", "-1"])
    def test_non_positive_rejected(self, bad):
        with pytest.raises(ValueError):
            tick_size(D(bad))

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            tick_size(95.5)

    def test_stock_before_2005_unsupported(self):
        with pytest.raises(ValueError):
            tick_size(D(20), STOCK, date(2005, 2, 28))
        assert tick_size(D(20), STOCK, date(2005, 3, 1)) == D("0.05")

    def test_same_table_both_sides_of_2015(self):
        for p in ("9", "30", "70", "300", "700", "1500"):
            assert tick_size(D(p), STOCK, BEFORE) == tick_size(D(p), STOCK, AFTER)


class TestRoundToTick:
    def test_down_and_up(self):
        assert round_to_tick(D("105.05"), Direction.DOWN) == D("105.0")
        assert round_to_tick(D("85.95"), Direction.UP) == D("86.0")

    def test_valid_price_unchanged(self):
        assert round_to_tick(D("44.65"), Direction.DOWN) == D("44.65")
        assert round_to_tick(D("44.65"), Direction.UP) == D("44.65")

    def test_up_crosses_band_boundary(self):
        assert round_to_tick(D("49.98"), Direction.UP) == D("50.00")
        assert round_to_tick(D("999.5"), Direction.UP) == D(1000)

    def test_down_at_band_lower_edge(self):
        assert round_to_tick(D("100.03"), Direction.DOWN) == D(100)

    def test_etf_finer_tick(self):
        assert round_to_tick(D("105.07"), Direction.DOWN, ETF) == D("105.05")


class TestIsValidPrice:
    @pytest.mark.parametrize("p", ["86.0", "105.0", "44.65", "1005", "9.99"])
    def test_valid(self, p):
        assert is_valid_price(D(p))

    @pytest.mark.parametrize("p", ["105.05", "44.66", "1001", "0", "-5"])
    def test_invalid_stock(self, p):
        assert not is_valid_price(D(p))

    def test_etf_vs_stock(self):
        assert is_valid_price(D("105.05"), ETF)
        assert not is_valid_price(D("105.05"), STOCK)


class TestPriceLimitPct:
    def test_switch_date(self):
        assert PRICE_LIMIT_10PCT_EFFECTIVE == date(2015, 6, 1)
        assert price_limit_pct(BEFORE) == D("0.07")
        assert price_limit_pct(AFTER) == D("0.10")
        assert price_limit_pct(None) == D("0.10")


class TestPriceLimits:
    def test_required_case_95_5(self):
        """指定測試：參考價 95.5，跌停 86.0、漲停 105.0。"""
        limits = price_limits(D("95.5"), STOCK, AFTER)
        assert limits == PriceLimits(limit_down=D("86.0"), limit_up=D("105.0"))

    def test_twse_official_example(self):
        # 證交所範例：基準價 40.60，漲停 44.66 → 44.65；跌停 36.54 → 36.55
        limits = price_limits(D("40.60"))
        assert limits.limit_up == D("44.65")
        assert limits.limit_down == D("36.55")

    def test_seven_percent_era(self):
        # 95.5 × 1.07 = 102.185 → 102.0；95.5 × 0.93 = 88.815 → 88.9
        limits = price_limits(D("95.5"), STOCK, BEFORE)
        assert limits == PriceLimits(limit_down=D("88.9"), limit_up=D("102.0"))

    def test_etf_uses_etf_ticks(self):
        limits = price_limits(D("95.5"), ETF, AFTER)
        assert limits == PriceLimits(limit_down=D("85.95"), limit_up=D("105.05"))

    def test_limits_never_exceed_pct(self):
        for ref in ("9.87", "10.05", "48.3", "51.2", "99.9", "123.5", "987", "1234"):
            r = D(ref)
            lim = price_limits(r)
            assert lim.limit_up <= r * D("1.1")
            assert lim.limit_down >= r * D("0.9")
            assert is_valid_price(lim.limit_up) and is_valid_price(lim.limit_down)

    def test_limit_up_cross_band(self):
        # 95 × 1.1 = 104.5（100 以上檔位 0.5，有效）
        assert price_limits(D(95)).limit_up == D("104.5")
        # 9.5 × 1.1 = 10.45 → 10.45（10 以上檔位 0.05，有效）
        assert price_limits(D("9.5")).limit_up == D("10.45")

    def test_high_price(self):
        # 1005 × 1.1 = 1105.5 → 1105；1005 × 0.9 = 904.5 → 905
        assert price_limits(D(1005)) == PriceLimits(D(905), D(1105))

    def test_custom_limit_pct(self):
        lim = price_limits(D(100), ETF, limit_pct=D("0.20"))
        assert lim == PriceLimits(D(80), D(120))

    @pytest.mark.parametrize("bad", ["0", "1", "-0.1", "1.5"])
    def test_invalid_limit_pct(self, bad):
        with pytest.raises(ValueError):
            price_limits(D(100), limit_pct=D(bad))

    def test_invalid_reference(self):
        with pytest.raises(ValueError):
            price_limits(D(0))
        with pytest.raises(TypeError):
            price_limits(95.5)

    def test_less_than_one_tick_band(self):
        # 0.05 × 10% = 0.005 不足一檔 → 以一檔計
        assert price_limits(D("0.05")) == PriceLimits(D("0.04"), D("0.06"))
        # 已在最低價：跌停不得低於 0.01
        assert price_limits(D("0.01")) == PriceLimits(D("0.01"), D("0.02"))

    def test_less_than_one_tick_with_invalid_reference(self):
        # 0.051 × 1.1 = 0.0561 → 0.05 ≤ 基準價，且基準價本身不是有效檔位
        with pytest.raises(ValueError):
            price_limits(D("0.051"))

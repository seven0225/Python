from datetime import date
from decimal import Decimal as D

import pytest

from twmarket.cost import (
    COMMISSION_RATE,
    DAY_TRADE_TAX_END,
    DAY_TRADE_TAX_START,
    CostBreakdown,
    Rounding,
    TaxCategory,
    commission,
    futures_round_trip_tax,
    futures_tax,
    option_premium_tax,
    option_round_trip_tax,
    option_settlement_tax,
    securities_tax,
    securities_tax_rate,
    stock_trade_cost,
)

IN_PERIOD = date(2026, 10, 14)


class TestCommission:
    def test_full_rate(self):
        # 1,000,000 × 0.1425% = 1425
        assert commission(D(1_000_000)) == D("1425.000000")
        assert COMMISSION_RATE == D("0.001425")

    def test_discount(self):
        # 六折：1425 × 0.6 = 855
        assert commission(D(1_000_000), discount=D("0.6")) == D(855)

    def test_min_fee_applies(self):
        # 10,000 × 0.1425% = 14.25 < 20
        assert commission(D(10_000)) == D(20)

    def test_min_fee_boundary(self):
        # 20 / 0.001425 ≈ 14035.09；14,036 元恰好超過 20
        assert commission(D(14_035)) == D(20)
        assert commission(D(14_036)) == D("20.001300")

    def test_custom_min_fee_and_zero(self):
        assert commission(D(10_000), min_fee=D(1)) == D("14.250000")
        assert commission(D(10_000), min_fee=0) == D("14.250000")

    def test_zero_amount(self):
        assert commission(D(0)) == 0

    def test_rounding_modes(self):
        amt = D(123_456)  # × 0.001425 = 175.9248
        assert commission(amt, rounding=Rounding.NONE) == D("175.924800")
        assert commission(amt, rounding=Rounding.FLOOR) == D(175)
        assert commission(amt, rounding=Rounding.HALF_UP) == D(176)

    @pytest.mark.parametrize("disc", ["0", "-0.1", "1.01"])
    def test_bad_discount(self, disc):
        with pytest.raises(ValueError):
            commission(D(100_000), discount=D(disc))

    def test_negative_inputs(self):
        with pytest.raises(ValueError):
            commission(D(-1))
        with pytest.raises(ValueError):
            commission(D(1), min_fee=D(-1))

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            commission(100000.0)


class TestSecuritiesTaxRate:
    def test_general_and_etf(self):
        assert securities_tax_rate(TaxCategory.STOCK) == D("0.003")
        assert securities_tax_rate(TaxCategory.ETF) == D("0.001")

    def test_day_trade_period(self):
        cat = TaxCategory.STOCK_DAY_TRADE
        assert DAY_TRADE_TAX_START == date(2017, 4, 28)
        assert DAY_TRADE_TAX_END == date(2027, 12, 31)
        assert securities_tax_rate(cat, date(2017, 4, 27)) == D("0.003")
        assert securities_tax_rate(cat, date(2017, 4, 28)) == D("0.0015")
        assert securities_tax_rate(cat, IN_PERIOD) == D("0.0015")
        assert securities_tax_rate(cat, date(2027, 12, 31)) == D("0.0015")
        assert securities_tax_rate(cat, date(2028, 1, 1)) == D("0.003")

    def test_day_trade_default_date_is_today(self):
        rate = securities_tax_rate(TaxCategory.STOCK_DAY_TRADE)
        assert rate in (D("0.0015"), D("0.003"))


class TestSecuritiesTax:
    def test_amounts(self):
        assert securities_tax(D(1_000_000), TaxCategory.STOCK) == D(3000)
        assert securities_tax(D(1_000_000), TaxCategory.ETF) == D(1000)
        assert securities_tax(
            D(1_000_000), TaxCategory.STOCK_DAY_TRADE, IN_PERIOD
        ) == D(1500)

    def test_rounding(self):
        # 33,333 × 0.003 = 99.999
        assert securities_tax(D(33_333), TaxCategory.STOCK) == D("99.999")
        assert (
            securities_tax(D(33_333), TaxCategory.STOCK, rounding=Rounding.FLOOR) == 99
        )
        assert (
            securities_tax(D(33_333), TaxCategory.STOCK, rounding=Rounding.HALF_UP)
            == 100
        )

    def test_zero_and_negative(self):
        assert securities_tax(D(0), TaxCategory.STOCK) == 0
        with pytest.raises(ValueError):
            securities_tax(D(-1), TaxCategory.STOCK)


class TestStockTradeCost:
    def test_general_round_trip(self):
        # 買 100 元 × 1000 股，賣 110 元 × 1000 股，無折扣
        c = stock_trade_cost(D(100), D(110), 1000)
        assert c.buy_commission == D("142.500")
        assert c.sell_commission == D("156.750")
        assert c.sell_tax == D("330.000")
        assert c.buy == D("142.5")
        assert c.sell == D("486.75")
        assert c.round_trip == D("629.25")

    def test_day_trade_with_discount_and_floor(self):
        c = stock_trade_cost(
            D("95.5"),
            D("96"),
            2000,
            category=TaxCategory.STOCK_DAY_TRADE,
            discount=D("0.28"),
            tax_date=IN_PERIOD,
            rounding=Rounding.FLOOR,
        )
        # 191,000 × 0.001425 × 0.28 = 76.209 → 76
        assert c.buy_commission == 76
        # 192,000 × 0.001425 × 0.28 = 76.608 → 76
        assert c.sell_commission == 76
        # 192,000 × 0.0015 = 288
        assert c.sell_tax == 288
        assert c.round_trip == 440

    def test_etf_odd_lot_hits_min_fee(self):
        c = stock_trade_cost(D("150"), D("151"), 1, category=TaxCategory.ETF)
        assert c.buy_commission == 20 and c.sell_commission == 20
        assert c.sell_tax == D("0.151")

    @pytest.mark.parametrize("shares", [0, -1, True, 1.0])
    def test_bad_shares(self, shares):
        with pytest.raises(ValueError):
            stock_trade_cost(D(10), D(10), shares)


class TestFuturesTax:
    def test_tx_example(self):
        # 30,000 點 × 200 × 0.00002 = 120 元
        assert futures_tax(D(30_000), D(200)) == D(120)
        assert futures_tax(D(30_000), D(200), contracts=3) == D(360)

    def test_per_contract_rounding_half_up(self):
        # 股票期貨 112.5 × 2000 × 0.00002 = 4.5 → 5（每口先四捨五入）
        assert futures_tax(D("112.5"), D(2000)) == D(5)
        assert futures_tax(D("112.5"), D(2000), contracts=10) == D(50)
        # 小型股票期貨 1,000 × 100 × 0.00002 = 2
        assert futures_tax(D(1000), D(100)) == D(2)
        # 0.4 → 0
        assert futures_tax(D(200), D(100)) == D(0)

    def test_round_trip(self):
        rt = futures_round_trip_tax(D(30_000), D(30_500), D(200), 2)
        assert rt == CostBreakdown(buy=D(240), sell=D(244))
        assert rt.round_trip == D(484)

    @pytest.mark.parametrize("contracts", [0, -1, True])
    def test_bad_contracts(self, contracts):
        with pytest.raises(ValueError):
            futures_tax(D(100), D(200), contracts)

    def test_negative_price(self):
        with pytest.raises(ValueError):
            futures_tax(D(-1), D(200))


class TestOptionTax:
    def test_taifex_examples(self):
        # 期交所課稅實例：30.5 點 × 50 × 0.001 = 1.525 → 2 元
        assert option_premium_tax(D("30.5"), D(50)) == D(2)
        # 期交所 FAQ：權利金 200 點買進 1 口，稅 10 元
        assert option_premium_tax(D(200), D(50)) == D(10)

    def test_per_contract_rounding_then_multiply(self):
        # 1.525 → 2 元 × 3 口 = 6（而非 4.575 → 5）
        assert option_premium_tax(D("30.5"), D(50), 3) == D(6)

    def test_settlement_tax_examples(self):
        # 期交所 FAQ：結算價 6,200 × 50 × 0.00002 = 6.2 → 6
        assert option_settlement_tax(D(6200), D(50)) == D(6)
        # 課稅實例：7,808 → 7.808 → 8
        assert option_settlement_tax(D(7808), D(50)) == D(8)

    def test_round_trip(self):
        rt = option_round_trip_tax(D("30.5"), D(200), D(50), 1)
        assert (rt.buy, rt.sell, rt.round_trip) == (D(2), D(10), D(12))

    def test_tiny_premium_rounds_to_zero(self):
        # 0.1 點 × 50 × 0.001 = 0.005 → 0
        assert option_premium_tax(D("0.1"), D(50)) == 0

    def test_bad_inputs(self):
        with pytest.raises(ValueError):
            option_premium_tax(D(-1), D(50))
        with pytest.raises(ValueError):
            option_settlement_tax(D(100), D(-50))
        with pytest.raises(TypeError):
            option_premium_tax(30.5, D(50))

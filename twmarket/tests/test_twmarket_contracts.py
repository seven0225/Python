from datetime import date
from decimal import Decimal as D

import pytest

from twmarket.contracts import (
    ALL_CONTRACTS,
    MINI_STOCK_FUTURES,
    STOCK_FUTURES,
    TX,
    TXO,
    ExerciseStyle,
    Settlement,
    last_trading_day,
    third_wednesday,
)


class TestSpecs:
    def test_tx(self):
        assert TX.multiplier == D(200)
        assert TX.min_tick == D(1)
        assert TX.settlement is Settlement.CASH
        assert TX.exercise_style is None

    def test_txo(self):
        assert TXO.multiplier == D(50)
        assert TXO.exercise_style is ExerciseStyle.EUROPEAN
        assert TXO.settlement is Settlement.CASH

    def test_stock_futures(self):
        assert STOCK_FUTURES.multiplier == D(2000)
        assert MINI_STOCK_FUTURES.multiplier == D(100)
        assert STOCK_FUTURES.settlement is Settlement.CASH

    def test_all_have_official_source(self):
        for spec in ALL_CONTRACTS:
            assert spec.source_url.startswith("https://www.taifex.com.tw/")
            assert "第三個星期三" in spec.last_trading_day_rule

    def test_specs_are_immutable(self):
        with pytest.raises(AttributeError):
            TX.multiplier = D(50)  # type: ignore[misc]


class TestThirdWednesday:
    @pytest.mark.parametrize(
        "year, month, expected",
        [
            (2026, 10, date(2026, 10, 21)),
            (2024, 1, date(2024, 1, 17)),
            (2025, 1, date(2025, 1, 15)),  # 1 日為星期三 → 最早可能日 15 日
            (2024, 5, date(2024, 5, 15)),  # 1 日為星期三
            (2024, 2, date(2024, 2, 21)),  # 閏年 2 月
            (2023, 11, date(2023, 11, 15)),  # 1 日為星期三
            (2026, 4, date(2026, 4, 15)),  # 1 日為星期三
            (2025, 10, date(2025, 10, 15)),  # 1 日為星期三
            (2026, 7, date(2026, 7, 15)),
            (2025, 12, date(2025, 12, 17)),
            (2024, 8, date(2024, 8, 21)),  # 1 日為星期四 → 最晚可能日 21 日
        ],
    )
    def test_known_dates(self, year, month, expected):
        assert third_wednesday(year, month) == expected

    def test_always_wednesday_between_15_and_21(self):
        for year in (2000, 2015, 2026, 2030):
            for month in range(1, 13):
                d = third_wednesday(year, month)
                assert d.weekday() == 2
                assert 15 <= d.day <= 21

    @pytest.mark.parametrize("month", [0, 13, -1])
    def test_bad_month(self, month):
        with pytest.raises(ValueError):
            third_wednesday(2026, month)

    @pytest.mark.parametrize("year", [0, 10000])
    def test_bad_year(self, year):
        with pytest.raises(ValueError):
            third_wednesday(year, 1)

    @pytest.mark.parametrize("bad", ["2026", 2026.0, True])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError):
            third_wednesday(bad, 1)


class TestLastTradingDay:
    def test_equals_third_wednesday(self):
        assert last_trading_day(2026, 10) == date(2026, 10, 21)
        assert last_trading_day(2026, 12) == third_wednesday(2026, 12)

    def test_validation_propagates(self):
        with pytest.raises(ValueError):
            last_trading_day(2026, 13)

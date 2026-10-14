"""台股升降單位（檔位）與漲跌停價格。

規則依據（查閱日期皆為 2026-10-14）：

[R1] 臺灣證券交易所營業細則第 62 條（升降單位）、第 63 條（漲跌幅度）
     法規名稱：臺灣證券交易所股份有限公司營業細則（115.09.24 版）
     https://twse-regulation.twse.com.tw/m/LawContent.aspx?FID=FL007304
[R2] 證交所「調整股價升降單位－自 94 年 3 月 1 日實施－」說明文件
     https://www.twse.com.tw/downloads/zh/trading/introduce/introduce004.pdf
     股票升降單位：未滿 10 元 0.01；10～未滿 50 元 0.05；50～未滿 100 元 0.1；
     100～未滿 500 元 0.5；500～未滿 1000 元 1；1000 元以上 5。
[R3] 臺灣證券交易所股份有限公司受益憑證買賣辦法（114.09.30 版）
     https://twse-regulation.twse.com.tw/m/LawContent.aspx?FID=FL007114
     指數股票型基金（ETF）升降單位：未滿 50 元 0.01 元；50 元以上 0.05 元。
     證交所 ETF 專區亦同：
     https://www.twse.com.tw/zh/products/securities/etf/overview/rules.html
[R4] 證交所「集中市場交易制度介紹」：漲跌停價先以基準價 ×110%／×90% 計算，
     再調整到符合升降單位且漲跌幅不超過 10% 的價位。官方範例：
     基準價 40.60 元，計算出漲停價 44.66 元，調整為 44.65 元。
     https://www.twse.com.tw/zh/products/system/trading.html
[R5] 櫃買中心「放寬漲跌幅度專區」：漲跌幅度自 104 年（2015 年）6 月 1 日起
     由 7% 放寬為 10%（上市、上櫃同步）。
     https://www.tpex.org.tw/web/stock/trading/information/range.php?l=zh-tw

查證限制：上述官方網站在本開發環境無法直接開啟，內容係透過搜尋引擎
擷取之官方頁面摘要確認，條文原文仍待人工逐字核對（見 README TODO）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import Enum

from .decimal_math import DecimalLike, to_decimal


class SecurityType(Enum):
    """升降單位表的種類。"""

    STOCK = "stock"  # 股票（依 [R1] 第 62 條、[R2]）
    ETF = "etf"  # 指數股票型基金受益憑證（依 [R3]）


class Direction(Enum):
    """對齊檔位時的取整方向。"""

    DOWN = "down"
    UP = "up"


#: 漲跌幅由 7% 放寬為 10% 的生效日 [R5]。此日（含）以後適用 10%。
PRICE_LIMIT_10PCT_EFFECTIVE = date(2015, 6, 1)
PRICE_LIMIT_PCT_BEFORE = Decimal("0.07")  # [R5]
PRICE_LIMIT_PCT_CURRENT = Decimal("0.10")  # [R1] 第 63 條、[R5]

#: 現行股票升降單位表的生效日 [R2]。更早的表格未查證，不予支援。
STOCK_TICK_TABLE_EFFECTIVE = date(2005, 3, 1)

#: 最小價格：依 [R1] 第 63 條摘要「價格只能跌至最小升降單位（一分）為止」。
MIN_PRICE = Decimal("0.01")

# (下限含, 檔位)；價格 ≥ 下限即適用該檔位，由高往低比對。[R2]
_TickTable = tuple[tuple[Decimal, Decimal], ...]

_STOCK_TICKS: _TickTable = (
    (Decimal(1000), Decimal(5)),
    (Decimal(500), Decimal(1)),
    (Decimal(100), Decimal("0.5")),
    (Decimal(50), Decimal("0.1")),
    (Decimal(10), Decimal("0.05")),
    (Decimal(0), Decimal("0.01")),
)

# [R3]
# TODO(ETF 升降單位沿革)：查無 ETF 升降單位表的起始生效日與歷史版本，
#   目前對所有日期（含 2015-06-01 以前）一律套用現行表，待查證。
_ETF_TICKS: _TickTable = (
    (Decimal(50), Decimal("0.05")),
    (Decimal(0), Decimal("0.01")),
)

# TODO(千元以上股票檔位改為 1 元)：證交所董事會於 2026-08-25 通過修正營業細則
#   第 62 條，股價 1000 元以上升降單位由 5 元改為 1 元；依媒體報導尚待主管機關
#   核定，預計最快 2027 年 7 月實施（例：工商時報
#   https://www.ctee.com.tw/news/20260825701782-430201 ，查閱 2026-10-14）。
#   正式生效日公告後，需在 _STOCK_TICKS 加入依日期切換的版本。


@dataclass(frozen=True)
class PriceLimits:
    """漲跌停價格。"""

    limit_down: Decimal
    limit_up: Decimal


def _check_price(price: Decimal, name: str = "price") -> None:
    if price <= 0:
        raise ValueError(f"{name} 必須大於 0：{price}")


def tick_size(
    price: DecimalLike,
    security_type: SecurityType = SecurityType.STOCK,
    trade_date: date | None = None,
) -> Decimal:
    """回傳價格所在區間的升降單位。

    trade_date 為 None 時採現行規則；股票在 2005-03-01 以前的規則未查證，
    傳入更早日期會拋出 ValueError。

    >>> tick_size("95.5")
    Decimal('0.1')
    >>> tick_size("95.5", SecurityType.ETF)
    Decimal('0.05')
    """
    p = to_decimal(price, "price")
    _check_price(p)
    if security_type is SecurityType.STOCK:
        if trade_date is not None and trade_date < STOCK_TICK_TABLE_EFFECTIVE:
            # TODO(2005 年以前升降單位)：舊制升降單位表未查證，暫不支援。
            raise ValueError(
                f"{STOCK_TICK_TABLE_EFFECTIVE} 以前的股票升降單位未查證，不支援"
            )
        table = _STOCK_TICKS
    elif security_type is SecurityType.ETF:
        table = _ETF_TICKS
    else:  # pragma: no cover - Enum 已窮舉
        raise ValueError(f"不支援的種類：{security_type}")
    for lower, tick in table:
        if p >= lower:
            return tick
    raise AssertionError("unreachable")  # pragma: no cover


def round_to_tick(
    price: DecimalLike,
    direction: Direction,
    security_type: SecurityType = SecurityType.STOCK,
    trade_date: date | None = None,
) -> Decimal:
    """將價格對齊到有效檔位：DOWN 向下取、UP 向上取。

    以「原始價格所在區間」的檔位取整。各區間邊界（10、50、100、500、1000）
    皆為較細檔位的整數倍，因此結果必為該方向最近的有效價格；向上取整
    可能剛好落在上一區間的下限（例如 49.98 → 50.00），該價位同樣有效。

    >>> round_to_tick("105.05", Direction.DOWN)
    Decimal('105.0')
    >>> round_to_tick("85.95", Direction.UP)
    Decimal('86.0')
    """
    p = to_decimal(price, "price")
    tick = tick_size(p, security_type, trade_date)
    rounding = ROUND_FLOOR if direction is Direction.DOWN else ROUND_CEILING
    units = (p / tick).to_integral_value(rounding=rounding)
    return units * tick


def is_valid_price(
    price: DecimalLike,
    security_type: SecurityType = SecurityType.STOCK,
    trade_date: date | None = None,
) -> bool:
    """價格是否為有效檔位（升降單位的整數倍）。"""
    p = to_decimal(price, "price")
    if p <= 0:
        return False
    tick = tick_size(p, security_type, trade_date)
    return p % tick == 0


def price_limit_pct(trade_date: date | None = None) -> Decimal:
    """回傳漲跌幅比例：2015-06-01（含）以後 10%，之前 7%。[R5]

    trade_date 為 None 時採現行規則（10%）。
    """
    if trade_date is not None and trade_date < PRICE_LIMIT_10PCT_EFFECTIVE:
        return PRICE_LIMIT_PCT_BEFORE
    return PRICE_LIMIT_PCT_CURRENT


def price_limits(
    reference_price: DecimalLike,
    security_type: SecurityType = SecurityType.STOCK,
    trade_date: date | None = None,
    limit_pct: DecimalLike | None = None,
) -> PriceLimits:
    """計算漲跌停價格。

    漲停價 = 基準價 × (1 + 漲跌幅) 向下取到有效檔位；
    跌停價 = 基準價 × (1 − 漲跌幅) 向上取到有效檔位。[R1][R4]

    limit_pct 可覆寫漲跌幅（例如槓桿／反向 ETF）。
    TODO(ETF 漲跌幅特例)：槓桿／反向 ETF 的漲跌幅倍數、國外成分證券 ETF
      是否不設漲跌幅、初次上市普通股前 5 個交易日不設漲跌幅 [R1] 等特例，
      本函式未自動判斷，呼叫端需自行以 limit_pct 處理或不使用本函式。

    當漲跌幅度換算後不足一個升降單位時，依 [R1] 第 63 條摘要「按最小升降
    單位計算」，漲停價取基準價加一檔、跌停價取基準價減一檔（不低於 0.01）。
    TODO(未滿一檔之處理)：此特例僅依搜尋摘要實作，待以條文原文核對；
      且僅在基準價本身為有效檔位時才可明確定義。

    >>> price_limits("95.5")
    PriceLimits(limit_down=Decimal('86.0'), limit_up=Decimal('105.0'))
    """
    ref = to_decimal(reference_price, "reference_price")
    _check_price(ref, "reference_price")
    pct = (
        price_limit_pct(trade_date)
        if limit_pct is None
        else to_decimal(limit_pct, "limit_pct")
    )
    if not (0 < pct < 1):
        raise ValueError(f"limit_pct 必須介於 0 與 1 之間：{pct}")

    up = round_to_tick(ref * (1 + pct), Direction.DOWN, security_type, trade_date)
    down = round_to_tick(ref * (1 - pct), Direction.UP, security_type, trade_date)

    if up <= ref or down >= ref:
        if not is_valid_price(ref, security_type, trade_date):
            raise ValueError(
                f"漲跌幅度不足一檔且基準價 {ref} 非有效檔位，無法依規則計算"
            )
        if up <= ref:
            up = ref + tick_size(ref, security_type, trade_date)
        if down >= ref:
            # 基準價減一檔：以「略低於基準價」所在區間的檔位為準
            # （例如基準價 10.00 時，下一檔為 9.99），且不低於 0.01。
            if ref > MIN_PRICE:
                down = round_to_tick(
                    ref - MIN_PRICE / 2, Direction.DOWN, security_type, trade_date
                )
            down = max(down, MIN_PRICE)
    return PriceLimits(limit_down=down, limit_up=up)

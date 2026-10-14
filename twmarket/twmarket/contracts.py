"""期交所契約規格常數與最後交易日計算。

規則依據（查閱日期皆為 2026-10-14）：

[K1] 期交所「臺股期貨」契約規格：契約價值＝指數 × 新臺幣 200 元；最小升降
     單位 1 點（200 元）；最後交易日為交割月份第三個星期三；最後結算日同最後
     交易日；最後結算價以最後結算日證交所收盤前 30 分鐘內標的指數之簡單算術
     平均價訂之；現金交割。
     https://www.taifex.com.tw/cht/2/tX
[K2] 期交所「臺指選擇權」契約規格：每點新臺幣 50 元；歐式；月契約最後交易日
     為交割月份第三個星期三，到期日同最後交易日；最後結算價同 [K1] 之 30 分鐘
     簡單算術平均；現金交割，到期價內部位自動履約。
     https://www.taifex.com.tw/cht/2/tXO
[K3] 期交所「股票期貨／ETF 期貨」契約規格：標的為股票者每口 2,000 股，期交所
     得加掛 100 股之契約（小型股票期貨）；最後交易日為交割月份第三個星期三；
     最後結算價以最後結算日收盤前 60 分鐘內標的證券之算術平均價訂之；現金交割。
     https://www.taifex.com.tw/cht/2/sTF
     期交所「高價位股票期貨加掛小型契約」：
     https://www.taifex.com.tw/chinese/event/HSTF/event.asp

查證限制：上述官方網站在本開發環境無法直接開啟，內容係透過搜尋引擎
擷取之官方頁面摘要確認，契約規格原文仍待人工逐字核對（見 README TODO）。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class Settlement(Enum):
    """交割方式。"""

    CASH = "cash"  # 現金交割


class ExerciseStyle(Enum):
    """選擇權履約型態。"""

    EUROPEAN = "european"
    AMERICAN = "american"


@dataclass(frozen=True)
class ContractSpec:
    """契約規格。

    multiplier：每 1 單位價格（指數 1 點或股價 1 元）對應的新臺幣金額。
    min_tick：最小升降單位（價格單位）；None 表示依價格區間而定或未查證。
    """

    code: str
    name: str
    multiplier: Decimal
    min_tick: Decimal | None
    settlement: Settlement
    last_trading_day_rule: str
    final_settlement_price_rule: str
    exercise_style: ExerciseStyle | None
    source_url: str


TX = ContractSpec(
    code="TX",
    name="臺股期貨",
    multiplier=Decimal(200),
    min_tick=Decimal(1),
    settlement=Settlement.CASH,
    last_trading_day_rule="交割月份第三個星期三",
    final_settlement_price_rule=(
        "最後結算日證交所收盤前 30 分鐘內標的指數之簡單算術平均價"
    ),
    exercise_style=None,
    source_url="https://www.taifex.com.tw/cht/2/tX",
)

TXO = ContractSpec(
    code="TXO",
    name="臺指選擇權",
    multiplier=Decimal(50),
    # TODO(TXO 權利金升降單位)：權利金升降單位依權利金區間而定，未查證，不提供。
    min_tick=None,
    settlement=Settlement.CASH,
    last_trading_day_rule="交割月份第三個星期三（月契約；週契約另訂，未實作）",
    final_settlement_price_rule=(
        "到期日證交所收盤前 30 分鐘內標的指數之簡單算術平均價"
    ),
    exercise_style=ExerciseStyle.EUROPEAN,
    source_url="https://www.taifex.com.tw/cht/2/tXO",
)

STOCK_FUTURES = ContractSpec(
    code="STF",
    name="股票期貨（每口 2,000 股）",
    multiplier=Decimal(2000),
    # TODO(股票期貨升降單位)：依標的價格區間而定，未查證，不提供。
    min_tick=None,
    settlement=Settlement.CASH,
    last_trading_day_rule="交割月份第三個星期三",
    final_settlement_price_rule=("最後結算日收盤前 60 分鐘內標的證券之算術平均價"),
    exercise_style=None,
    source_url="https://www.taifex.com.tw/cht/2/sTF",
)

MINI_STOCK_FUTURES = ContractSpec(
    code="STF-MINI",
    name="小型股票期貨（每口 100 股）",
    multiplier=Decimal(100),
    min_tick=None,  # 同 STOCK_FUTURES 之 TODO
    settlement=Settlement.CASH,
    last_trading_day_rule="交割月份第三個星期三",
    final_settlement_price_rule=("最後結算日收盤前 60 分鐘內標的證券之算術平均價"),
    exercise_style=None,
    source_url="https://www.taifex.com.tw/cht/2/sTF",
)

ALL_CONTRACTS = (TX, TXO, STOCK_FUTURES, MINI_STOCK_FUTURES)

_WEDNESDAY = 2  # date.weekday()：星期一為 0


def third_wednesday(year: int, month: int) -> date:
    """指定年月的第三個星期三（純日曆計算）。

    >>> third_wednesday(2026, 10)
    datetime.date(2026, 10, 21)
    """
    for name, value in (("year", year), ("month", month)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} 必須是 int：{value!r}")
    if not 1 <= month <= 12:
        raise ValueError(f"month 必須介於 1 與 12：{month}")
    if not 1 <= year <= 9999:
        raise ValueError(f"year 超出範圍：{year}")
    first_weekday, _ = calendar.monthrange(year, month)
    offset = (_WEDNESDAY - first_weekday) % 7
    return date(year, month, 1 + offset + 14)


def last_trading_day(year: int, month: int) -> date:
    """TX／TXO（月契約）／股票期貨的最後交易日：交割月份第三個星期三。[K1–K3]

    TODO(最後交易日遇假日)：第三個星期三若為休市日（例如國定假日、颱風停市）
      時的順延規則尚未以期交所條文確認，本函式未處理，僅回傳日曆上的第三個
      星期三。合併到研究系統前需接上交易日曆並核對規則。
    """
    return third_wednesday(year, month)

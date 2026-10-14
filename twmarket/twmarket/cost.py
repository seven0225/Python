"""台灣市場交易成本：證券手續費、證券交易稅、期貨交易稅。

規則依據（查閱日期皆為 2026-10-14）：

[C1] 證交所法規分享知識庫，1990 年函釋：證券經紀商受託買賣股票及受益憑證
     之手續費按成交值千分之 1.425 計收，未滿 20 元者以 20 元計收。
     https://twse-regulation.twse.com.tw/TW/int/DAT01_print.aspx?FLCODE=FE064320
     註：其後改採「費率上限制」，由券商在上限內自訂費率（證交所 60 週年特刊
     https://www.twse.com.tw/staticFiles/product/publication/twse60/html/293/ ），
     因此折扣與最低收費皆設為可調參數；預設最低 20 元僅反映上述函釋。
[C2] 證券交易稅條例第 2 條：向出賣人按每次成交價格課徵；
     第 1 款 股票 千分之三；第 2 款 公司債及其他經政府核准之有價證券 千分之一。
     https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=G0340078&flno=2
[C3] 財政部稅務入口網「買賣受益憑證的證券交易稅稅率是多少？(6208)」：
     受益憑證（含 ETF）千分之一。
     https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-q-and-a/national/securities-transaction-tax/filing/KJZD0QV
[C4] 證券交易稅條例第 2 條之 2（現股當日沖銷）：出賣股票稅率千分之 1.5，
     適用期間 2017-04-28 至 2027-12-31（2024-12-31 立法院三讀延長）。
     財政部賦稅署公告：
     https://www.dot.gov.tw/singlehtml/ch26?cntId=fde9d7d1546d4df8a4db96bf23e2f57c
     財政部稅務入口網「買賣股票的證券交易稅稅率是多少？(6206)」：
     https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-q-and-a/national/securities-transaction-tax/filing/mM8n39b
[C5] 期貨交易稅條例第 2 條（法定稅率區間；實際徵收率由財政部報行政院核定）
     https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=G0340079&flno=2
[C6] 財政部稅務入口網「期貨交易稅稅率及計算方式」：股價類期貨按每次交易之
     契約金額課徵十萬分之 2；選擇權按每次交易之權利金金額課徵千分之 1；
     選擇權到期以現金結算者，依對應期貨稅率（股價類為十萬分之 2）課徵。
     https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-saving-manual/national/future-transaction-tax/12B2ODn
     期交所費率表（TXO 0.001；股價類期貨 0.00002）：
     https://www.taifex.com.tw/cht/4/feeSchedules
[C7] 期交所「選擇權類課稅實例」：每口稅額先四捨五入至元，再乘以口數。
     例：TXO 權利金 30.5 點 → 每口 1,525 元 × 0.001 = 1.525 → 2 元。
     https://www.taifex.com.tw/chinese/4/%E9%81%B8%E6%93%87%E6%AC%8A%E9%A1%9E%E8%AA%B2%E7%A8%85%E5%AF%A6%E4%BE%8B.doc

查證限制：上述官方網站在本開發環境無法直接開啟，內容係透過搜尋引擎
擷取之官方頁面摘要確認，條文原文仍待人工逐字核對（見 README TODO）。

TODO(證券手續費、證交稅之元以下處理)：未查到官方明文規定手續費與證交稅
  計算至元的取整方式（無條件捨去或四捨五入）。本模組預設不取整（回傳精確
  Decimal），可用 rounding 參數指定，實際以券商對帳單為準。
TODO(債券 ETF 證交稅)：債券 ETF 暫停徵收證交稅的法源條號、期限與範圍尚未
  查證，本模組未實作，ETF 一律以千分之一計算。
TODO(期貨手續費)：期貨商向交易人收取之手續費由雙方議定 [C6 費率表]，
  本模組不計算期貨／選擇權手續費，只計算期貨交易稅。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import Enum

from .decimal_math import DecimalLike, to_decimal

# --- 證券手續費 [C1] ---------------------------------------------------------
COMMISSION_RATE = Decimal("0.001425")
DEFAULT_MIN_COMMISSION = Decimal(20)

# --- 證券交易稅 [C2][C3][C4] ------------------------------------------------
STOCK_TAX_RATE = Decimal("0.003")  # [C2] 第 1 款
ETF_TAX_RATE = Decimal("0.001")  # [C2] 第 2 款、[C3]
DAY_TRADE_TAX_RATE = Decimal("0.0015")  # [C4]
DAY_TRADE_TAX_START = date(2017, 4, 28)  # [C4]
DAY_TRADE_TAX_END = date(2027, 12, 31)  # [C4]，含當日
# TODO(當沖減稅期間的判斷日)：財政部說明證交稅於「交割日」代徵；條文期間
#   是以成交日或交割日判斷尚未逐字核對。本模組以呼叫端傳入的 tax_date 判斷，
#   建議傳入交割日。

# --- 期貨交易稅 [C5][C6][C7] ------------------------------------------------
EQUITY_FUTURES_TAX_RATE = Decimal("0.00002")  # 股價類期貨（含臺指期、股票期貨）
OPTION_PREMIUM_TAX_RATE = Decimal("0.001")  # 選擇權權利金（含臺指選擇權）
OPTION_SETTLEMENT_TAX_RATE = EQUITY_FUTURES_TAX_RATE  # 股價類選擇權到期結算


class Rounding(Enum):
    """金額取整方式（至新臺幣元）。"""

    NONE = "none"  # 不取整
    FLOOR = "floor"  # 無條件捨去
    HALF_UP = "half_up"  # 四捨五入


class TaxCategory(Enum):
    """證券交易稅類別。"""

    STOCK = "stock"  # 一般股票 [C2]
    STOCK_DAY_TRADE = "stock_day_trade"  # 現股當沖之賣出 [C4]
    ETF = "etf"  # ETF 等受益憑證 [C3]


@dataclass(frozen=True)
class CostBreakdown:
    """單位：新臺幣元。buy＝買進端成本，sell＝賣出端成本。"""

    buy: Decimal
    sell: Decimal

    @property
    def round_trip(self) -> Decimal:
        """來回合計。"""
        return self.buy + self.sell


@dataclass(frozen=True)
class StockTradeCost:
    """現貨一買一賣的成本明細。"""

    buy_commission: Decimal
    sell_commission: Decimal
    sell_tax: Decimal

    @property
    def buy(self) -> Decimal:
        return self.buy_commission

    @property
    def sell(self) -> Decimal:
        return self.sell_commission + self.sell_tax

    @property
    def round_trip(self) -> Decimal:
        return self.buy + self.sell


def _round(amount: Decimal, rounding: Rounding) -> Decimal:
    if rounding is Rounding.NONE:
        return amount
    mode = ROUND_FLOOR if rounding is Rounding.FLOOR else ROUND_HALF_UP
    return amount.quantize(Decimal(1), rounding=mode)


def _non_negative(value: DecimalLike, name: str) -> Decimal:
    d = to_decimal(value, name)
    if d < 0:
        raise ValueError(f"{name} 不可為負：{d}")
    return d


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} 必須是正整數：{value!r}")
    return value


def commission(
    amount: DecimalLike,
    discount: DecimalLike = 1,
    min_fee: DecimalLike = DEFAULT_MIN_COMMISSION,
    rounding: Rounding = Rounding.NONE,
) -> Decimal:
    """證券手續費 = max(成交金額 × 0.1425% × 折扣, 最低收費)。[C1]

    discount：折扣倍數，例如 Decimal("0.6") 代表六折；須在 (0, 1]。
    min_fee：最低收費（券商自訂，預設 20 元，傳 0 代表無下限）。
    成交金額為 0 時回傳 0（沒有成交即無手續費）。
    取整先於最低收費比較。
    """
    amt = _non_negative(amount, "amount")
    disc = to_decimal(discount, "discount")
    if not (0 < disc <= 1):
        raise ValueError(f"discount 必須介於 0（不含）與 1（含）之間：{disc}")
    floor_fee = _non_negative(min_fee, "min_fee")
    if amt == 0:
        return Decimal(0)
    fee = _round(amt * COMMISSION_RATE * disc, rounding)
    return max(fee, floor_fee)


def securities_tax_rate(category: TaxCategory, tax_date: date | None = None) -> Decimal:
    """證券交易稅率。

    現股當沖在 [2017-04-28, 2027-12-31] 期間外，回到第 2 條第 1 款一般
    股票稅率千分之三 [C2][C4]。tax_date 為 None 時採 date.today()。
    """
    if category is TaxCategory.STOCK:
        return STOCK_TAX_RATE
    if category is TaxCategory.ETF:
        return ETF_TAX_RATE
    if category is TaxCategory.STOCK_DAY_TRADE:
        d = date.today() if tax_date is None else tax_date
        if DAY_TRADE_TAX_START <= d <= DAY_TRADE_TAX_END:
            return DAY_TRADE_TAX_RATE
        return STOCK_TAX_RATE
    raise ValueError(f"不支援的類別：{category}")  # pragma: no cover


def securities_tax(
    amount: DecimalLike,
    category: TaxCategory,
    tax_date: date | None = None,
    rounding: Rounding = Rounding.NONE,
) -> Decimal:
    """證券交易稅（僅賣出方負擔）= 成交金額 × 稅率。[C2]"""
    amt = _non_negative(amount, "amount")
    return _round(amt * securities_tax_rate(category, tax_date), rounding)


def stock_trade_cost(
    buy_price: DecimalLike,
    sell_price: DecimalLike,
    shares: int,
    category: TaxCategory = TaxCategory.STOCK,
    discount: DecimalLike = 1,
    min_fee: DecimalLike = DEFAULT_MIN_COMMISSION,
    tax_date: date | None = None,
    rounding: Rounding = Rounding.NONE,
) -> StockTradeCost:
    """現貨（股票／ETF）一買一賣的手續費與證交稅。

    買進：手續費；賣出：手續費 + 證交稅。證交稅只向出賣人課徵 [C2]。
    """
    n = _positive_int(shares, "shares")
    buy_amt = _non_negative(buy_price, "buy_price") * n
    sell_amt = _non_negative(sell_price, "sell_price") * n
    return StockTradeCost(
        buy_commission=commission(buy_amt, discount, min_fee, rounding),
        sell_commission=commission(sell_amt, discount, min_fee, rounding),
        sell_tax=securities_tax(sell_amt, category, tax_date, rounding),
    )


def _per_contract_tax(
    price: Decimal, multiplier: Decimal, rate: Decimal, contracts: int
) -> Decimal:
    """每口稅額四捨五入至元後乘以口數。[C7]"""
    per_contract = (price * multiplier * rate).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return per_contract * contracts


def futures_tax(
    price: DecimalLike, multiplier: DecimalLike, contracts: int = 1
) -> Decimal:
    """股價類期貨單邊交易稅 = 契約金額 × 十萬分之 2（每口四捨五入至元）。

    契約金額 = 成交價 × 契約乘數（臺指期每點 200 元；股票期貨為每口股數）。
    買賣雙方各自課徵 [C5][C6]。
    """
    p = _non_negative(price, "price")
    m = _non_negative(multiplier, "multiplier")
    n = _positive_int(contracts, "contracts")
    return _per_contract_tax(p, m, EQUITY_FUTURES_TAX_RATE, n)


def option_premium_tax(
    premium: DecimalLike, multiplier: DecimalLike, contracts: int = 1
) -> Decimal:
    """選擇權單邊交易稅 = 權利金金額 × 千分之 1（每口四捨五入至元）。[C6][C7]"""
    p = _non_negative(premium, "premium")
    m = _non_negative(multiplier, "multiplier")
    n = _positive_int(contracts, "contracts")
    return _per_contract_tax(p, m, OPTION_PREMIUM_TAX_RATE, n)


def option_settlement_tax(
    settlement_price: DecimalLike, multiplier: DecimalLike, contracts: int = 1
) -> Decimal:
    """股價類選擇權到期現金結算之交易稅 = 最後結算價 × 乘數 × 十萬分之 2。

    依 [C6]（到期結算依對應期貨稅率）與 [C7]（每口四捨五入至元）。
    TODO(到期結算課稅對象)：是否僅對履約（價內）部位課徵，待核對條文。
    """
    p = _non_negative(settlement_price, "settlement_price")
    m = _non_negative(multiplier, "multiplier")
    n = _positive_int(contracts, "contracts")
    return _per_contract_tax(p, m, OPTION_SETTLEMENT_TAX_RATE, n)


def futures_round_trip_tax(
    open_price: DecimalLike,
    close_price: DecimalLike,
    multiplier: DecimalLike,
    contracts: int = 1,
) -> CostBreakdown:
    """股價類期貨一買一賣的交易稅：buy＝買進成交價、sell＝賣出成交價。"""
    return CostBreakdown(
        buy=futures_tax(open_price, multiplier, contracts),
        sell=futures_tax(close_price, multiplier, contracts),
    )


def option_round_trip_tax(
    buy_premium: DecimalLike,
    sell_premium: DecimalLike,
    multiplier: DecimalLike,
    contracts: int = 1,
) -> CostBreakdown:
    """選擇權一買一賣（平倉，不持有至到期）的交易稅。"""
    return CostBreakdown(
        buy=option_premium_tax(buy_premium, multiplier, contracts),
        sell=option_premium_tax(sell_premium, multiplier, contracts),
    )

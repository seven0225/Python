"""以 Decimal 實作的數學工具（標準函式庫 math 只支援 float）。

所有價格計算一律使用 Decimal，避免二進位浮點誤差。本模組提供：
輸入轉換（拒收 float）、常態分配 PDF／CDF。指數、對數、開根號
直接使用 Decimal 內建的 exp()、ln()、sqrt()。
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Union

#: 內部計算精度（有效位數）。選擇權模型在此精度下計算，回傳前不另行捨入。
PRECISION = 50

# 圓周率前 60 位（數學常數，非市場規則）。
PI = Decimal("3.14159265358979323846264338327950288419716939937510582097494")

ZERO = Decimal(0)
ONE = Decimal(1)
HALF = Decimal("0.5")

DecimalLike = Union[Decimal, int, str]

# |x| 超過此值時，Φ(x) 與 0 或 1 的差距小於 1e-50（Φ(-15) ≈ 3.7e-51），
# 已低於 PRECISION 可表示的範圍，直接回傳 0 或 1。
_CDF_CUTOFF = Decimal(15)


def to_decimal(value: DecimalLike, name: str = "value") -> Decimal:
    """將輸入轉為 Decimal；拒收 float 與 bool，避免浮點誤差混入。

    >>> to_decimal("95.5")
    Decimal('95.5')
    >>> to_decimal(3)
    Decimal('3')
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(
            f"{name} 必須是 Decimal、int 或 str，不接受 {type(value).__name__}"
            "（請改用 Decimal('…') 以避免浮點誤差）"
        )
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except ArithmeticError as exc:  # decimal.InvalidOperation
            raise ValueError(f"{name} 無法轉成 Decimal：{value!r}") from exc
    else:
        raise TypeError(f"{name} 型別不支援：{type(value).__name__}")
    if not result.is_finite():
        raise ValueError(f"{name} 必須是有限數值：{value!r}")
    return result


def norm_pdf(x: Decimal) -> Decimal:
    """標準常態機率密度 φ(x) = exp(-x²/2) / √(2π)。"""
    with localcontext() as ctx:
        ctx.prec = PRECISION + 10
        result = (-(x * x) / 2).exp() / (2 * PI).sqrt()
        ctx.prec = PRECISION
        return +result


def norm_cdf(x: Decimal) -> Decimal:
    """標準常態累積分配 Φ(x)。

    使用 Marsaglia (2004) "Evaluating the Normal Distribution",
    Journal of Statistical Software 11(4) 的級數：
    Φ(x) = 1/2 + φ(x)·(x + x³/3 + x⁵/(3·5) + …)，x ≥ 0 時各項皆為正，
    無相消誤差；x < 0 時以 Φ(x) = 1 − Φ(−x) 計算。
    """
    if x > _CDF_CUTOFF:
        return ONE
    if x < -_CDF_CUTOFF:
        return ZERO
    with localcontext() as ctx:
        ctx.prec = PRECISION
        if x < 0:
            return ONE - norm_cdf(-x)
        ctx.prec = PRECISION + 10
        epsilon = Decimal(10) ** -(PRECISION + 8)
        term = x
        total = x
        x2 = x * x
        n = 1
        while term > epsilon:
            n += 2
            term = term * x2 / n
            total += term
        result = HALF + norm_pdf(x) * total
        ctx.prec = PRECISION
        return +result

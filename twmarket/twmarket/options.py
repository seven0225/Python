"""選擇權定價：Black-76、CRR 二項樹、隱含波動率（Brent 法）、Greeks。

全部以 Decimal 計算（精度見 decimal_math.PRECISION）。

參考文獻（模型為學術公式，非交易所規則）：
- Black, F. (1976). "The pricing of commodity contracts."
  Journal of Financial Economics 3, 167–179.
- Cox, J. C., Ross, S. A., Rubinstein, M. (1979). "Option pricing:
  A simplified approach." Journal of Financial Economics 7, 229–263.
- Brent, R. P. (1973). Algorithms for Minimization without Derivatives,
  Chapter 4（求根演算法）。
- Hull, J. C. Options, Futures, and Other Derivatives（Black 模型、二項樹、
  Greeks 章節；章節編號依版次不同）。

單位慣例：
- T：到期時間（年）；r：連續複利無風險利率；sigma：年化波動率（0.25 = 25%）。
- vega：波動率變動 1.00（即 100 個百分點）的價格變動；每 1% 請自行除以 100。
- theta：每「年」的價格變動（∂V/∂t，時間經過為正方向，通常為負值）；
  每日請自行除以 365 或交易日數。
- rho：利率變動 1.00 的價格變動。Black-76 下期貨價格 F 視為與 r 無關，
  故 rho = −T·V。
- delta、gamma 皆對期貨價格 F 微分。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from .decimal_math import (
    PRECISION,
    DecimalLike,
    norm_cdf,
    norm_pdf,
    to_decimal,
)

ZERO = Decimal(0)
ONE = Decimal(1)


class OptionType(Enum):
    CALL = "call"
    PUT = "put"


class NoImpliedVolatilityError(ValueError):
    """目標價格在給定區間內無對應的隱含波動率。"""


@dataclass(frozen=True)
class Greeks:
    delta: Decimal
    gamma: Decimal
    vega: Decimal
    theta: Decimal
    rho: Decimal


def _validate(
    forward: DecimalLike,
    strike: DecimalLike,
    t: DecimalLike,
    r: DecimalLike,
    sigma: DecimalLike,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    f = to_decimal(forward, "forward")
    k = to_decimal(strike, "strike")
    tt = to_decimal(t, "t")
    rr = to_decimal(r, "r")
    s = to_decimal(sigma, "sigma")
    if f <= 0:
        raise ValueError(f"forward 必須大於 0：{f}")
    if k <= 0:
        raise ValueError(f"strike 必須大於 0：{k}")
    if tt < 0:
        raise ValueError(f"t 不可為負：{tt}")
    if s < 0:
        raise ValueError(f"sigma 不可為負：{s}")
    return f, k, tt, rr, s


def _black76(
    f: Decimal, k: Decimal, t: Decimal, r: Decimal, s: Decimal, kind: OptionType
) -> Decimal:
    """內部版本：參數已驗證、已在高精度 context 中。"""
    df = (-r * t).exp()
    if t == 0 or s == 0:
        intrinsic = f - k if kind is OptionType.CALL else k - f
        return df * max(intrinsic, ZERO)
    vol_sqrt_t = s * t.sqrt()
    d1 = ((f / k).ln() + s * s * t / 2) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    if kind is OptionType.CALL:
        return df * (f * norm_cdf(d1) - k * norm_cdf(d2))
    return df * (k * norm_cdf(-d2) - f * norm_cdf(-d1))


def black76_price(
    forward: DecimalLike,
    strike: DecimalLike,
    t: DecimalLike,
    r: DecimalLike,
    sigma: DecimalLike,
    option_type: OptionType,
) -> Decimal:
    """Black-76 歐式期貨選擇權價格。

    c = e^{−rT}[F·N(d1) − K·N(d2)]，p = e^{−rT}[K·N(−d2) − F·N(−d1)]，
    d1 = [ln(F/K) + σ²T/2] / (σ√T)，d2 = d1 − σ√T。
    T = 0 或 σ = 0 時回傳折現後的內含價值。
    """
    f, k, tt, rr, s = _validate(forward, strike, t, r, sigma)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return _black76(f, k, tt, rr, s, option_type)


def black76_greeks(
    forward: DecimalLike,
    strike: DecimalLike,
    t: DecimalLike,
    r: DecimalLike,
    sigma: DecimalLike,
    option_type: OptionType,
) -> Greeks:
    """Black-76 Greeks（單位見模組說明）。T 或 σ 為 0 時未定義，拋出 ValueError。

    delta：買權 e^{−rT}N(d1)；賣權 −e^{−rT}N(−d1)
    gamma：e^{−rT}φ(d1) / (Fσ√T)
    vega ：e^{−rT}F·φ(d1)·√T
    theta：r·V − e^{−rT}F·φ(d1)·σ / (2√T)
    rho  ：−T·V
    """
    f, k, tt, rr, s = _validate(forward, strike, t, r, sigma)
    if tt == 0 or s == 0:
        raise ValueError("t 與 sigma 必須大於 0 才能計算 Greeks")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        df = (-rr * tt).exp()
        sqrt_t = tt.sqrt()
        vol_sqrt_t = s * sqrt_t
        d1 = ((f / k).ln() + s * s * tt / 2) / vol_sqrt_t
        pdf_d1 = norm_pdf(d1)
        value = _black76(f, k, tt, rr, s, option_type)
        if option_type is OptionType.CALL:
            delta = df * norm_cdf(d1)
        else:
            delta = -df * norm_cdf(-d1)
        gamma = df * pdf_d1 / (f * vol_sqrt_t)
        vega = df * f * pdf_d1 * sqrt_t
        theta = rr * value - df * f * pdf_d1 * s / (2 * sqrt_t)
        rho = -tt * value
        return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def crr_price(
    spot: DecimalLike,
    strike: DecimalLike,
    t: DecimalLike,
    r: DecimalLike,
    sigma: DecimalLike,
    option_type: OptionType,
    steps: int,
    american: bool = True,
    carry: DecimalLike = 0,
) -> Decimal:
    """Cox-Ross-Rubinstein 二項樹。

    carry 為持有成本 b：期貨選擇權 b = 0（預設）；無股利股票 b = r；
    連續股利率 q 的股票 b = r − q。
    u = e^{σ√Δt}，d = 1/u，p = (e^{bΔt} − d)/(u − d)，每步以 e^{−rΔt} 折現。
    american=True 時每個節點比較提前履約價值。
    若 p 不在 (0, 1)（Δt 過大或參數極端）則拋出 ValueError。
    """
    s0, k, tt, rr, s = _validate(spot, strike, t, r, sigma)
    b = to_decimal(carry, "carry")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise ValueError(f"steps 必須是正整數：{steps!r}")
    if tt == 0 or s == 0:
        raise ValueError("t 與 sigma 必須大於 0")
    is_call = option_type is OptionType.CALL
    with localcontext() as ctx:
        ctx.prec = PRECISION
        dt = tt / steps
        u = (s * dt.sqrt()).exp()
        d = ONE / u
        growth = (b * dt).exp()
        p = (growth - d) / (u - d)
        if not (0 < p < 1):
            raise ValueError(f"風險中立機率 p={p} 不在 (0,1)，請增加 steps")
        q = ONE - p
        disc = (-rr * dt).exp()
        pu = disc * p
        pd = disc * q

        def payoff(price: Decimal) -> Decimal:
            v = price - k if is_call else k - price
            return v if v > 0 else ZERO

        # 到期節點：j 為上漲次數，價格 = S·u^j·d^(N−j) = S·u^(2j−N)
        u2 = u * u
        price = s0 * d**steps
        values = []
        for _ in range(steps + 1):
            values.append(payoff(price))
            price *= u2
        for i in range(steps - 1, -1, -1):
            price = s0 * d**i
            for j in range(i + 1):
                cont = pd * values[j] + pu * values[j + 1]
                if american:
                    ex = payoff(price)
                    if ex > cont:
                        cont = ex
                values[j] = cont
                price *= u2
        return +values[0]


def implied_volatility(
    price: DecimalLike,
    forward: DecimalLike,
    strike: DecimalLike,
    t: DecimalLike,
    r: DecimalLike,
    option_type: OptionType,
    lower: DecimalLike = "0.0001",
    upper: DecimalLike = "5",
    tol: DecimalLike = "1e-12",
    max_iter: int = 200,
) -> Decimal:
    """以 Brent 法由 Black-76 價格反推隱含波動率。

    無解時拋出 NoImpliedVolatilityError：
    - 價格 ≤ 折現內含價值（σ→0 的下界）或 ≥ 無套利上界
      （買權 e^{−rT}F、賣權 e^{−rT}K）；
    - 價格在無套利區間內，但不在 [lower, upper] 對應的價格區間內；
    - t = 0（價格與 σ 無關）。
    tol 為 σ 的絕對容許誤差。
    """
    target = to_decimal(price, "price")
    f, k, tt, rr, _ = _validate(forward, strike, t, r, 0)
    lo = to_decimal(lower, "lower")
    hi = to_decimal(upper, "upper")
    eps = to_decimal(tol, "tol")
    if not (0 < lo < hi):
        raise ValueError(f"需 0 < lower < upper：{lo}, {hi}")
    if eps <= 0:
        raise ValueError(f"tol 必須大於 0：{eps}")
    if tt == 0:
        raise NoImpliedVolatilityError("t = 0 時價格與波動率無關，無法反推")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        df = (-rr * tt).exp()
        if option_type is OptionType.CALL:
            floor_value = df * max(f - k, ZERO)
            cap_value = df * f
        else:
            floor_value = df * max(k - f, ZERO)
            cap_value = df * k
        if not (floor_value < target < cap_value):
            raise NoImpliedVolatilityError(
                f"價格 {target} 不在無套利區間 ({floor_value}, {cap_value}) 內"
            )

        def objective(vol: Decimal) -> Decimal:
            return _black76(f, k, tt, rr, vol, option_type) - target

        return _brent(objective, lo, hi, eps, max_iter)


def _brent(
    func: Callable[[Decimal], Decimal],
    a: Decimal,
    b: Decimal,
    tol: Decimal,
    max_iter: int,
) -> Decimal:
    """Brent (1973) 求根法：結合二分法、割線法與反二次插值。

    實作依 Brent 原著 zero 演算法的標準形式（亦見 Press et al.,
    Numerical Recipes, §9.3）。呼叫端須已設定 Decimal 精度。
    """
    fa = func(a)
    fb = func(b)
    if fa == 0:
        return a
    if fb == 0:
        return b
    if (fa > 0) == (fb > 0):
        raise NoImpliedVolatilityError(
            f"區間 [{a}, {b}] 兩端同號，目標價格不在此波動率區間內"
        )
    machine_eps = Decimal(10) ** -(PRECISION - 2)
    c, fc = b, fb
    d = e = b - a
    for _ in range(max_iter):
        if (fb > 0) == (fc > 0):
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, b, c = b, c, b
            fa, fb, fc = fb, fc, fb
        tol1 = 2 * machine_eps * abs(b) + tol / 2
        xm = (c - b) / 2
        if abs(xm) <= tol1 or fb == 0:
            return b
        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                p = 2 * xm * s
                q = 1 - s
            else:
                q = fa / fc
                rr = fb / fc
                p = s * (2 * xm * q * (q - rr) - (b - a) * (rr - 1))
                q = (q - 1) * (rr - 1) * (s - 1)
            if p > 0:
                q = -q
            p = abs(p)
            min1 = 3 * xm * q - abs(tol1 * q)
            min2 = abs(e * q)
            if 2 * p < min(min1, min2):
                e = d
                d = p / q
            else:
                d = xm
                e = d
        else:
            d = xm
            e = d
        a, fa = b, fb
        if abs(d) > tol1:
            b += d
        else:
            b += tol1 if xm > 0 else -tol1
        fb = func(b)
    raise NoImpliedVolatilityError(f"Brent 法在 {max_iter} 次迭代內未收斂")

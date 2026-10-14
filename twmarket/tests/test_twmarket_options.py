"""選擇權模型測試。

教科書數值取自 Hull, Options, Futures, and Other Derivatives（章節編號依
版次不同）；書中數值多四捨五入到 2～3 位小數，故容許誤差設為
「書中最後一位的半個單位」：2 位小數 → 0.005，3 位小數 → 0.0005，
1 位小數（vega 12.1）→ 0.05。
"""

from contextlib import contextmanager
from decimal import Decimal as D
from decimal import localcontext

import pytest

from twmarket.options import (
    Greeks,
    NoImpliedVolatilityError,
    OptionType,
    black76_greeks,
    black76_price,
    crr_price,
    implied_volatility,
)

CALL = OptionType.CALL
PUT = OptionType.PUT


@contextmanager
def hp():
    """測試端以與套件相同的 50 位精度計算預期值（預設 context 只有 28 位）。"""
    with localcontext() as ctx:
        ctx.prec = 50
        yield


def close(a, b, tol):
    return abs(D(a) - D(b)) <= D(tol)


def forward_from_spot(s, r, t):
    """無股利股票：F = S·e^{rT}，使 Black-76 等價於 Black-Scholes。"""
    return D(s) * (D(r) * D(t)).exp()


class TestBlack76:
    def test_hull_futures_put(self):
        # Hull：F=20, K=20, r=9%, T=4 個月, σ=25% → 歐式期貨賣權 1.12
        p = black76_price(D(20), D(20), D(4) / 12, D("0.09"), D("0.25"), PUT)
        assert close(p, "1.12", "0.005")

    def test_hull_black_scholes_equivalence(self):
        # Hull：S=42, K=40, r=10%, σ=20%, T=0.5 → c=4.76, p=0.81
        f = forward_from_spot(42, "0.1", "0.5")
        c = black76_price(f, D(40), D("0.5"), D("0.1"), D("0.2"), CALL)
        p = black76_price(f, D(40), D("0.5"), D("0.1"), D("0.2"), PUT)
        assert close(c, "4.76", "0.005")
        assert close(p, "0.81", "0.005")

    @pytest.mark.parametrize("f, k", [(20, 20), (100, 80), (80, 100), (30000, 29500)])
    def test_put_call_parity(self, f, k):
        t, r, s = D("0.75"), D("0.03"), D("0.3")
        c = black76_price(D(f), D(k), t, r, s, CALL)
        p = black76_price(D(f), D(k), t, r, s, PUT)
        with hp():
            assert abs((c - p) - (-r * t).exp() * (D(f) - D(k))) < D("1e-40")

    def test_zero_time_is_intrinsic(self):
        assert black76_price(D(110), D(100), D(0), D("0.05"), D("0.2"), CALL) == 10
        assert black76_price(D(110), D(100), D(0), D("0.05"), D("0.2"), PUT) == 0

    def test_zero_vol_is_discounted_intrinsic(self):
        c = black76_price(D(110), D(100), D(1), D("0.05"), D(0), CALL)
        with hp():
            assert abs(c - 10 * D("-0.05").exp()) < D("1e-45")
        assert black76_price(D(110), D(100), D(1), D("0.05"), D(0), PUT) == 0

    def test_bounds(self):
        t, r = D(1), D("0.02")
        df = (-r * t).exp()
        c = black76_price(D(100), D(100), t, r, D(3), CALL)
        assert 0 < c < df * 100

    def test_monotone_in_vol(self):
        prices = [
            black76_price(D(100), D(105), D("0.5"), D("0.01"), D(v), CALL)
            for v in ("0.1", "0.2", "0.4", "0.8")
        ]
        assert prices == sorted(prices)

    @pytest.mark.parametrize(
        "args",
        [
            (0, 100, 1, "0.01", "0.2"),
            (100, 0, 1, "0.01", "0.2"),
            (100, 100, -1, "0.01", "0.2"),
            (100, 100, 1, "0.01", "-0.2"),
        ],
    )
    def test_invalid_inputs(self, args):
        with pytest.raises(ValueError):
            black76_price(*(D(a) for a in args), CALL)

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            black76_price(100.0, D(100), D(1), D(0), D("0.2"), CALL)


class TestGreeks:
    S, K, T, R, SIG = D(49), D(50), D("0.3846"), D("0.05"), D("0.2")

    def test_hull_greeks_via_conversion(self):
        """Hull：S=49, K=50, r=5%, σ=20%, T=0.3846 的 Black-Scholes 買權。

        書中數值：價格 2.40、delta 0.522、gamma 0.066、vega 12.1、
        theta −4.31（每年）、rho 8.91。
        以 F = S·e^{rT} 換算：Δ_S = Δ_F·e^{rT}，Γ_S = Γ_F·e^{2rT}，
        vega 相同，θ_BS = θ_B76 − rF·Δ_F，ρ_BS = ρ_B76 + T·F·Δ_F。
        """
        f = forward_from_spot(self.S, self.R, self.T)
        growth = (self.R * self.T).exp()
        c = black76_price(f, self.K, self.T, self.R, self.SIG, CALL)
        g = black76_greeks(f, self.K, self.T, self.R, self.SIG, CALL)
        assert close(c, "2.40", "0.005")
        assert close(g.delta * growth, "0.522", "0.0005")
        assert close(g.gamma * growth * growth, "0.066", "0.0005")
        assert close(g.vega, "12.1", "0.05")
        assert close(g.theta - self.R * f * g.delta, "-4.31", "0.005")
        assert close(g.rho + self.T * f * g.delta, "8.91", "0.005")

    @pytest.mark.parametrize("kind", [CALL, PUT])
    @pytest.mark.parametrize("f, k", [(100, 100), (100, 120), (100, 85)])
    def test_against_finite_differences(self, kind, f, k):
        f, k = D(f), D(k)
        t, r, s = D("0.5"), D("0.04"), D("0.3")
        h = D("1e-12")

        def price(ff=f, tt=t, rr=r, ss=s):
            return black76_price(ff, k, tt, rr, ss, kind)

        g = black76_greeks(f, k, t, r, s, kind)
        tol = D("1e-9")
        with hp():
            fd_delta = (price(ff=f + h) - price(ff=f - h)) / (2 * h)
            fd_gamma = (price(ff=f + h) - 2 * price() + price(ff=f - h)) / (h * h)
            fd_vega = (price(ss=s + h) - price(ss=s - h)) / (2 * h)
            # theta = ∂V/∂t = −∂V/∂T
            fd_theta = -(price(tt=t + h) - price(tt=t - h)) / (2 * h)
            fd_rho = (price(rr=r + h) - price(rr=r - h)) / (2 * h)
            assert abs(g.delta - fd_delta) < tol
            assert abs(g.gamma - fd_gamma) < tol
            assert abs(g.vega - fd_vega) < tol
            assert abs(g.theta - fd_theta) < tol
            assert abs(g.rho - fd_rho) < tol

    def test_delta_parity_and_signs(self):
        f, k, t, r, s = D(100), D(100), D(1), D("0.05"), D("0.2")
        gc = black76_greeks(f, k, t, r, s, CALL)
        gp = black76_greeks(f, k, t, r, s, PUT)
        with hp():
            assert abs(gc.delta - gp.delta - (-r * t).exp()) < D("1e-45")
        assert gc.gamma == gp.gamma and gc.vega == gp.vega
        assert 0 < gc.delta < 1 and -1 < gp.delta < 0
        assert gc.gamma > 0 and gc.vega > 0
        assert gc.rho < 0 and gp.rho < 0  # Black-76：rho = −T·V
        assert isinstance(gc, Greeks)

    @pytest.mark.parametrize("t, s", [(0, "0.2"), (1, 0)])
    def test_undefined(self, t, s):
        with pytest.raises(ValueError):
            black76_greeks(D(100), D(100), D(t), D("0.01"), D(s), CALL)


class TestCRR:
    def test_hull_american_put_on_stock(self):
        # Hull：S=50, K=50, r=10%, σ=40%, T=5 個月，5 步 → 4.49
        args = (D(50), D(50), D(5) / 12, D("0.1"), D("0.4"), PUT)
        assert close(crr_price(*args, steps=5, carry=D("0.1")), "4.49", "0.005")
        # Hull 同例：30、50、100 步 → 4.263、4.272、4.278
        for n, expected in ((30, "4.263"), (50, "4.272"), (100, "4.278")):
            assert close(crr_price(*args, steps=n, carry=D("0.1")), expected, "0.0005")

    def test_hull_american_put_on_futures(self):
        # Hull：F=31, K=30, r=5%, σ=30%, T=9 個月，3 步 → 2.84
        p = crr_price(D(31), D(30), D("0.75"), D("0.05"), D("0.3"), PUT, steps=3)
        assert close(p, "2.84", "0.005")

    @pytest.mark.parametrize("kind", [CALL, PUT])
    def test_converges_to_black76(self, kind):
        f, k, t, r, s = D(100), D(95), D(1), D("0.05"), D("0.25")
        exact = black76_price(f, k, t, r, s, kind)
        errors = {}
        for n in (25, 100, 400, 1600):
            approx = crr_price(f, k, t, r, s, kind, steps=n, american=False)
            errors[n] = abs(approx - exact)
            # CRR 誤差為 O(1/N) 且隨 N 振盪；此參數下實測 N·誤差 ≈ 0.6～2.2，
            # 以常數 3 檢查上界
            assert errors[n] < D(3) / n
        assert errors[1600] < D("0.002")
        assert errors[1600] < errors[25]

    def test_converges_to_black_scholes_for_stock(self):
        # 股票（carry=r）的歐式 CRR 收斂到 Black-Scholes（以 F=S·e^{rT} 的 Black-76）
        s0, k, t, r, s = D(42), D(40), D("0.5"), D("0.1"), D("0.2")
        exact = black76_price(forward_from_spot(s0, r, t), k, t, r, s, CALL)
        approx = crr_price(s0, k, t, r, s, CALL, steps=1000, american=False, carry=r)
        assert abs(approx - exact) < D("0.002")

    def test_european_parity_on_tree(self):
        f, k, t, r, s = D(100), D(110), D(1), D("0.03"), D("0.2")
        c = crr_price(f, k, t, r, s, CALL, steps=200, american=False)
        p = crr_price(f, k, t, r, s, PUT, steps=200, american=False)
        with hp():
            assert abs((c - p) - (-r * t).exp() * (f - k)) < D("1e-40")

    def test_american_futures_parity_bounds(self):
        # Hull：美式期貨選擇權 F·e^{−rT} − K < C − P < F − K·e^{−rT}
        f, k, t, r, s = D(100), D(100), D(1), D("0.08"), D("0.3")
        c = crr_price(f, k, t, r, s, CALL, steps=200)
        p = crr_price(f, k, t, r, s, PUT, steps=200)
        with hp():
            df = (-r * t).exp()
            assert f * df - k < c - p < f - k * df

    def test_american_at_least_european(self):
        for kind in (CALL, PUT):
            args = (D(100), D(100), D(1), D("0.08"), D("0.3"), kind)
            am = crr_price(*args, steps=100)
            eu = crr_price(*args, steps=100, american=False)
            assert am >= eu

    def test_american_call_no_dividend_equals_european(self):
        # 無股利股票的美式買權不會提前履約
        args = (D(50), D(50), D(1), D("0.05"), D("0.3"), CALL)
        am = crr_price(*args, steps=100, carry=D("0.05"))
        eu = crr_price(*args, steps=100, american=False, carry=D("0.05"))
        assert abs(am - eu) < D("1e-40")

    def test_one_step(self):
        # 單步手算：u=e^{0.2}, d=1/u, p=(1−d)/(u−d)，r=0
        f, k = D(100), D(100)
        with hp():
            u = D("0.2").exp()
            d = 1 / u
            p = (1 - d) / (u - d)
            expected = p * (f * u - k)
        got = crr_price(f, k, D(1), D(0), D("0.2"), CALL, steps=1, american=False)
        assert abs(got - expected) < D("1e-45")

    @pytest.mark.parametrize("steps", [0, -1, True, 1.5])
    def test_bad_steps(self, steps):
        with pytest.raises(ValueError):
            crr_price(D(100), D(100), D(1), D(0), D("0.2"), CALL, steps=steps)

    def test_zero_time_or_vol(self):
        with pytest.raises(ValueError):
            crr_price(D(100), D(100), D(0), D(0), D("0.2"), CALL, steps=10)
        with pytest.raises(ValueError):
            crr_price(D(100), D(100), D(1), D(0), D(0), CALL, steps=10)

    def test_invalid_probability(self):
        # 持有成本極大且步數少 → p ≥ 1，應拒絕
        with pytest.raises(ValueError):
            crr_price(D(100), D(100), D(1), D(0), D("0.05"), CALL, steps=1, carry=D(1))


class TestImpliedVolatility:
    @pytest.mark.parametrize("kind", [CALL, PUT])
    @pytest.mark.parametrize("vol", ["0.05", "0.25", "0.8", "2"])
    @pytest.mark.parametrize("k", [80, 100, 125])
    def test_round_trip(self, kind, vol, k):
        f, t, r = D(100), D("0.5"), D("0.02")
        price = black76_price(f, D(k), t, r, D(vol), kind)
        iv = implied_volatility(price, f, D(k), t, r, kind)
        assert abs(iv - D(vol)) < D("1e-10")

    def test_hull_futures_put(self):
        t, r = D(4) / 12, D("0.09")
        price = black76_price(D(20), D(20), t, r, D("0.25"), PUT)
        iv = implied_volatility(price, D(20), D(20), t, r, PUT)
        assert abs(iv - D("0.25")) < D("1e-10")

    def test_below_intrinsic(self):
        # 深價內買權：價格低於折現內含價值 → 無解
        with pytest.raises(NoImpliedVolatilityError):
            implied_volatility(D(5), D(110), D(100), D(1), D(0), CALL)

    def test_equal_to_intrinsic(self):
        with pytest.raises(NoImpliedVolatilityError):
            implied_volatility(D(10), D(110), D(100), D(1), D(0), CALL)

    def test_above_upper_bound(self):
        with pytest.raises(NoImpliedVolatilityError):
            implied_volatility(D(100), D(100), D(100), D(1), D(0), CALL)
        with pytest.raises(NoImpliedVolatilityError):
            implied_volatility(D(100), D(100), D(100), D(1), D(0), PUT)

    def test_zero_or_negative_price(self):
        for bad in (D(0), D(-1)):
            with pytest.raises(NoImpliedVolatilityError):
                implied_volatility(bad, D(100), D(100), D(1), D(0), CALL)

    def test_outside_search_interval(self):
        # σ=3 的價格在無套利區間內，但超出 upper=1 的搜尋範圍
        price = black76_price(D(100), D(100), D(1), D(0), D(3), CALL)
        with pytest.raises(NoImpliedVolatilityError):
            implied_volatility(price, D(100), D(100), D(1), D(0), CALL, upper=D(1))

    def test_zero_time(self):
        with pytest.raises(NoImpliedVolatilityError):
            implied_volatility(D(1), D(100), D(100), D(0), D(0), CALL)

    def test_error_is_value_error_subclass(self):
        assert issubclass(NoImpliedVolatilityError, ValueError)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"lower": D(0)},
            {"lower": D(2), "upper": D(1)},
            {"tol": D(0)},
        ],
    )
    def test_bad_parameters(self, kwargs):
        with pytest.raises(ValueError):
            implied_volatility(D(5), D(100), D(100), D(1), D(0), CALL, **kwargs)

    def test_max_iter_exhausted(self):
        price = black76_price(D(100), D(100), D(1), D(0), D("0.3"), CALL)
        with pytest.raises(NoImpliedVolatilityError):
            implied_volatility(
                price, D(100), D(100), D(1), D(0), CALL, tol=D("1e-40"), max_iter=2
            )

    def test_bracket_endpoint_is_root(self):
        price = black76_price(D(100), D(100), D(1), D(0), D("0.5"), CALL)
        iv = implied_volatility(price, D(100), D(100), D(1), D(0), CALL, upper=D("0.5"))
        assert iv == D("0.5")

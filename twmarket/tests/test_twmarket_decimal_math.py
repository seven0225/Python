import math
from decimal import Decimal as D
from decimal import localcontext

import pytest

from twmarket.decimal_math import PI, norm_cdf, norm_pdf, to_decimal


class TestToDecimal:
    def test_accepts_decimal_int_str(self):
        assert to_decimal(D("1.5")) == D("1.5")
        assert to_decimal(2) == D(2)
        assert to_decimal("95.5") == D("95.5")

    @pytest.mark.parametrize("bad", [1.5, 0.1, True, False])
    def test_rejects_float_and_bool(self, bad):
        with pytest.raises(TypeError):
            to_decimal(bad)

    def test_rejects_other_types(self):
        with pytest.raises(TypeError):
            to_decimal([1])  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", ["abc", "", "NaN", "Infinity", D("NaN")])
    def test_rejects_non_finite_or_unparsable(self, bad):
        with pytest.raises(ValueError):
            to_decimal(bad)


class TestNormal:
    def test_pdf_at_zero(self):
        # φ(0) = 1/√(2π) = 0.3989422804014326779399460599343818684758586...
        expected = D("0.39894228040143267793994605993438186847585863116")
        assert abs(norm_pdf(D(0)) - expected) < D("1e-45")

    def test_pdf_symmetric(self):
        assert norm_pdf(D("1.3")) == norm_pdf(D("-1.3"))

    def test_cdf_at_zero_is_half(self):
        assert norm_cdf(D(0)) == D("0.5")

    @pytest.mark.parametrize(
        "x", ["-8", "-3", "-1.96", "-0.5", "0.1", "1", "1.96", "3", "6.5"]
    )
    def test_cdf_matches_stdlib_erfc(self, x):
        # 獨立對照：標準函式庫 math.erfc（float）。float 僅作為測試用的對照組，
        # 不參與任何價格計算。erfc 在尾端的相對誤差約數個 ulp（x=-8 實測
        # 約 6e-15），故容許相對誤差 1e-13。
        oracle = 0.5 * math.erfc(-float(x) / math.sqrt(2))
        got = float(norm_cdf(D(x)))
        assert abs(got - oracle) <= 1e-13 * oracle

    def test_cdf_symmetry(self):
        for x in (D("0.3"), D("2.5"), D("7")):
            assert abs(norm_cdf(x) + norm_cdf(-x) - 1) < D("1e-45")

    def test_cdf_tails(self):
        assert norm_cdf(D(16)) == 1
        assert norm_cdf(D(-16)) == 0
        # 截斷點附近：絕對誤差不超過 1e-49（Φ(-15) ≈ 3.7e-51 會被算成 0）
        assert 0 <= norm_cdf(D(-15)) < D("1e-49")
        with localcontext() as ctx:
            ctx.prec = 60
            assert 1 - D("1e-49") < norm_cdf(D(15)) <= 1

    def test_pi_constant(self):
        assert str(PI).startswith("3.14159265358979323846264338327950288")

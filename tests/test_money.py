from decimal import Decimal

from payment_reconciliation.money import (
    AmountError,
    gateway_fee_paise,
    paise_integer_to_paise,
    paise_to_inr,
    rupee_string_to_paise,
)

import pytest


@pytest.mark.parametrize("raw,expected", [
    ("1000.00", 100_000),
    ("0.99", 99),
    ("1234.5", 123_450),
    ("1", 100),
    ("0.01", 1),
    ("100.005", 10_001),  # half-up at the sub-paisa boundary
    (" 250.25 ", 25_025),
])
def test_rupee_string_to_paise(raw, expected):
    assert rupee_string_to_paise(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "", "NaN", "inf", "12,34"])
def test_rupee_string_rejects_garbage(raw):
    with pytest.raises(AmountError):
        rupee_string_to_paise(raw)


@pytest.mark.parametrize("raw,expected", [
    (100_000, 100_000),
    ("100000", 100_000),
    ("1", 1),
    (0, 0),
])
def test_paise_integer_to_paise(raw, expected):
    assert paise_integer_to_paise(raw) == expected


@pytest.mark.parametrize("raw", ["100.5", "abc", "1_000.5"])
def test_paise_integer_rejects_fractional_and_garbage(raw):
    with pytest.raises(AmountError):
        paise_integer_to_paise(raw)


@pytest.mark.parametrize("captured,fee", [
    (100_000, 2_000),   # exactly 2%
    (1, 0),             # 0.02 paise -> 0
    (25, 1),            # exactly half a paisa -> rounds up (half-up)
    (75, 2),            # 1.5 paise -> 2
    (10_049, 201),      # 200.98 -> 201
    (10_050, 201),      # 201.00 -> 201
])
def test_gateway_fee_rounds_half_up(captured, fee):
    assert gateway_fee_paise(captured) == fee


def test_fee_basis_points_exactness():
    for amount in range(0, 5_000):
        fee = gateway_fee_paise(amount)
        exact = Decimal(amount) * Decimal("0.02")
        assert abs(Decimal(fee) - exact) <= Decimal("0.5")


@pytest.mark.parametrize("paise,text", [
    (0, "0.00"),
    (1, "0.01"),
    (99, "0.99"),
    (100, "1.00"),
    (123_456, "1234.56"),
    (-5, "-0.05"),
])
def test_paise_to_inr(paise, text):
    assert paise_to_inr(paise) == text


def test_exactness_beyond_float_integer_range():
    # 2**53 = 9007199254740992; beyond this, floats cannot represent every paisa exactly.
    assert rupee_string_to_paise("90071992547409.91") == 9_007_199_254_740_991
    assert gateway_fee_paise(9_007_199_254_740_991) == (9_007_199_254_740_991 * 2 + 50) // 100

"""Exact money handling.

Every amount in the pipeline is carried as an integer number of paise.
No floating-point arithmetic is used anywhere near money.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

RUPEE = 100
GATEWAY_FEE_BASIS_POINTS = 200  # 2.00%

_PAISE = Decimal("1")
_HUNDRED = Decimal("100")


class AmountError(ValueError):
    """Raised when an amount cannot be parsed into exact paise."""


def rupee_string_to_paise(raw: str) -> int:
    """Convert a rupee decimal string (API v1, e.g. \"1234.50\") to paise."""
    text = raw.strip()
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise AmountError(f"unparseable rupee amount: {raw!r}") from exc
    if value.is_nan() or value.is_infinite():
        raise AmountError(f"invalid rupee amount: {raw!r}")
    return int((value * _HUNDRED).quantize(_PAISE, rounding=ROUND_HALF_UP))


def paise_integer_to_paise(raw) -> int:
    """Convert an API v2 paise value (integer, e.g. 123450 or \"123450\") to paise."""
    text = str(raw).strip()
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise AmountError(f"unparseable paise amount: {raw!r}") from exc
    if value != value.to_integral_value():
        raise AmountError(f"paise amount is not a whole number: {raw!r}")
    return int(value)


def gateway_fee_paise(captured_paise: int) -> int:
    """2% of a captured amount, rounded to the nearest paisa (half-up).

    Integer math: floor((a * 2 + 50) / 100) is exactly round-half-up for
    non-negative a. The fee is deducted at settlement and is not refunded.
    """
    if captured_paise < 0:
        raise AmountError("captured amount cannot be negative")
    return (captured_paise * GATEWAY_FEE_BASIS_POINTS + 5000) // 10000


def paise_to_inr(paise: int) -> str:
    """Format paise as an exact rupee string with two decimals (e.g. \"1234.50\")."""
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    return f"{sign}{paise // RUPEE}.{paise % RUPEE:02d}"


def paise_to_decimal(paise: int) -> Decimal:
    return Decimal(paise) / _HUNDRED

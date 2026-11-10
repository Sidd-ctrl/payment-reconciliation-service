"""Timezone-safe timestamp handling.

All cut-off and expiry logic is anchored to Asia/Kolkata (IST, UTC+05:30).
Naive timestamps in the feed are treated as IST and documented as such;
aware timestamps are converted to IST. Internally everything is stored as
integer microseconds since the Unix epoch to keep comparisons exact and fast.
"""

import calendar
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
UTC = timezone.utc

SETTLEMENT_CUTOFF_IST = datetime(2026, 6, 30, 23, 59, 59, tzinfo=IST)
AUTHORIZATION_EXPIRY = timedelta(days=7)

_US = 1_000_000


class TimestampError(ValueError):
    """Raised when sent_at cannot be parsed."""


def parse_sent_at(raw: str) -> tuple[int, datetime]:
    """Parse an ISO-8601 timestamp. Returns (epoch_microseconds, datetime in IST).

    - Trailing "Z" is normalised to "+00:00".
    - Naive timestamps are assumed to be IST (the business reports in IST).
    - Aware timestamps are converted to IST.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise TimestampError(f"missing sent_at: {raw!r}")
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TimestampError(f"unparseable sent_at: {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    else:
        parsed = parsed.astimezone(IST)
    utc_naive = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    epoch_micros = calendar.timegm(utc_naive.utctimetuple()) * _US + utc_naive.microsecond
    return epoch_micros, parsed


def _to_epoch_micros(dt: datetime) -> int:
    utc_naive = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return calendar.timegm(utc_naive.utctimetuple()) * _US + utc_naive.microsecond


def cutoff_microseconds(cutoff: datetime) -> int:
    return _to_epoch_micros(cutoff)


def expiry_limit_microseconds(cutoff: datetime) -> int:
    """Authorizations strictly older than (cutoff - 7 days) are expired."""
    return _to_epoch_micros(cutoff - AUTHORIZATION_EXPIRY)

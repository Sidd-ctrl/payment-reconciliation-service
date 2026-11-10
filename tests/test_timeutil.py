from datetime import datetime, timedelta

import pytest

from payment_reconciliation.timeutil import (
    IST,
    SETTLEMENT_CUTOFF_IST,
    TimestampError,
    cutoff_microseconds,
    expiry_limit_microseconds,
    parse_sent_at,
)


def test_z_suffix_is_utc_converted_to_ist():
    micros, ist = parse_sent_at("2026-06-15T10:00:00Z")
    assert ist.utcoffset() == timedelta(hours=5, minutes=30)
    assert ist.hour == 15 and ist.minute == 30  # 10:00Z == 15:30 IST


def test_offset_timestamp_converted_to_ist():
    _, ist = parse_sent_at("2026-06-15T10:00:00+00:00")
    assert (ist.hour, ist.minute) == (15, 30)


def test_ist_timestamp_kept():
    _, ist = parse_sent_at("2026-06-15T10:00:00+05:30")
    assert (ist.hour, ist.minute) == (10, 0)


def test_naive_timestamp_assumed_ist():
    _, ist = parse_sent_at("2026-06-15T10:00:00")
    assert ist.tzinfo is not None
    assert (ist.hour, ist.minute) == (10, 0)


def test_same_instant_different_notations_equal():
    a, _ = parse_sent_at("2026-04-01T04:30:00Z")
    b, _ = parse_sent_at("2026-04-01T10:00:00+05:30")
    assert a == b


@pytest.mark.parametrize("raw", ["", "not-a-date", "2026-13-99T99:99:99Z", None])
def test_unparseable_timestamps_rejected(raw):
    with pytest.raises(TimestampError):
        parse_sent_at(raw)


def test_cutoff_is_ist_mid_night():
    assert SETTLEMENT_CUTOFF_IST.tzinfo is not None
    assert SETTLEMENT_CUTOFF_IST.utcoffset() == timedelta(hours=5, minutes=30)
    assert (SETTLEMENT_CUTOFF_IST.hour, SETTLEMENT_CUTOFF_IST.minute, SETTLEMENT_CUTOFF_IST.second) == (23, 59, 59)


def test_expiry_limit_is_cutoff_minus_seven_days():
    assert expiry_limit_microseconds(SETTLEMENT_CUTOFF_IST) == int(
        (SETTLEMENT_CUTOFF_IST - timedelta(days=7)).timestamp() * 1_000_000
    )


def test_cutoff_microseconds_roundtrip():
    assert cutoff_microseconds(SETTLEMENT_CUTOFF_IST) == int(SETTLEMENT_CUTOFF_IST.timestamp() * 1_000_000)

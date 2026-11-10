"""Streaming parsers for orders.csv and events.jsonl.

Parsers never hold more than one record in memory; they yield dataclasses.
Parsing problems are surfaced as typed exceptions so the caller decides
whether to count-and-skip (events) or abort (orders).
"""

import csv
import json
from typing import Iterator

from .models import GatewayEvent, VALID_EVENT_TYPES
from .money import AmountError, paise_integer_to_paise, rupee_string_to_paise
from .timeutil import parse_sent_at, TimestampError


class OrderParseError(ValueError):
    pass


class EventParseError(ValueError):
    pass


def stream_orders(path: str) -> Iterator[tuple[str, str, str, int]]:
    """Yield (order_id, customer_id, created_at, amount_paise) one row at a time."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"order_id", "amount_inr"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise OrderParseError(f"orders.csv is missing required columns: {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            order_id = (row.get("order_id") or "").strip()
            if not order_id:
                raise OrderParseError(f"orders.csv line {line_no}: empty order_id")
            amount_raw = (row.get("amount_inr") or "").strip()
            try:
                amount_paise = rupee_string_to_paise(amount_raw)
            except AmountError as exc:
                raise OrderParseError(f"orders.csv line {line_no}: bad amount_inr {amount_raw!r}") from exc
            yield (
                order_id,
                (row.get("customer_id") or "").strip(),
                (row.get("created_at") or "").strip(),
                amount_paise,
            )


def parse_event_line(line: str) -> GatewayEvent:
    """Parse and validate one JSONL line. Raises EventParseError on any defect."""
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise EventParseError(f"malformed JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise EventParseError("event is not a JSON object")

    event_id = raw.get("event_id")
    order_id = raw.get("order_id")
    event_type = raw.get("type")
    api_version = str(raw.get("api_version") or "").strip().lower()
    amount_raw = raw.get("amount")
    sent_at_raw = raw.get("sent_at")

    if not isinstance(event_id, str) or not event_id.strip():
        raise EventParseError("missing or invalid event_id")
    if not isinstance(order_id, str) or not order_id.strip():
        raise EventParseError("missing or invalid order_id")
    if event_type not in VALID_EVENT_TYPES:
        raise EventParseError(f"unknown event type: {event_type!r}")
    if api_version not in ("v1", "v2"):
        raise EventParseError(f"unsupported api_version: {raw.get('api_version')!r}")
    if amount_raw is None:
        raise EventParseError("missing amount")

    if api_version == "v1":
        if not isinstance(amount_raw, str):
            raise EventParseError("v1 amount must be a rupee decimal string")
        try:
            amount_paise = rupee_string_to_paise(amount_raw)
        except AmountError as exc:
            raise EventParseError(str(exc)) from exc
    else:
        try:
            amount_paise = paise_integer_to_paise(amount_raw)
        except AmountError as exc:
            raise EventParseError(str(exc)) from exc

    if amount_paise < 0:
        raise EventParseError("negative amount")

    try:
        sent_at_us, sent_at_ist = parse_sent_at(sent_at_raw)
    except TimestampError as exc:
        raise EventParseError(str(exc)) from exc

    delivery_attempt = raw.get("delivery_attempt")
    try:
        delivery_attempt = int(delivery_attempt) if delivery_attempt is not None else None
    except (TypeError, ValueError):
        delivery_attempt = None

    return GatewayEvent(
        event_id=event_id.strip(),
        order_id=order_id.strip(),
        type=event_type,
        amount_paise=amount_paise,
        api_version=api_version,
        sent_at_us=sent_at_us,
        sent_at_raw=str(sent_at_raw).strip(),
        sent_at_ist=sent_at_ist,
        delivery_attempt=delivery_attempt,
    )

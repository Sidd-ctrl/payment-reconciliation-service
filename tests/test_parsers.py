import pytest

from payment_reconciliation.parsers import EventParseError, parse_event_line, stream_orders
from payment_reconciliation.models import VALID_EVENT_TYPES


def base_event(**overrides):
    event = {
        "event_id": "evt-1",
        "order_id": "ORD-1",
        "type": "payment.captured",
        "amount": "100.00",
        "api_version": "v1",
        "sent_at": "2026-04-10T10:00:00+05:30",
        "delivery_attempt": 1,
    }
    event.update(overrides)
    return event


def as_line(event):
    import json
    return json.dumps(event)


def test_valid_v1_event_parses():
    event = parse_event_line(as_line(base_event()))
    assert event.api_version == "v1"
    assert event.amount_paise == 10_000


def test_valid_v2_event_parses():
    event = parse_event_line(as_line(base_event(api_version="v2", amount=10_000)))
    assert event.amount_paise == 10_000


def test_v1_v2_same_amount_equivalent():
    v1 = parse_event_line(as_line(base_event(api_version="v1", amount="250.75")))
    v2 = parse_event_line(as_line(base_event(api_version="v2", amount=25_075)))
    assert v1.amount_paise == v2.amount_paise == 25_075


def test_v1_amount_must_be_string():
    with pytest.raises(EventParseError):
        parse_event_line(as_line(base_event(api_version="v1", amount=100)))


def test_v2_amount_must_be_whole():
    with pytest.raises(EventParseError):
        parse_event_line(as_line(base_event(api_version="v2", amount="100.5")))


def test_unknown_type_rejected():
    with pytest.raises(EventParseError):
        parse_event_line(as_line(base_event(type="payment.refunded")))


@pytest.mark.parametrize("type_", VALID_EVENT_TYPES)
def test_all_documented_types_accepted(type_):
    event = parse_event_line(as_line(base_event(type=type_)))
    assert event.type == type_


def test_unknown_api_version_rejected():
    with pytest.raises(EventParseError):
        parse_event_line(as_line(base_event(api_version="v3")))


def test_missing_event_id_rejected():
    with pytest.raises(EventParseError):
        parse_event_line(as_line(base_event(event_id="")))


def test_missing_order_id_rejected():
    event = base_event()
    del event["order_id"]
    with pytest.raises(EventParseError):
        parse_event_line(as_line(event))


def test_negative_amount_rejected():
    with pytest.raises(EventParseError):
        parse_event_line(as_line(base_event(api_version="v2", amount=-50)))


def test_malformed_json_rejected():
    with pytest.raises(EventParseError):
        parse_event_line("{not json")


def test_bad_sent_at_rejected():
    with pytest.raises(EventParseError):
        parse_event_line(as_line(base_event(sent_at="whenever")))


def test_stream_orders_reads_bom_and_header(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text("\ufefforder_id,customer_id,created_at,amount_inr\nORD-9,CUST-9,2026-04-01T10:00:00+05:30,750.50\n", encoding="utf-8")
    rows = list(stream_orders(str(path)))
    assert rows == [("ORD-9", "CUST-9", "2026-04-01T10:00:00+05:30", 75_050)]


def test_stream_orders_requires_columns(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text("id,amount\nORD-9,100\n", encoding="utf-8")
    with pytest.raises(Exception):
        list(stream_orders(str(path)))

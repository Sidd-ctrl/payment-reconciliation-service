import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def write_orders(path, rows):
    lines = ["order_id,customer_id,created_at,amount_inr"]
    for order_id, customer_id, created_at, amount_inr in rows:
        lines.append(f"{order_id},{customer_id},{created_at},{amount_inr}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_events(path, events):
    with open(path, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def v1_event(event_id, order_id, type_, amount_rupees, sent_at, delivery_attempt=1):
    return {
        "event_id": event_id,
        "order_id": order_id,
        "type": type_,
        "amount": str(amount_rupees),
        "api_version": "v1",
        "sent_at": sent_at,
        "delivery_attempt": delivery_attempt,
    }


def v2_event(event_id, order_id, type_, amount_paise, sent_at, delivery_attempt=1):
    return {
        "event_id": event_id,
        "order_id": order_id,
        "type": type_,
        "amount": int(amount_paise),
        "api_version": "v2",
        "sent_at": sent_at,
        "delivery_attempt": delivery_attempt,
    }


def run_reconcile(tmp_path, orders, events, cutoff="2026-06-30T23:59:59+05:30"):
    from payment_reconciliation.cli import main
    orders_path = tmp_path / "orders.csv"
    events_path = tmp_path / "events.jsonl"
    out_dir = tmp_path / "out"
    write_orders(orders_path, orders)
    write_events(events_path, events)
    rc = main(["reconcile", "--orders", str(orders_path), "--events", str(events_path),
               "--out", str(out_dir), "--cutoff", cutoff])
    assert rc == 0
    return out_dir


def read_states(out_dir):
    import csv
    with open(out_dir / "order_states.csv", newline="", encoding="utf-8") as handle:
        return {row["order_id"]: row for row in csv.DictReader(handle)}


def read_summary(out_dir):
    return json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_orders():
    return [
        ("ORD-1", "CUST-1", "2026-04-01T10:00:00+05:30", "1000.00"),
        ("ORD-2", "CUST-2", "2026-04-02T10:00:00+05:30", "2000.00"),
        ("ORD-3", "CUST-3", "2026-04-03T10:00:00+05:30", "500.00"),
    ]

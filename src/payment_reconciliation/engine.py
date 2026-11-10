"""Reconciliation engine.

Pipeline:
  Phase 1  stage orders.csv into SQLite (streaming)
  Phase 2  stream events.jsonl line by line; validate, dedupe by event_id,
           split off orphans (events for unknown orders are never processed)
  Phase 3  merge-join the orders cursor and the per-order ordered events
           cursor; apply the state machine; stream results out

Events are applied in the order they happened (sent_at), not the order they
arrived in. Per-order processing is O(events of that order); memory stays
flat regardless of input size.
"""

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from .models import FINAL_STATES, OrderAccumulator
from .money import gateway_fee_paise, paise_to_inr
from .parsers import EventParseError, parse_event_line, stream_orders
from .store import StagingStore
from .timeutil import IST, SETTLEMENT_CUTOFF_IST, expiry_limit_microseconds



@dataclass
class ReconciliationStats:
    lines_read: int = 0
    unique_events: int = 0
    processed_events: int = 0
    duplicate_deliveries_ignored: int = 0
    orphan_events: int = 0
    invalid_events: int = 0
    invalid_event_examples: list = field(default_factory=list)
    duplicate_orders: int = 0
    orders_total: int = 0
    orders_by_state: dict = field(default_factory=lambda: {s: 0 for s in FINAL_STATES})
    mismatched_orders: int = 0
    total_captured_paise: int = 0
    total_refunded_paise: int = 0
    gateway_fees_paise: int = 0
    stale_failures_ignored: int = 0
    stale_authorizations_ignored: int = 0
    pending_refunds: int = 0
    refunds_without_capture: int = 0
    over_refunded_orders: int = 0

    @property
    def net_settlement_paise(self) -> int:
        return self.total_captured_paise - self.gateway_fees_paise - self.total_refunded_paise


def _apply_event(acc: OrderAccumulator, event_type: str, amount_paise: int, sent_at_us: int):
    """Apply one event in event-time order to the per-order accumulator."""
    if event_type == "payment.failed":
        if acc.capture_count > 0:
            acc.stale_failures_ignored += 1  # failure arriving after capture is stale
        else:
            acc.has_failure = True
    elif event_type == "payment.authorized":
        if acc.capture_count > 0:
            acc.stale_authorizations_ignored += 1
        elif acc.latest_authorization_us is None or sent_at_us > acc.latest_authorization_us:
            acc.latest_authorization_us = sent_at_us
    elif event_type == "payment.captured":
        acc.captured_paise += amount_paise
        acc.capture_count += 1
        acc.fees_paise += gateway_fee_paise(amount_paise)
    elif event_type == "refund.created":
        acc.pending_refund_count += 1
    elif event_type == "refund.processed":
        acc.refunded_paise += amount_paise
        acc.processed_refund_count += 1


def finalize_order(acc: OrderAccumulator, expiry_limit_us: int) -> str:
    if acc.capture_count > 0:
        if acc.refunded_paise >= acc.captured_paise and acc.refunded_paise > 0:
            state = "REFUNDED"
        elif acc.refunded_paise > 0:
            state = "PARTIALLY_REFUNDED"
        else:
            state = "CAPTURED"
    elif acc.latest_authorization_us is not None:
        state = "EXPIRED" if acc.latest_authorization_us < expiry_limit_us else "AUTHORIZED"
    elif acc.has_failure:
        state = "FAILED"
    else:
        state = "CREATED"
    return state


def _mismatch(acc: OrderAccumulator) -> bool:
    return acc.capture_count > 0 and acc.captured_paise != acc.amount_paise


def reconcile(orders_path: str, events_path: str, out_dir: str,
              work_db_path: str | None = None, cutoff: datetime = SETTLEMENT_CUTOFF_IST,
              keep_work_db: bool = False, progress_every: int = 1_000_000) -> ReconciliationStats:
    os.makedirs(out_dir, exist_ok=True)
    work_db_path = work_db_path or os.path.join(out_dir, ".reconcile_work.sqlite")
    stats = ReconciliationStats()
    store = StagingStore(work_db_path)
    try:
        stats.orders_total = store.stage_orders(stream_orders(orders_path))
        stats.duplicate_orders = store.duplicate_orders

        with open(events_path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stats.lines_read += 1
                line = line.strip()
                if not line:
                    stats.invalid_events += 1
                    continue
                try:
                    event = parse_event_line(line)
                except EventParseError as exc:
                    stats.invalid_events += 1
                    if len(stats.invalid_event_examples) < 20:
                        stats.invalid_event_examples.append(f"line {stats.lines_read}: {exc}")
                    continue
                stats.unique_events += 1
                outcome = store.stage_event(event)
                if outcome == "duplicate":
                    stats.duplicate_deliveries_ignored += 1
                    stats.unique_events -= 1
                elif outcome == "orphan":
                    stats.orphan_events += 1
                if stats.lines_read % 10_000 == 0:
                    store.commit()
                if progress_every and stats.lines_read % progress_every == 0:
                    print(f"  … staged {stats.lines_read:,} lines", flush=True)
        store.commit()
        stats.processed_events = stats.unique_events - stats.orphan_events

        stats = _merge_join(store, out_dir, stats, cutoff)
        _write_orphan_report(store, os.path.join(out_dir, "orphan_events.csv"))
        return stats
    finally:
        if keep_work_db:
            store.conn.commit()
            store.conn.close()
        else:
            store.close()


def _merge_join(store: StagingStore, out_dir: str, stats: ReconciliationStats,
                cutoff: datetime) -> ReconciliationStats:
    expiry_limit_us = expiry_limit_microseconds(cutoff)
    orders_path = os.path.join(out_dir, "order_states.csv")
    mismatch_path = os.path.join(out_dir, "mismatches.csv")

    orders_cur = store.orders_cursor()
    events_cur = store.events_cursor()

    order_row = orders_cur.fetchone()
    event_row = events_cur.fetchone()

    with open(orders_path, "w", newline="", encoding="utf-8") as orders_out, \
            open(mismatch_path, "w", newline="", encoding="utf-8") as mismatch_out:
        orders_writer = csv.writer(orders_out)
        orders_writer.writerow(["order_id", "final_state", "captured_inr", "refunded_inr", "mismatch"])
        mismatch_writer = csv.writer(mismatch_out)
        mismatch_writer.writerow(["order_id", "order_amount_inr", "captured_inr", "difference_inr"])

        while order_row is not None:
            order_id, _customer_id, _created_at, amount_paise = order_row
            acc = OrderAccumulator(order_id=order_id, amount_paise=amount_paise)

            while event_row is not None and event_row[0] < order_id:
                event_row = events_cur.fetchone()  # defensive; processed events ⊆ staged orders
            while event_row is not None and event_row[0] == order_id:
                _apply_event(acc, event_row[1], event_row[2], event_row[3])
                event_row = events_cur.fetchone()

            state = finalize_order(acc, expiry_limit_us)
            mismatch = _mismatch(acc)
            stats.orders_by_state[state] += 1
            if mismatch:
                stats.mismatched_orders += 1
            stats.total_captured_paise += acc.captured_paise
            stats.total_refunded_paise += acc.refunded_paise
            stats.gateway_fees_paise += acc.fees_paise
            stats.stale_failures_ignored += acc.stale_failures_ignored
            stats.stale_authorizations_ignored += acc.stale_authorizations_ignored
            stats.pending_refunds += acc.pending_refund_count
            if acc.refunded_paise > 0 and acc.captured_paise == 0:
                stats.refunds_without_capture += 1
            if acc.capture_count > 0 and acc.refunded_paise > acc.captured_paise:
                stats.over_refunded_orders += 1

            orders_writer.writerow([
                order_id,
                state,
                paise_to_inr(acc.captured_paise),
                paise_to_inr(acc.refunded_paise),
                "true" if mismatch else "false",
            ])
            if mismatch:
                mismatch_writer.writerow([
                    order_id,
                    paise_to_inr(acc.amount_paise),
                    paise_to_inr(acc.captured_paise),
                    paise_to_inr(acc.captured_paise - acc.amount_paise),
                ])
            order_row = orders_cur.fetchone()

    return stats


def _write_orphan_report(store: StagingStore, path: str):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["event_id", "order_id", "type", "amount_inr", "api_version", "sent_at"])
        for row in store.orphans_cursor():
            event_id, order_id, type_, amount_paise, api_version, sent_at_raw = row
            writer.writerow([event_id, order_id, type_, paise_to_inr(amount_paise), api_version, sent_at_raw])


def summary_dict(stats: ReconciliationStats, generated_at: datetime,
                 cutoff: datetime) -> dict:
    return {
        "generated_at_ist": generated_at.astimezone(IST).isoformat(timespec="seconds"),
        "settlement_cutoff_ist": cutoff.astimezone(IST).isoformat(timespec="seconds"),
        "total_orders": stats.orders_total,
        "orders_by_state": dict(stats.orders_by_state),
        "unique_events": stats.unique_events,
        "duplicate_deliveries_ignored": stats.duplicate_deliveries_ignored,
        "orphan_events": stats.orphan_events,
        "invalid_events": stats.invalid_events,
        "processed_events": stats.processed_events,
        "mismatched_orders": stats.mismatched_orders,
        "total_captured_inr": paise_to_inr(stats.total_captured_paise),
        "total_refunded_inr": paise_to_inr(stats.total_refunded_paise),
        "gateway_fees_inr": paise_to_inr(stats.gateway_fees_paise),
        "net_settlement_inr": paise_to_inr(stats.net_settlement_paise),
        "net_settlement_before_refunds_inr": paise_to_inr(stats.total_captured_paise - stats.gateway_fees_paise),
        "total_captured_paise": stats.total_captured_paise,
        "total_refunded_paise": stats.total_refunded_paise,
        "gateway_fees_paise": stats.gateway_fees_paise,
        "net_settlement_paise": stats.net_settlement_paise,
        "net_settlement_before_refunds_paise": stats.total_captured_paise - stats.gateway_fees_paise,
        "diagnostics": {
            "total_lines_read": stats.lines_read,
            "duplicate_orders_in_orders_csv": stats.duplicate_orders,
            "stale_failures_ignored": stats.stale_failures_ignored,
            "stale_authorizations_ignored": stats.stale_authorizations_ignored,
            "pending_refunds_not_yet_processed": stats.pending_refunds,
            "refunds_without_capture": stats.refunds_without_capture,
            "over_refunded_orders": stats.over_refunded_orders,
            "invalid_event_examples": stats.invalid_event_examples,
        },
    }


def write_summary(stats: ReconciliationStats, out_dir: str,
                  cutoff: datetime = SETTLEMENT_CUTOFF_IST) -> dict:
    generated_at = datetime.now(IST)
    summary = summary_dict(stats, generated_at, cutoff)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary

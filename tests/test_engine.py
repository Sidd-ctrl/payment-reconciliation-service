"""End-to-end pipeline tests for every scenario in the assignment brief."""

from conftest import read_states, read_summary, run_reconcile, v1_event, v2_event

T = lambda day, hhmm="10:00:00": f"2026-{day}T{hhmm}+05:30"


def one_order(amount="1000.00"):
    return [("ORD-1", "CUST-1", "2026-04-01T09:00:00+05:30", amount)]


def test_created_when_no_valid_events(tmp_path):
    out = run_reconcile(tmp_path, one_order(), [])
    assert read_states(out)["ORD-1"]["final_state"] == "CREATED"


def test_failed_only(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.failed", 0, T("04-05"))]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "FAILED"


def test_later_authorization_overrides_earlier_failure(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.failed", 0, "2026-06-24T10:00:00+05:30"),
        v2_event("e2", "ORD-1", "payment.authorized", 100_000, "2026-06-25T10:00:00+05:30"),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "AUTHORIZED"


def test_duplicate_delivery_counted_once(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05"), delivery_attempt=3),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    summary = read_summary(out)
    assert summary["unique_events"] == 1
    assert summary["duplicate_deliveries_ignored"] == 2
    states = read_states(out)
    assert states["ORD-1"]["captured_inr"] == "1000.00"
    assert summary["total_captured_inr"] == "1000.00"


def test_out_of_order_events_processed_in_event_time(tmp_path):
    # Capture arrives in the log BEFORE the authorization, but happened after it.
    events = [
        v2_event("e2", "ORD-1", "payment.captured", 100_000, T("04-06")),
        v2_event("e1", "ORD-1", "payment.authorized", 100_000, T("04-05")),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "CAPTURED"


def test_failure_after_capture_is_stale_and_ignored(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
        v2_event("e2", "ORD-1", "payment.failed", 0, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    summary = read_summary(out)
    assert read_states(out)["ORD-1"]["final_state"] == "CAPTURED"
    assert summary["diagnostics"]["stale_failures_ignored"] == 1


def test_failure_before_capture_in_log_but_after_in_time_is_stale(tmp_path):
    # Failure sent_at is after the capture, even though it is logged first.
    events = [
        v2_event("e2", "ORD-1", "payment.failed", 0, T("04-07")),
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "CAPTURED"


def test_mixed_api_versions_same_order(tmp_path):
    events = [
        v1_event("e1", "ORD-1", "payment.captured", "400.50", T("04-05")),
        v2_event("e2", "ORD-1", "refund.processed", 40_050, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order("400.50"), events)
    states = read_states(out)
    assert states["ORD-1"]["final_state"] == "REFUNDED"
    assert states["ORD-1"]["captured_inr"] == "400.50"
    assert states["ORD-1"]["refunded_inr"] == "400.50"


def test_partial_then_full_refund_transitions(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
        v2_event("e2", "ORD-1", "refund.processed", 30_000, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "PARTIALLY_REFUNDED"

    events.append(v2_event("e3", "ORD-1", "refund.processed", 70_000, T("04-07")))
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "REFUNDED"


def test_refund_created_is_pending_and_moves_no_money(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
        v2_event("e2", "ORD-1", "refund.created", 100_000, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    states = read_states(out)
    assert states["ORD-1"]["final_state"] == "CAPTURED"
    assert states["ORD-1"]["refunded_inr"] == "0.00"
    summary = read_summary(out)
    assert summary["diagnostics"]["pending_refunds_not_yet_processed"] == 1
    assert summary["total_refunded_inr"] == "0.00"


def test_authorization_expires_after_seven_days(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.authorized", 100_000, "2026-06-20T10:00:00+05:30")]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "EXPIRED"


def test_authorization_exactly_seven_days_old_is_not_expired(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.authorized", 100_000, "2026-06-23T23:59:59+05:30")]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "AUTHORIZED"


def test_authorization_one_second_beyond_seven_days_expires(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.authorized", 100_000, "2026-06-23T23:59:58+05:30")]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "EXPIRED"


def test_fresh_authorization_within_seven_days(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.authorized", 100_000, "2026-06-28T10:00:00+05:30")]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "AUTHORIZED"


def test_orphan_events_reported_not_processed(tmp_path):
    orders = one_order()
    events = [
        v2_event("e1", "GHOST-9", "payment.captured", 50_000, T("04-05")),
        v2_event("e1", "GHOST-9", "payment.captured", 50_000, T("04-05")),  # same event delivered twice
        v2_event("e2", "GHOST-9", "payment.captured", 50_000, T("04-06")),  # a different orphan event
        v2_event("e3", "ORD-1", "payment.captured", 100_000, T("04-05")),
    ]
    out = run_reconcile(tmp_path, orders, events)
    summary = read_summary(out)
    assert summary["orphan_events"] == 2
    assert summary["duplicate_deliveries_ignored"] == 1
    assert summary["total_captured_inr"] == "1000.00"
    states = read_states(out)
    assert "GHOST-9" not in states
    import csv
    with open(out / "orphan_events.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert {r["event_id"] for r in rows} == {"e1", "e2"}


def test_timezone_variants_order_events_identically(tmp_path):
    # Same instant written as Z and as +05:30; capture must order after authorization.
    events = [
        v2_event("e2", "ORD-1", "payment.captured", 100_000, "2026-04-06T04:30:00Z"),
        v2_event("e1", "ORD-1", "payment.authorized", 100_000, "2026-04-05T10:00:00+05:30"),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "CAPTURED"


def test_utc_late_evening_is_next_day_in_ist(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.authorized", 100_000, "2026-06-23T18:30:00Z")]  # = 2026-06-24 00:00 IST, within 7d
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "AUTHORIZED"


def test_captured_amount_mismatch_flagged_but_state_kept(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.captured", 90_000, T("04-05"))]
    out = run_reconcile(tmp_path, one_order("1000.00"), events)
    states = read_states(out)
    assert states["ORD-1"]["final_state"] == "CAPTURED"
    assert states["ORD-1"]["mismatch"] == "true"
    summary = read_summary(out)
    assert summary["mismatched_orders"] == 1
    import csv
    with open(out / "mismatches.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["order_id"] == "ORD-1"
    assert rows[0]["difference_inr"] == "-100.00"


def test_captured_equal_to_order_amount_no_mismatch(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05"))]
    out = run_reconcile(tmp_path, one_order("1000.00"), events)
    assert read_states(out)["ORD-1"]["mismatch"] == "false"


def test_multiple_captures_sum_and_compare(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 60_000, T("04-05")),
        v2_event("e2", "ORD-1", "payment.captured", 40_000, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order("1000.00"), events)
    states = read_states(out)
    assert states["ORD-1"]["captured_inr"] == "1000.00"
    assert states["ORD-1"]["mismatch"] == "false"


def test_malformed_lines_counted_and_skipped(tmp_path):
    orders = one_order()
    orders_path = tmp_path / "orders.csv"
    events_path = tmp_path / "events.jsonl"
    out_dir = tmp_path / "out"
    from conftest import write_orders
    write_orders(orders_path, orders)
    events_path.write_text(
        '{"event_id":"e1","order_id":"ORD-1","type":"payment.captured","amount":1000,"api_version":"v2","sent_at":"2026-04-05T10:00:00+05:30"}\n'
        "{broken json\n"
        "\n"
        '{"event_id":"e2","order_id":"ORD-1","type":"payment.captured","amount":-5,"api_version":"v2","sent_at":"2026-04-05T10:00:00+05:30"}\n',
        encoding="utf-8",
    )
    from payment_reconciliation.cli import main
    assert main(["reconcile", "--orders", str(orders_path), "--events", str(events_path),
                 "--out", str(out_dir)]) == 0
    summary = read_summary(out_dir)
    assert summary["total_captured_inr"] == "10.00"
    assert summary["invalid_events"] == 3


def test_refund_before_capture_reaches_correct_totals(tmp_path):
    events = [
        v2_event("e2", "ORD-1", "refund.processed", 20_000, T("04-05")),
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    states = read_states(out)
    assert states["ORD-1"]["captured_inr"] == "1000.00"
    assert states["ORD-1"]["refunded_inr"] == "200.00"
    assert states["ORD-1"]["final_state"] == "PARTIALLY_REFUNDED"


def test_over_refund_counts_as_refunded_and_is_diagnosed(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
        v2_event("e2", "ORD-1", "refund.processed", 150_000, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    states = read_states(out)
    assert states["ORD-1"]["final_state"] == "REFUNDED"
    summary = read_summary(out)
    assert summary["diagnostics"]["over_refunded_orders"] == 1


def test_refund_without_capture_does_not_invent_state(tmp_path):
    events = [v2_event("e1", "ORD-1", "refund.processed", 10_000, T("04-05"))]
    out = run_reconcile(tmp_path, one_order(), events)
    states = read_states(out)
    assert states["ORD-1"]["final_state"] == "CREATED"
    assert states["ORD-1"]["refunded_inr"] == "100.00"
    summary = read_summary(out)
    assert summary["diagnostics"]["refunds_without_capture"] == 1


def test_authorization_after_capture_is_not_used_for_expiry(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 100_000, "2026-06-01T10:00:00+05:30"),
        v2_event("e2", "ORD-1", "payment.authorized", 100_000, "2026-04-01T10:00:00+05:30"),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "CAPTURED"


def test_summary_fee_and_net_settlement_math(tmp_path):
    orders = one_order("1000.00") + [("ORD-2", "CUST-2", "2026-04-01T09:00:00+05:30", "2000.00")]
    events = [
        v2_event("e1", "ORD-1", "payment.captured", 100_000, T("04-05")),
        v2_event("e2", "ORD-2", "payment.captured", 200_000, T("04-05")),
        v2_event("e3", "ORD-2", "refund.processed", 50_000, T("04-06")),
    ]
    out = run_reconcile(tmp_path, orders, events)
    summary = read_summary(out)
    # fees: 2% of 1000.00 = 20.00 ; 2% of 2000.00 = 40.00 ; total 60.00
    assert summary["gateway_fees_inr"] == "60.00"
    assert summary["total_captured_inr"] == "3000.00"
    assert summary["total_refunded_inr"] == "500.00"
    assert summary["net_settlement_inr"] == "2440.00"  # 3000 - 60 - 500


def test_every_order_in_orders_csv_gets_a_row(tmp_path):
    orders = one_order() + [("ORD-EMPTY", "CUST-X", "2026-04-01T09:00:00+05:30", "10.00")]
    out = run_reconcile(tmp_path, orders, [])
    states = read_states(out)
    assert set(states) == {"ORD-1", "ORD-EMPTY"}
    assert states["ORD-EMPTY"]["final_state"] == "CREATED"


def test_zero_amount_capture_fee_is_zero(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.captured", 0, T("04-05"))]
    out = run_reconcile(tmp_path, one_order(), events)
    summary = read_summary(out)
    assert summary["gateway_fees_inr"] == "0.00"


def test_capture_overrides_earlier_failure(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.failed", 0, "2026-06-24T10:00:00+05:30"),
        v2_event("e2", "ORD-1", "payment.captured", 100_000, "2026-06-25T10:00:00+05:30"),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "CAPTURED"


def test_multiple_failures_then_authorization(tmp_path):
    events = [
        v2_event("e1", "ORD-1", "payment.failed", 0, "2026-06-22T10:00:00+05:30"),
        v2_event("e2", "ORD-1", "payment.failed", 0, "2026-06-23T10:00:00+05:30"),
        v2_event("e3", "ORD-1", "payment.authorized", 100_000, "2026-06-24T10:00:00+05:30"),
    ]
    out = run_reconcile(tmp_path, one_order(), events)
    assert read_states(out)["ORD-1"]["final_state"] == "AUTHORIZED"


def test_capture_of_zero_amount_is_not_mismatch(tmp_path):
    events = [v2_event("e1", "ORD-1", "payment.captured", 0, T("04-05"))]
    out = run_reconcile(tmp_path, one_order("1000.00"), events)
    states = read_states(out)
    assert states["ORD-1"]["final_state"] == "CAPTURED"
    assert states["ORD-1"]["mismatch"] == "true"  # captured (0) != billed (1000) with ≥1 capture


def test_unmixed_versions_partial_refund_boundary(tmp_path):
    # Refund of exactly captured amount in mixed versions -> REFUNDED
    events = [
        v1_event("e1", "ORD-1", "payment.captured", "999.99", T("04-05")),
        v2_event("e2", "ORD-1", "refund.processed", 99_999, T("04-06")),
    ]
    out = run_reconcile(tmp_path, one_order("999.99"), events)
    assert read_states(out)["ORD-1"]["final_state"] == "REFUNDED"

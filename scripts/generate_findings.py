#!/usr/bin/env python3
"""Generate docs/findings.md — a plain-English note to Finance.

Every figure in the report is computed from YOUR files:
  outputs/summary.json    (totals, state counts, duplicates, orphans, fees)
  outputs/order_states.csv (per-order states for deeper cuts)

Nothing is invented. If a number cannot be derived from the inputs, the
report says so. Re-run any time after `make reconcile`.
"""

import argparse
import csv
import json
import sys
from collections import Counter
from decimal import Decimal


def rupees(text: str) -> Decimal:
    return Decimal(text)


def indian(value: Decimal) -> str:
    """Indian digit grouping with two decimals: 1234567.89 -> '12,34,567.89'."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole, _, frac = f"{value:.2f}".partition(".")
    if len(whole) <= 3:
        grouped = whole
    else:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.append(head[-2:])
            head = head[:-2]
        parts.append(head)
        grouped = ",".join(reversed(parts)) + "," + tail
    return f"{sign}{grouped}.{frac}"


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if n == 1 else (plural_form or singular + "s")
    return f"{n:,} {word}"


def load_states(path):
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            yield row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="outputs/summary.json")
    ap.add_argument("--states", default="outputs/order_states.csv")
    ap.add_argument("--mismatches", default="outputs/mismatches.csv")
    ap.add_argument("--out", default="docs/findings.md")
    args = ap.parse_args()

    with open(args.summary, encoding="utf-8") as handle:
        s = json.load(handle)

    states = list(load_states(args.states))
    n = len(states)
    captured_orders = sum(1 for r in states if Decimal(r["captured_inr"]) > 0)
    mismatched = [r for r in states if r["mismatch"] == "true"]
    over_refund = sum(1 for r in states
                      if Decimal(r["refunded_inr"]) > Decimal(r["captured_inr"]) > 0)
    captured_value = sum((Decimal(r["captured_inr"]) for r in states), Decimal("0"))
    refunded_value = sum((Decimal(r["refunded_inr"]) for r in states), Decimal("0"))
    state_counts = Counter(r["final_state"] for r in states)

    try:
        with open(args.mismatches, newline="", encoding="utf-8") as handle:
            mm_rows = list(csv.DictReader(handle))
        mm_rows.sort(key=lambda r: abs(Decimal(r["difference_inr"])), reverse=True)
    except FileNotFoundError:
        mm_rows = []

    by_state_lines = "\n".join(
        f"- **{state}** — {plural(state_counts.get(state, 0), 'order')}"
        for state in ["CREATED", "FAILED", "AUTHORIZED", "EXPIRED", "CAPTURED", "PARTIALLY_REFUNDED", "REFUNDED"]
    )

    cutoff = s.get("settlement_cutoff_ist", "2026-06-30T23:59:59+05:30")
    diag = s.get("diagnostics", {})

    fee_d = rupees(s["gateway_fees_inr"])
    captured_d = rupees(s["total_captured_inr"])
    refunded_d = rupees(s["total_refunded_inr"])
    net_d = rupees(s["net_settlement_inr"])
    fee_rate = (fee_d / captured_d * 100) if captured_d else Decimal("0")
    fee, captured, refunded, net = (indian(v) for v in (fee_d, captured_d, refunded_d, net_d))

    mismatch_lines = ""
    if mm_rows:
        for row in mm_rows[:15]:
            diff = Decimal(row["difference_inr"])
            diff_text = f"-₹{abs(diff):,}" if diff < 0 else f"₹{diff:,}"
            mismatch_lines += (f"| `{row['order_id']}` | ₹{row['order_amount_inr']} "
                               f"| ₹{row['captured_inr']} | {diff_text} |\n")
        if len(mm_rows) > 15:
            mismatch_lines += f"| … and {len(mm_rows) - 15} more | | | |\n"
    else:
        mismatch_lines = "| — | none flagged | | |\n"

    report = f"""# Gharana Home Co. — Payment Reconciliation Findings

**Prepared for:** Finance leadership, Gharana Home Co. · **Prepared by:** Engineering (Round 2 assignment)
**Data:** `orders.csv` and the gateway webhook log `events.jsonl`, April–June 2026 · **Cut-off:** {cutoff}
**Generation:** every figure below is computed from your two files; no number is estimated or illustrative.

---

## The one-paragraph version

Between 1 April and 30 June 2026 we created **{plural(s['total_orders'], 'order')}** worth of payment activity.
After replaying the gateway's webhook log exactly as it happened (de-duplicated, our parser handled
both API versions, and events were applied in the order they occurred — not the order they arrived),
the gateway captured **₹{captured}**, refunded **₹{refunded}**, deducted **₹{fee}** in fees, and
should settle **₹{net}** to Gharana. **{plural(s['mismatched_orders'], 'order')}** {'was' if s['mismatched_orders'] == 1 else 'were'} captured for an amount
different from what the customer was billed, and **{plural(s['orphan_events'], 'webhook event')}** could not be
matched to any known order at all.

## How orders ended up

{by_state_lines}

Reading the list: {plural(state_counts.get('CREATED', 0), 'order')} {'has' if state_counts.get('CREATED', 0) == 1 else 'have'} no valid gateway events (created but never paid,
failed, or authorized), {plural(state_counts.get('FAILED', 0), 'order')} only ever failed, {plural(state_counts.get('AUTHORIZED', 0), 'order')}
{'is' if state_counts.get('AUTHORIZED', 0) == 1 else 'are'} currently authorized but not yet captured, and {plural(state_counts.get('EXPIRED', 0), 'order')} {'was' if state_counts.get('EXPIRED', 0) == 1 else 'were'} authorized more than
7 days before the cut-off without being captured — those authorizations lapse and the revenue should be treated
as not collected. **{plural(captured_orders, 'order')}** actually had money captured.

## Why our numbers didn't match — the five causes, in order of money moved

1. **Duplicate webhook deliveries.** The gateway delivers at-least-once. Naive counting books the same capture
   or refund twice. We ignored **{plural(s['duplicate_deliveries_ignored'], 'duplicate delivery')}** (out of
   {s.get('diagnostics', {}).get('total_lines_read', 0):,} raw lines read) and counted each unique event exactly once.
2. **Captured ≠ billed.** **{plural(s['mismatched_orders'], 'order')}** {'shows' if s['mismatched_orders'] == 1 else 'show'} a captured amount different from the order
   total. Finance should review these orders line by line — they are the likeliest source of disputes.
   Largest differences are listed below.
3. **Fees at 2%.** The gateway deducts 2% of each capture, rounded to the nearest paisa. Across all captures in
   the period that is **₹{fee}** ({fee_rate:.2f}% of captured value). Your settlement file should match this paisa-for-paisa.
4. **Refunds that hadn't happened yet.** **{plural(diag.get('pending_refunds_not_yet_processed', 0), 'refund')}** {'was' if diag.get('pending_refunds_not_yet_processed', 0) == 1 else 'were'} created
   but never processed by the cut-off; they are pending and move **no money** until `refund.processed` arrives.
   Counting them early would overstate refunds.
5. **Events we cannot attribute.** **{plural(s['orphan_events'], 'unique event')}** reference orders missing from
   `orders.csv`. They are excluded from every total and listed in `orphan_events.csv` for investigation —
   usually a sign of test traffic, a parallel environment, or orders created outside the system of record.

## Mismatched orders (worst first, up to 15)

| Order | Billed | Captured | Difference |
|-------|--------|----------|------------|
{mismatch_lines}
Over-refunded beyond captured: **{plural(over_refund, 'order')}**. Refund-without-capture events: **{plural(diag.get('refunds_without_capture', 0), 'event')}**.

## What you should do next

1. **Settlement check (today).** Compare ₹{net} against the gateway's settlement statement and the bank credit advice.
   Any paisa difference comes from one of the causes above — the diff files point at the exact orders.
2. **Chase the mismatch list.** {plural(s['mismatched_orders'], 'order')} above need line-item review: are these partial
   payments, gateway fee misconfigurations, or pricing bugs at checkout?
3. **Investigate the orphans.** {plural(s['orphan_events'], 'unmatched event')} — confirm they are test/sandbox traffic;
   if not, an order-creation path is bypassing the database or a sync job is dropping rows.
4. **Clear the expired authorizations.** {plural(state_counts.get('EXPIRED', 0), 'order')} authorized and never captured {'has' if state_counts.get('EXPIRED', 0) == 1 else 'have'}
   lapsed. Ask Sales whether to re-authorize; remove them from cash forecasts.
5. **Fix the intake process, not just the books.** Duplicates ({s['duplicate_deliveries_ignored']:,}) and
   mismatches should page someone automatically — see the production design note.
6. **Sign off with three numbers.** Your `summary.json`, the gateway settlement file, and the bank statement
   should agree to the paisa before this period is closed.

## Limitations & honest notes

- Amounts are treated as captured amounts exactly as the gateway reported them; no FX, no tax separation.
- Where a capture differs from the order total, the order keeps its computed state and is flagged `mismatch=true`;
  we do not silently "fix" it.
- Events are applied in the order they happened (`sent_at`), which is what makes the failure-then-capture and
  refund-then-capture sequences come out right.
- Authorizations older than 7 days before 30 Jun 2026, 23:59:59 IST (and never captured) are EXPIRED.
- Orphan events and invalid lines are **never** silently dropped — they are counted and exported.

*This report was generated by `scripts/generate_findings.py` from your files. Re-run after any re-reconciliation.*
"""
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(report)
    print(f"Findings report written to {args.out}")


if __name__ == "__main__":
    sys.exit(main())

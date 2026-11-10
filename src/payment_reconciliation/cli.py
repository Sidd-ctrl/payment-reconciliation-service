"""Command line interface.

  reconcile  Run the reconciliation pipeline.
  digest     Print key figures from an existing summary.json (for filling answers.csv).
"""

import argparse
import json
import sys
from datetime import datetime

from . import __version__
from .engine import reconcile, write_summary
from .timeutil import IST


def _parse_cutoff(value: str) -> datetime:
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="payment-reconciliation", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("reconcile", help="reconcile events.jsonl against orders.csv")
    rec.add_argument("--orders", default="data/orders.csv")
    rec.add_argument("--events", default="data/events.jsonl")
    rec.add_argument("--out", default="outputs")
    rec.add_argument("--work-db", default=None, help="SQLite staging file (default: <out>/.reconcile_work.sqlite)")
    rec.add_argument("--cutoff", default="2026-06-30T23:59:59+05:30",
                     help="settlement cut-off, ISO-8601 (default: 2026-06-30T23:59:59+05:30)")
    rec.add_argument("--keep-work-db", action="store_true", help="keep the SQLite staging file for inspection")

    dig = sub.add_parser("digest", help="print headline numbers from outputs/summary.json")
    dig.add_argument("--summary", default="outputs/summary.json")

    args = parser.parse_args(argv)

    if args.command == "reconcile":
        cutoff = _parse_cutoff(args.cutoff)
        print(f"Reconciling {args.events} against {args.orders}")
        print(f"Settlement cut-off: {cutoff.isoformat(timespec='seconds')}")
        stats = reconcile(args.orders, args.events, args.out,
                          work_db_path=args.work_db, cutoff=cutoff,
                          keep_work_db=args.keep_work_db)
        summary = write_summary(stats, args.out, cutoff)
        _print_report(summary)
        return 0

    if args.command == "digest":
        with open(args.summary, encoding="utf-8") as handle:
            summary = json.load(handle)
        _print_report(summary)
        return 0

    return 2


def _print_report(summary: dict) -> None:
    print()
    print("════════════════ PAYMENT RECONCILIATION — SUMMARY ════════════════")
    print(f"  Total orders                    : {summary['total_orders']:,}")
    for state, count in summary["orders_by_state"].items():
        print(f"    {state:<20}        : {count:,}")
    print(f"  Unique events                   : {summary['unique_events']:,}")
    print(f"  Duplicate deliveries ignored    : {summary['duplicate_deliveries_ignored']:,}")
    print(f"  Orphan events (unknown orders)  : {summary['orphan_events']:,}")
    print(f"  Invalid events                  : {summary['invalid_events']:,}")
    print(f"  Mismatched orders               : {summary['mismatched_orders']:,}")
    print(f"  Total captured                  : ₹{summary['total_captured_inr']}")
    print(f"  Total refunded                  : ₹{summary['total_refunded_inr']}")
    print(f"  Gateway fees (2%)               : ₹{summary['gateway_fees_inr']}")
    print(f"  Net settlement                  : ₹{summary['net_settlement_inr']}")
    print(f"    … before refund deduction    : ₹{summary.get('net_settlement_before_refunds_inr', '—')}")
    print("════════════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    sys.exit(main())

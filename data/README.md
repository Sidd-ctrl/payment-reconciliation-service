# Your datasets go here

Place the three files from the Arcass assignment folder in this directory:

| File | What | Committed to git? |
|------|------|-------------------|
| `orders.csv` | Every order: `order_id, customer_id, created_at, amount_inr` | **No** — unique & confidential |
| `events.jsonl` | One webhook per line (sent_at, api_version v1/v2, …) | **No** — unique & confidential |
| `answers.csv` | The assignment's answer sheet to fill in | **No** — unique & confidential |

`.gitignore` excludes all three on purpose: this repository is designed to be
uploaded publicly to GitHub for review, and the brief marks the data
"Confidential, do not share". Share outputs only through the submission
channel named in the brief (email/Drive with the named recipient).

## Expected columns

**orders.csv**
```
order_id,customer_id,created_at,amount_inr
ORD-1001,CUST-88,2026-04-03T14:22:00+05:30,2499.00
```

**events.jsonl** (one JSON object per line)
```
{"event_id": "evt_abc123", "order_id": "ORD-1001", "type": "payment.captured", "amount": "2499.00", "api_version": "v1", "sent_at": "2026-04-03T14:25:11+05:30", "delivery_attempt": 1}
{"event_id": "evt_def456", "order_id": "ORD-1001", "type": "refund.processed", "amount": 49900, "api_version": "v2", "sent_at": "2026-04-09T09:01:00Z", "delivery_attempt": 2}
```

The reconciler validates as it streams: unparseable lines are counted under
`invalid_events` in `summary.json` (with the first 20 examples) and skipped;
events whose `order_id` is absent from `orders.csv` are reported in
`outputs/orphan_events.csv` and never processed.

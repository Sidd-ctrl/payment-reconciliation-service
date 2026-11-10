"""Gharana Home Co. — Payment Reconciliation Service.

Reconciles gateway webhook events (events.jsonl) against the order database
(orders.csv) and reports the true final state and settlement position of
every order, using exact integer-paise arithmetic.
"""

__version__ = "1.0.0"

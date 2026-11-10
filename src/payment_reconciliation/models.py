"""Shared domain types."""

from dataclasses import dataclass, field
from datetime import datetime

VALID_EVENT_TYPES = (
    "payment.failed",
    "payment.authorized",
    "payment.captured",
    "refund.created",
    "refund.processed",
)

FINAL_STATES = (
    "CREATED",
    "FAILED",
    "AUTHORIZED",
    "EXPIRED",
    "CAPTURED",
    "PARTIALLY_REFUNDED",
    "REFUNDED",
)


@dataclass(frozen=True)
class GatewayEvent:
    event_id: str
    order_id: str
    type: str
    amount_paise: int
    api_version: str
    sent_at_us: int
    sent_at_raw: str
    sent_at_ist: datetime
    delivery_attempt: int | None


@dataclass
class OrderAccumulator:
    """Mutable per-order tally. Lives only while one order is being finalized."""

    order_id: str
    amount_paise: int
    has_failure: bool = False
    latest_authorization_us: int | None = None
    captured_paise: int = 0
    capture_count: int = 0
    refunded_paise: int = 0
    processed_refund_count: int = 0
    pending_refund_count: int = 0
    stale_failures_ignored: int = 0
    stale_authorizations_ignored: int = 0
    fees_paise: int = 0
    extra: dict = field(default_factory=dict)

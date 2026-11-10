"""SQLite staging store.

Events and orders are staged in an on-disk SQLite database so the pipeline
streams input and never holds the dataset in memory. Peak resident memory is
O(batch size), not O(50M events). SQLite is stdlib, transactional and fast
enough (millions of rows per minute with bulk inserts and relaxed durability
because the file is a disposable intermediate).
"""

import os
import sqlite3

SCHEMA = """
CREATE TABLE orders (
    order_id     TEXT PRIMARY KEY,
    customer_id  TEXT,
    created_at   TEXT,
    amount_paise INTEGER NOT NULL
);
CREATE TABLE events (
    event_id     TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    type         TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    api_version  TEXT NOT NULL,
    sent_at_us   INTEGER NOT NULL,
    sent_at_raw  TEXT NOT NULL,
    delivery_attempt INTEGER
);
CREATE INDEX idx_events_order ON events (order_id, sent_at_us, event_id);
CREATE TABLE orphans (
    event_id     TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    type         TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    api_version  TEXT NOT NULL,
    sent_at_raw  TEXT NOT NULL
);
CREATE TABLE stats (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""

INSERT_ORDER = "INSERT OR IGNORE INTO orders (order_id, customer_id, created_at, amount_paise) VALUES (?,?,?,?)"
INSERT_EVENT = "INSERT OR IGNORE INTO events (event_id, order_id, type, amount_paise, api_version, sent_at_us, sent_at_raw, delivery_attempt) VALUES (?,?,?,?,?,?,?,?)"
INSERT_ORPHAN = "INSERT OR IGNORE INTO orphans (event_id, order_id, type, amount_paise, api_version, sent_at_raw) VALUES (?,?,?,?,?,?)"


class StagingStore:
    def __init__(self, db_path: str):
        if os.path.exists(db_path):
            os.remove(db_path)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode = OFF")
        self.conn.execute("PRAGMA synchronous = OFF")
        self.conn.execute("PRAGMA temp_store = MEMORY")
        self.conn.executescript(SCHEMA)
        self._duplicate_orders = 0

    def stage_orders(self, rows, batch_size: int = 5000):
        total = 0
        seen_batch = []
        for row in rows:
            seen_batch.append(row)
            if len(seen_batch) >= batch_size:
                total += self._flush_orders(seen_batch)
                seen_batch = []
        if seen_batch:
            total += self._flush_orders(seen_batch)
        return total

    def _flush_orders(self, batch):
        cur = self.conn.executemany(INSERT_ORDER, batch)
        self.conn.commit()
        written = cur.rowcount if cur.rowcount is not None else len(batch)
        self._duplicate_orders += len(batch) - written
        return written

    @property
    def duplicate_orders(self):
        return self._duplicate_orders

    def order_exists(self, order_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        return row is not None

    def stage_event(self, event) -> str:
        """Insert one validated event. Returns 'inserted' | 'duplicate' | 'orphan'."""
        if not self.order_exists(event.order_id):
            cur = self.conn.execute(
                INSERT_ORPHAN,
                (event.event_id, event.order_id, event.type, event.amount_paise,
                 event.api_version, event.sent_at_raw),
            )
            return "orphan" if cur.rowcount else "duplicate"
        cur = self.conn.execute(
            INSERT_EVENT,
            (event.event_id, event.order_id, event.type, event.amount_paise,
             event.api_version, event.sent_at_us, event.sent_at_raw, event.delivery_attempt),
        )
        return "inserted" if cur.rowcount else "duplicate"

    def commit(self):
        self.conn.commit()

    def orders_cursor(self):
        return self.conn.execute(
            "SELECT order_id, customer_id, created_at, amount_paise FROM orders ORDER BY order_id"
        )

    def events_cursor(self):
        return self.conn.execute(
            "SELECT order_id, type, amount_paise, sent_at_us "
            "FROM events ORDER BY order_id, sent_at_us, event_id"
        )

    def orphans_cursor(self):
        return self.conn.execute(
            "SELECT event_id, order_id, type, amount_paise, api_version, sent_at_raw "
            "FROM orphans ORDER BY order_id, sent_at_raw, event_id"
        )

    def orphan_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM orphans").fetchone()[0]

    def count(self, table: str) -> int:
        allowed = {"orders", "events", "orphans"}
        if table not in allowed:
            raise ValueError(table)
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def close(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

BEGIN;

CREATE TABLE IF NOT EXISTS shift (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL,
    opened_by TEXT,
    opening_cash INTEGER DEFAULT 0,
    closed_at TEXT,
    closed_by TEXT,
    closing_cash INTEGER
);

CREATE INDEX IF NOT EXISTS idx_shift_opened_at ON shift(opened_at);

ALTER TABLE ticket ADD COLUMN shift_id INTEGER REFERENCES shift(id);

CREATE INDEX IF NOT EXISTS idx_ticket_ts ON ticket(ts);
CREATE INDEX IF NOT EXISTS idx_ticket_shift ON ticket(shift_id);
CREATE INDEX IF NOT EXISTS idx_ticket_item_ticket ON ticket_item(ticket_id);

COMMIT;


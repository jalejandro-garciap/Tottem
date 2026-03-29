BEGIN;

-- Pricing rules: one optional rule per product
CREATE TABLE IF NOT EXISTS pricing_rule (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id        INTEGER NOT NULL UNIQUE,
    wholesale_price   INTEGER DEFAULT 0,       -- wholesale price in cents
    wholesale_min_qty REAL    DEFAULT 0,        -- minimum qty to trigger wholesale
    discount_pct      REAL    DEFAULT 0,        -- discount percentage (0-100)
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(product_id) REFERENCES product(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pricing_rule_product ON pricing_rule(product_id);

-- Record applied pricing on each ticket item for audit trail
ALTER TABLE ticket_item ADD COLUMN price_type TEXT DEFAULT 'normal';
ALTER TABLE ticket_item ADD COLUMN original_price INTEGER DEFAULT NULL;

COMMIT;

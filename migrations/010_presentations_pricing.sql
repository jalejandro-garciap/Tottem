BEGIN;

-- ═══════════════════════════════════════════════════════════════════════
-- Migration 010: Presentations & Pricing (v1.3)
--
-- Adds product presentations (variants) with integrated pricing:
--   - Normal price per presentation
--   - Wholesale price with minimum quantity threshold
--   - Discount percentage (auto-applied)
--   - Wholesale and discount are mutually exclusive per presentation
--     (wholesale takes priority when qty threshold is reached)
--
-- Backward-compatible: creates a default "Única" presentation for
-- every existing product, preserving current behavior.
-- ═══════════════════════════════════════════════════════════════════════

-- 1) Flag on product: does it have multiple presentations?
ALTER TABLE product ADD COLUMN has_presentations INTEGER NOT NULL DEFAULT 0;

-- 2) Presentation table with integrated pricing
CREATE TABLE IF NOT EXISTS presentation (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id        INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    name              TEXT    NOT NULL DEFAULT 'Única',
    price             INTEGER NOT NULL,              -- normal price in cents
    wholesale_price   INTEGER DEFAULT NULL,          -- wholesale price in cents (NULL = no wholesale)
    wholesale_min_qty REAL    DEFAULT NULL,           -- min qty to activate wholesale
    discount_pct      INTEGER DEFAULT NULL,           -- discount % (NULL = no discount)
    active            INTEGER NOT NULL DEFAULT 1,
    sort_order        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_presentation_product ON presentation(product_id);
CREATE INDEX IF NOT EXISTS idx_presentation_active  ON presentation(product_id, active);

-- 3) Extend ticket_item to record presentation + applied pricing
ALTER TABLE ticket_item ADD COLUMN presentation_id   INTEGER DEFAULT NULL REFERENCES presentation(id);
ALTER TABLE ticket_item ADD COLUMN presentation_name TEXT    DEFAULT NULL;
ALTER TABLE ticket_item ADD COLUMN applied_price     INTEGER DEFAULT NULL;
ALTER TABLE ticket_item ADD COLUMN price_type        TEXT    DEFAULT 'normal';

-- 4) Migrate existing data: create "Única" presentation for every product
INSERT INTO presentation (product_id, name, price, active, sort_order)
SELECT id, 'Única', price, 1, 0 FROM product;

-- 5) Link existing ticket_items to their new default presentations
UPDATE ticket_item SET
  presentation_id = (
    SELECT pr.id FROM presentation pr
    WHERE pr.product_id = ticket_item.product_id
      AND pr.name = 'Única'
    LIMIT 1
  ),
  presentation_name = 'Única',
  applied_price = ticket_item.price,
  price_type = 'normal'
WHERE presentation_id IS NULL AND product_id IS NOT NULL;

COMMIT;

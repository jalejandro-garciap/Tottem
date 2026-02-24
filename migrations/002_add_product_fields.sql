BEGIN;

ALTER TABLE product ADD COLUMN unit TEXT DEFAULT 'pz';
ALTER TABLE product ADD COLUMN allow_decimal INTEGER NOT NULL DEFAULT 0;
ALTER TABLE product ADD COLUMN category TEXT DEFAULT 'General';

CREATE INDEX IF NOT EXISTS idx_product_active ON product(active);
CREATE INDEX IF NOT EXISTS idx_product_name ON product(name);

COMMIT;


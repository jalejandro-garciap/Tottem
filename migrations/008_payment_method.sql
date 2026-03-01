BEGIN;

ALTER TABLE ticket ADD COLUMN payment_method TEXT DEFAULT 'cash';

COMMIT;

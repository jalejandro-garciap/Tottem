BEGIN;

-- Create new table with quantity REAL
CREATE TABLE ticket_item_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    product_id INTEGER,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    quantity REAL NOT NULL, -- <- REAL instead of INTEGER
    FOREIGN KEY(ticket_id) REFERENCES ticket(id),
    FOREIGN KEY(product_id) REFERENCES product(id)
);

-- Copy existing data (cast to REAL)
INSERT INTO ticket_item_new (id, ticket_id, product_id, name, price, quantity)
SELECT id, ticket_id, product_id, name, price, CAST(quantity AS REAL)
FROM ticket_item;

-- Drop old table and rename
DROP TABLE ticket_item;
ALTER TABLE ticket_item_new RENAME TO ticket_item;

COMMIT;


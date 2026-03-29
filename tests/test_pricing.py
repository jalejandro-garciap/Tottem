# -*- coding: utf-8 -*-
"""
Tests for TOTTEM POS · Pricing Rules Service
"""
import sys
import os
import sqlite3
import pytest
from pathlib import Path

# Ensure src/ is on the path for imports
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

# We need to stub out the DB connection before importing pricing
# so it uses a temp in-memory database.
import tempfile

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TEST_DB_PATH = _test_db.name
_test_db.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch, tmp_path):
    """Set up a fresh in-memory test database with schema for each test."""
    db_path = str(tmp_path / "test.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS product (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            unit TEXT DEFAULT 'pz',
            allow_decimal INTEGER NOT NULL DEFAULT 0,
            category TEXT DEFAULT 'General',
            icon TEXT DEFAULT '',
            card_color TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS pricing_rule (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id    INTEGER NOT NULL UNIQUE,
            wholesale_price    INTEGER DEFAULT 0,
            wholesale_min_qty  REAL    DEFAULT 0,
            discount_pct       REAL    DEFAULT 0,
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(product_id) REFERENCES product(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ticket (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            total INTEGER NOT NULL,
            shift_id INTEGER,
            paid INTEGER DEFAULT 0,
            change_amount INTEGER DEFAULT 0,
            payment_method TEXT DEFAULT 'cash'
        );

        CREATE TABLE IF NOT EXISTS ticket_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            product_id INTEGER,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT 'pz',
            price_type TEXT DEFAULT 'normal',
            original_price INTEGER DEFAULT NULL,
            FOREIGN KEY(ticket_id) REFERENCES ticket(id),
            FOREIGN KEY(product_id) REFERENCES product(id)
        );

        INSERT INTO product (name, price, active) VALUES ('Helado', 5000, 1);
        INSERT INTO product (name, price, active) VALUES ('Queso', 3000, 1);
        INSERT INTO product (name, price, active) VALUES ('Pan', 1500, 1);
    """)
    conn.commit()
    conn.close()

    # Monkey-patch the connect function in services.sales
    def _fake_connect():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA busy_timeout=5000;")
        return c

    import services.sales as sales_mod
    monkeypatch.setattr(sales_mod, "connect", _fake_connect)

    # Also patch in pricing module (it imports connect from sales)
    import services.pricing as pricing_mod
    monkeypatch.setattr(pricing_mod, "connect", _fake_connect)

    yield


class TestResolvePrice:
    """Test the resolve_price function directly."""

    def test_normal_no_rule(self):
        from services.pricing import resolve_price
        final, ptype, orig = resolve_price(5000, 1.0, None)
        assert final == 5000
        assert ptype == "normal"
        assert orig is None

    def test_discount_applied(self):
        from services.pricing import resolve_price
        rule = {"discount_pct": 10, "wholesale_price": 0, "wholesale_min_qty": 0}
        final, ptype, orig = resolve_price(5000, 1.0, rule)
        assert final == 4500  # 10% off 5000
        assert ptype == "discount"
        assert orig == 5000

    def test_discount_20_percent(self):
        from services.pricing import resolve_price
        rule = {"discount_pct": 20, "wholesale_price": 0, "wholesale_min_qty": 0}
        final, ptype, orig = resolve_price(3000, 1.0, rule)
        assert final == 2400  # 20% off 3000
        assert ptype == "discount"
        assert orig == 3000

    def test_wholesale_below_threshold(self):
        from services.pricing import resolve_price
        rule = {"discount_pct": 0, "wholesale_price": 4000, "wholesale_min_qty": 5}
        final, ptype, orig = resolve_price(5000, 3.0, rule)
        # qty=3 < min=5, so normal price
        assert final == 5000
        assert ptype == "normal"
        assert orig is None

    def test_wholesale_at_threshold(self):
        from services.pricing import resolve_price
        rule = {"discount_pct": 0, "wholesale_price": 4000, "wholesale_min_qty": 5}
        final, ptype, orig = resolve_price(5000, 5.0, rule)
        # qty=5 >= min=5, wholesale
        assert final == 4000
        assert ptype == "wholesale"
        assert orig == 5000

    def test_wholesale_above_threshold(self):
        from services.pricing import resolve_price
        rule = {"discount_pct": 0, "wholesale_price": 4000, "wholesale_min_qty": 5}
        final, ptype, orig = resolve_price(5000, 10.0, rule)
        assert final == 4000
        assert ptype == "wholesale"
        assert orig == 5000

    def test_discount_takes_priority_over_wholesale(self):
        """Even if both are set (shouldn't happen via UI), discount wins."""
        from services.pricing import resolve_price
        rule = {"discount_pct": 10, "wholesale_price": 4000, "wholesale_min_qty": 5}
        final, ptype, orig = resolve_price(5000, 10.0, rule)
        # Discount takes priority per resolve_price logic
        assert final == 4500
        assert ptype == "discount"

    def test_inactive_rule_treated_as_none(self):
        from services.pricing import resolve_price
        # An empty/zero rule acts like normal
        rule = {"discount_pct": 0, "wholesale_price": 0, "wholesale_min_qty": 0}
        final, ptype, orig = resolve_price(5000, 10.0, rule)
        assert final == 5000
        assert ptype == "normal"


class TestPricingCRUD:
    """Test pricing rule CRUD operations against the test DB."""

    def test_upsert_and_get(self):
        from services.pricing import upsert_pricing_rule, get_pricing_rule
        rule_id = upsert_pricing_rule(1, wholesale_price=4000, wholesale_min_qty=5, active=True)
        assert rule_id > 0

        rule = get_pricing_rule(1)
        assert rule is not None
        assert rule["wholesale_price"] == 4000
        assert rule["wholesale_min_qty"] == 5
        assert rule["active"] == 1

    def test_upsert_updates_existing(self):
        from services.pricing import upsert_pricing_rule, get_pricing_rule
        upsert_pricing_rule(1, discount_pct=15, active=True)
        rule = get_pricing_rule(1)
        assert rule["discount_pct"] == 15

        # Update
        upsert_pricing_rule(1, discount_pct=20, active=True)
        rule = get_pricing_rule(1)
        assert rule["discount_pct"] == 20

    def test_mutual_exclusion(self):
        from services.pricing import upsert_pricing_rule
        with pytest.raises(ValueError, match="Cannot have wholesale and discount"):
            upsert_pricing_rule(
                1,
                wholesale_price=4000,
                wholesale_min_qty=5,
                discount_pct=10,
                active=True,
            )

    def test_delete(self):
        from services.pricing import upsert_pricing_rule, get_pricing_rule, delete_pricing_rule
        upsert_pricing_rule(2, discount_pct=10, active=True)
        assert get_pricing_rule(2) is not None

        delete_pricing_rule(2)
        assert get_pricing_rule(2) is None

    def test_get_all_active_rules(self):
        from services.pricing import upsert_pricing_rule, get_all_active_rules
        upsert_pricing_rule(1, discount_pct=10, active=True)
        upsert_pricing_rule(2, wholesale_price=2000, wholesale_min_qty=3, active=True)
        upsert_pricing_rule(3, discount_pct=5, active=False)  # inactive

        rules = get_all_active_rules()
        assert 1 in rules
        assert 2 in rules
        assert 3 not in rules  # inactive
        assert rules[1]["discount_pct"] == 10
        assert rules[2]["wholesale_price"] == 2000

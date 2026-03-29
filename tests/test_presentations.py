"""
Tests for presentations service and price resolution logic.
"""
import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Create a temporary SQLite DB with schema for testing."""
    import sqlite3

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create minimal schema
    conn.executescript("""
        CREATE TABLE product (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            unit TEXT DEFAULT 'pz',
            allow_decimal INTEGER NOT NULL DEFAULT 0,
            category TEXT DEFAULT 'General',
            icon TEXT DEFAULT NULL,
            card_color TEXT DEFAULT NULL,
            has_presentations INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE presentation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT 'Única',
            price INTEGER NOT NULL,
            wholesale_price INTEGER DEFAULT NULL,
            wholesale_min_qty REAL DEFAULT NULL,
            discount_pct INTEGER DEFAULT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE ticket (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            total INTEGER NOT NULL,
            shift_id INTEGER,
            paid INTEGER DEFAULT 0,
            change_amount INTEGER DEFAULT 0,
            payment_method TEXT DEFAULT 'cash'
        );

        CREATE TABLE shift (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_at TEXT NOT NULL,
            opened_by TEXT,
            opening_cash INTEGER DEFAULT 0,
            closed_at TEXT,
            closed_by TEXT,
            closing_cash INTEGER
        );

        CREATE TABLE employee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_no TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE ticket_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            product_id INTEGER,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT 'pz',
            presentation_id INTEGER DEFAULT NULL,
            presentation_name TEXT DEFAULT NULL,
            applied_price INTEGER DEFAULT NULL,
            price_type TEXT DEFAULT 'normal'
        );
    """)
    conn.commit()

    # Patch the connect function to return our test connection
    monkeypatch.setattr("services.sales.DB_PATH", db_path)
    monkeypatch.setattr("core.db.DB_PATH", db_path)

    # Force a fresh connection
    from core.db import close_cached
    close_cached()

    yield conn
    conn.close()
    close_cached()


class TestPresentationsService:
    """Tests for the presentations service."""

    def test_ensure_default_creates_unica(self, db_conn):
        """When a product has no presentations, ensure_default creates 'Única'."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 1500)")
        db_conn.commit()

        from services.presentations import ensure_default_presentation, list_presentations

        pres_id = ensure_default_presentation(1, 1500)
        assert pres_id > 0

        presos = list_presentations(1)
        assert len(presos) == 1
        assert presos[0]["name"] == "Única"
        assert presos[0]["price"] == 1500

    def test_ensure_default_idempotent(self, db_conn):
        """Calling ensure_default twice doesn't create duplicates."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 1500)")
        db_conn.commit()

        from services.presentations import ensure_default_presentation, list_presentations

        id1 = ensure_default_presentation(1, 1500)
        id2 = ensure_default_presentation(1, 1500)
        assert id1 == id2

        presos = list_presentations(1)
        assert len(presos) == 1

    def test_upsert_and_list_presentations(self, db_conn):
        """CRUD operations for presentations."""
        db_conn.execute("INSERT INTO product(name, price, has_presentations) VALUES('Helado', 1500, 1)")
        db_conn.commit()

        from services.presentations import upsert_presentation, list_presentations, get_presentation

        # Create presentations
        id_cono = upsert_presentation(
            product_id=1, name="Cono", price_cents=1500,
            wholesale_price_cents=1200, wholesale_min_qty=5.0
        )
        id_vaso = upsert_presentation(
            product_id=1, name="Vaso Grande", price_cents=3000,
            discount_pct=10
        )

        presos = list_presentations(1)
        assert len(presos) == 2
        assert presos[0]["name"] == "Cono"
        assert presos[1]["name"] == "Vaso Grande"

        # Verify get
        p = get_presentation(id_cono)
        assert p["wholesale_price"] == 1200
        assert p["wholesale_min_qty"] == 5.0

        p2 = get_presentation(id_vaso)
        assert p2["discount_pct"] == 10
        assert p2["wholesale_price"] is None  # Not set

    def test_delete_presentation(self, db_conn):
        """Deleting a presentation removes it."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 1500)")
        db_conn.commit()

        from services.presentations import upsert_presentation, delete_presentation, list_presentations

        pid = upsert_presentation(product_id=1, name="Cono", price_cents=1500)
        upsert_presentation(product_id=1, name="Vaso", price_cents=2000)

        assert len(list_presentations(1)) == 2

        delete_presentation(pid)
        assert len(list_presentations(1)) == 1

    def test_count_presentations(self, db_conn):
        """count_presentations counts only active ones."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 1500)")
        db_conn.commit()

        from services.presentations import upsert_presentation, count_presentations

        upsert_presentation(product_id=1, name="Cono", price_cents=1500, active=True)
        upsert_presentation(product_id=1, name="Vaso", price_cents=2000, active=False)

        assert count_presentations(1) == 1


class TestPriceResolution:
    """Tests for price resolution logic (normal, wholesale, discount)."""

    def test_normal_price(self, db_conn):
        """Without wholesale or discount, returns normal price."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 1500)")
        db_conn.commit()

        from services.presentations import upsert_presentation, resolve_price

        pres_id = upsert_presentation(product_id=1, name="Cono", price_cents=1500)

        price, ptype = resolve_price(pres_id, qty=1.0)
        assert price == 1500
        assert ptype == "normal"

        price, ptype = resolve_price(pres_id, qty=10.0)
        assert price == 1500
        assert ptype == "normal"

    def test_wholesale_activates_at_threshold(self, db_conn):
        """Wholesale price activates when qty >= wholesale_min_qty."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 1500)")
        db_conn.commit()

        from services.presentations import upsert_presentation, resolve_price

        pres_id = upsert_presentation(
            product_id=1, name="Cono", price_cents=1500,
            wholesale_price_cents=1200, wholesale_min_qty=5.0
        )

        # Below threshold: normal
        price, ptype = resolve_price(pres_id, qty=4.0)
        assert price == 1500
        assert ptype == "normal"

        # At threshold: wholesale
        price, ptype = resolve_price(pres_id, qty=5.0)
        assert price == 1200
        assert ptype == "wholesale"

        # Above threshold: wholesale
        price, ptype = resolve_price(pres_id, qty=10.0)
        assert price == 1200
        assert ptype == "wholesale"

    def test_discount_auto_applied(self, db_conn):
        """Discount is auto-applied when configured."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 2000)")
        db_conn.commit()

        from services.presentations import upsert_presentation, resolve_price

        pres_id = upsert_presentation(
            product_id=1, name="Vaso", price_cents=2000,
            discount_pct=15
        )

        price, ptype = resolve_price(pres_id, qty=1.0)
        assert price == 1700  # 2000 * 0.85 = 1700
        assert ptype == "discount"

    def test_wholesale_takes_priority_over_discount(self, db_conn):
        """When both wholesale and discount are configured, wholesale wins at threshold."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 2000)")
        db_conn.commit()

        from services.presentations import upsert_presentation, resolve_price

        # Note: upsert_presentation normalizes — if wholesale is set, discount is cleared
        pres_id = upsert_presentation(
            product_id=1, name="Cono", price_cents=2000,
            wholesale_price_cents=1500, wholesale_min_qty=3.0,
            discount_pct=10  # This gets cleared because wholesale is set
        )

        # Below wholesale threshold: normal (discount was cleared)
        price, ptype = resolve_price(pres_id, qty=2.0)
        assert ptype == "normal"
        assert price == 2000

        # At wholesale threshold: wholesale
        price, ptype = resolve_price(pres_id, qty=3.0)
        assert price == 1500
        assert ptype == "wholesale"

    def test_resolve_price_from_data(self, db_conn):
        """resolve_price_from_data works without DB lookup."""
        from services.presentations import resolve_price_from_data

        # Normal
        p, t = resolve_price_from_data(1000, None, None, None, 1.0)
        assert p == 1000 and t == "normal"

        # Wholesale
        p, t = resolve_price_from_data(1000, 800, 3.0, None, 5.0)
        assert p == 800 and t == "wholesale"

        # Below wholesale threshold → normal
        p, t = resolve_price_from_data(1000, 800, 3.0, None, 2.0)
        assert p == 1000 and t == "normal"

        # Discount
        p, t = resolve_price_from_data(1000, None, None, 20, 1.0)
        assert p == 800 and t == "discount"

    def test_sync_default_price(self, db_conn):
        """sync_default_price updates 'Única' when product has only one presentation."""
        db_conn.execute("INSERT INTO product(name, price) VALUES('Helado', 1500)")
        db_conn.commit()

        from services.presentations import ensure_default_presentation, sync_default_price, get_presentation

        pres_id = ensure_default_presentation(1, 1500)
        p = get_presentation(pres_id)
        assert p["price"] == 1500

        sync_default_price(1, 2000)
        p = get_presentation(pres_id)
        assert p["price"] == 2000


class TestCartItemWithPresentations:
    """Tests for CartItem with presentation fields."""

    def test_cart_item_default_fields(self):
        """CartItem without presentation fields uses defaults."""
        from services.sales import CartItem

        item = CartItem(product_id=1, name="Helado", price=1500, qty=2.0, unit="pz")
        assert item.presentation_id is None
        assert item.presentation_name is None
        assert item.applied_price is None
        assert item.price_type == "normal"

    def test_cart_item_with_presentation(self):
        """CartItem with presentation fields set."""
        from services.sales import CartItem

        item = CartItem(
            product_id=1, name="Helado", price=1500, qty=5.0, unit="pz",
            presentation_id=10, presentation_name="Cono",
            applied_price=1200, price_type="wholesale"
        )
        assert item.presentation_id == 10
        assert item.presentation_name == "Cono"
        assert item.applied_price == 1200
        assert item.price_type == "wholesale"


class TestSaveTicketWithPresentations:
    """Tests for save_ticket with presentation data."""

    def test_save_ticket_stores_presentation_fields(self, db_conn):
        """save_ticket persists presentation_id, presentation_name, applied_price, price_type."""
        # Insert a shift
        db_conn.execute(
            "INSERT INTO product(name, price) VALUES('Helado', 1500)"
        )
        db_conn.commit()

        from services.sales import CartItem, save_ticket, get_ticket_items

        items = [
            CartItem(
                product_id=1, name="Helado", price=1500, qty=5.0, unit="pz",
                presentation_id=99, presentation_name="Cono",
                applied_price=1200, price_type="wholesale"
            ),
        ]

        tid = save_ticket(items, shift_id=None, paid_cents=6000, change_cents=0)
        assert tid > 0

        loaded = get_ticket_items(tid)
        assert len(loaded) == 1
        it = loaded[0]
        assert it.presentation_id == 99
        assert it.presentation_name == "Cono"
        assert it.applied_price == 1200
        assert it.price_type == "wholesale"

    def test_save_ticket_uses_applied_price_for_total(self, db_conn):
        """Total should use applied_price when set."""
        db_conn.execute(
            "INSERT INTO product(name, price) VALUES('Helado', 1500)"
        )
        db_conn.commit()

        from services.sales import CartItem, save_ticket

        items = [
            CartItem(
                product_id=1, name="Helado", price=1500, qty=5.0, unit="pz",
                applied_price=1200, price_type="wholesale"
            ),
        ]

        tid = save_ticket(items, shift_id=None, paid_cents=6000, change_cents=0)

        # Total should be 1200 * 5 = 6000, not 1500 * 5 = 7500
        row = db_conn.execute("SELECT total FROM ticket WHERE id=?", (tid,)).fetchone()
        assert row[0] == 6000

    def test_save_ticket_backward_compat(self, db_conn):
        """CartItem without presentation fields still works (backward compat)."""
        db_conn.execute(
            "INSERT INTO product(name, price) VALUES('Helado', 1500)"
        )
        db_conn.commit()

        from services.sales import CartItem, save_ticket, get_ticket_items

        items = [
            CartItem(product_id=1, name="Helado", price=1500, qty=2.0, unit="pz"),
        ]

        tid = save_ticket(items, shift_id=None, paid_cents=3000, change_cents=0)
        loaded = get_ticket_items(tid)
        assert len(loaded) == 1
        it = loaded[0]
        assert it.price == 1500
        assert it.applied_price == 1500  # Falls back to base price
        assert it.price_type == "normal"

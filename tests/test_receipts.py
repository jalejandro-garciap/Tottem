import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.receipts import render_ticket
from services.sales import CartItem


def _write_config(tmp_path, *, header: str | None, footer: str | None) -> None:
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "store": {
                    "ticket_header": header,
                    "ticket_footer": footer,
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_render_ticket_formats_lines_and_totals(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Encabezado\nLinea Extra", footer="Gracias!")
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket(
        [
            CartItem(1, "Water", 1200, 2, "pz"),
            CartItem(2, "Chips", 250, 1, "pz"),
        ],
        paid_cents=3000,
        change_cents=350,
    )

    expected = (
        "Encabezado\n"
        "Linea Extra\n"
        "------------------------------\n"
        "x2 Water\n"
        "   $ 12.00\n"
        "x1 Chips\n"
        "   $ 2.50\n"
        "------------------------------\n"
        "TOTAL: $ 26.50\n"
        "Pago:  $ 30.00\n"
        "Cambio:$ 3.50\n"
        "\n"
        "Gracias!\n"
    )

    assert txt == expected


def test_render_ticket_default_header_when_missing_config(monkeypatch, tmp_path):
    missing_config = tmp_path / "missing.yaml"
    monkeypatch.setattr("services.receipts.CONFIG_PATH", missing_config)

    txt = render_ticket([CartItem(1, "Café", 100, 1, "pz")])

    expected = (
        "Mi Tienda\n"
        "------------------------------\n"
        "x1 Café\n"
        "   $ 1.00\n"
        "------------------------------\n"
        "TOTAL: $ 1.00\n"
    )

    assert txt == expected


def test_render_ticket_cash_payment_shows_paid_and_change(monkeypatch, tmp_path):
    """Cash payment shows Pago/Cambio lines."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket(
        [CartItem(1, "Agua", 1500, 1, "pz")],
        paid_cents=2000,
        change_cents=500,
        payment_method="cash",
    )

    assert "Pago:  $ 20.00" in txt
    assert "Cambio:$ 5.00" in txt
    assert "Metodo: Tarjeta" not in txt


def test_render_ticket_card_payment_shows_method(monkeypatch, tmp_path):
    """Card payment shows 'Metodo: Tarjeta' instead of Pago/Cambio."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket(
        [CartItem(1, "Agua", 1500, 1, "pz")],
        paid_cents=1500,
        change_cents=0,
        payment_method="card",
    )

    assert "Metodo: Tarjeta" in txt
    assert "Pago:" not in txt
    assert "Cambio:" not in txt


def test_render_ticket_no_method_defaults_to_cash(monkeypatch, tmp_path):
    """Omitting payment_method maintains backward compat (cash behavior)."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket(
        [CartItem(1, "Agua", 1500, 1, "pz")],
        paid_cents=2000,
        change_cents=500,
    )

    assert "Pago:  $ 20.00" in txt
    assert "Cambio:$ 5.00" in txt
    assert "Metodo: Tarjeta" not in txt


# ═══════════════════════════════════════════════════════════════════
# v1.3: Presentation & Pricing Tests
# ═══════════════════════════════════════════════════════════════════

def test_render_ticket_with_presentation_name(monkeypatch, tmp_path):
    """Items with presentation_name show it on the ticket."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket([
        CartItem(1, "Helado", 1500, 2, "pz",
                 presentation_id=10, presentation_name="Cono",
                 applied_price=1500, price_type="normal"),
    ])

    assert "Helado (Cono)" in txt
    assert "$ 15.00" in txt
    assert "TOTAL: $ 30.00" in txt


def test_render_ticket_unica_presentation_hidden(monkeypatch, tmp_path):
    """Items with 'Única' presentation name don't show it (backward compat)."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket([
        CartItem(1, "Helado", 1500, 1, "pz",
                 presentation_id=10, presentation_name="Única",
                 applied_price=1500, price_type="normal"),
    ])

    assert "(Única)" not in txt
    assert "Helado" in txt


def test_render_ticket_wholesale_tag(monkeypatch, tmp_path):
    """Wholesale items show MAYOREO tag and use applied_price for total."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket([
        CartItem(1, "Helado", 1500, 5, "pz",
                 presentation_id=10, presentation_name="Cono",
                 applied_price=1200, price_type="wholesale"),
    ])

    assert "MAYOREO" in txt
    assert "$ 12.00" in txt
    # Total should be 1200 * 5 = 6000 cents = $60.00
    assert "TOTAL: $ 60.00" in txt


def test_render_ticket_discount_tag(monkeypatch, tmp_path):
    """Discounted items show DTO tag and use applied_price for total."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket([
        CartItem(1, "Helado", 2000, 1, "pz",
                 presentation_id=10, presentation_name="Vaso",
                 applied_price=1700, price_type="discount"),
    ])

    assert "DTO" in txt
    assert "$ 17.00" in txt
    assert "TOTAL: $ 17.00" in txt


def test_render_ticket_backward_compat_no_presentation_fields(monkeypatch, tmp_path):
    """CartItem without v1.3 fields still renders correctly."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket([
        CartItem(1, "Agua", 1000, 3, "pz"),
    ])

    assert "Agua" in txt
    assert "$ 10.00" in txt
    assert "TOTAL: $ 30.00" in txt
    # No tags should appear
    assert "MAYOREO" not in txt
    assert "DTO" not in txt

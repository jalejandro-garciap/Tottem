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
    assert "Método: Tarjeta" not in txt


def test_render_ticket_card_payment_shows_method(monkeypatch, tmp_path):
    """Card payment shows 'Método: Tarjeta' instead of Pago/Cambio."""
    config_path = tmp_path / "config.yaml"
    _write_config(tmp_path, header="Test", footer=None)
    monkeypatch.setattr("services.receipts.CONFIG_PATH", config_path)

    txt = render_ticket(
        [CartItem(1, "Agua", 1500, 1, "pz")],
        paid_cents=1500,
        change_cents=0,
        payment_method="card",
    )

    assert "Método: Tarjeta" in txt
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
    assert "Método: Tarjeta" not in txt

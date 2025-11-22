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

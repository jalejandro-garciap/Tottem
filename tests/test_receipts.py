from src.services.receipts import render_ticket
from src.services.sales import CartItem


def test_render_ticket():
    txt = render_ticket([CartItem(1, "Water", 1200, 2)])
    assert "TOTAL" in txt

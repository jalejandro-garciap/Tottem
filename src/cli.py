import typer
from rich import print

from drivers.printer_escpos import EscposPrinter
from services.reports import report_x, report_z

app = typer.Typer(add_completion=False)

@app.command("print-test")
def print_test():
    """Send a simple test to the ESC/POS printer."""
    EscposPrinter().selftest()
    print("[green]OK:[/green] test sent.")

@app.command("drawer-open")
def drawer_open():
    """Open the cash drawer."""
    EscposPrinter().open_drawer()
    print("[green]OK:[/green] drawer opened.")

@app.command("run-kiosk")
def run_kiosk():
    """Start kiosk UI."""
    from ui.kiosk_app import run
    run()

@app.command("run-admin")
def run_admin():
    """Start admin/configuration UI."""
    from ui.admin_app import run
    run()

@app.command("x-report")
def x_report():
    """Preview current shift totals (doesn't close)."""
    txt, _ = report_x()
    print(txt)

@app.command("z-report")
def z_report(
    closed_by: str = typer.Option("", help="Name/initials of the user closing the shift."),
    closing_cash: int = typer.Option(0, help="Closing cash in cents (optional)."),
):
    """Close current shift and print final totals."""
    txt = report_z(closed_by=closed_by, closing_cash=closing_cash)
    print(txt)

if __name__ == "__main__":
    app()


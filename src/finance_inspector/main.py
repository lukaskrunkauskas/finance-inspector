from __future__ import annotations

from pathlib import Path
import csv
import typer
from rich import print
from rich.table import Table

from finance_inspector.parsing.revolut_pdf import parse_revolut_statement_pdf
app = typer.Typer(no_args_is_help=True, help="Finance Inspector: parse bank PDFs and analyze spending")


def _export_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["date", "title", "details", "money_out", "money_in", "balance", "currency"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})


@app.command()
def parse(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False, help="Path to a Revolut statement PDF"),
    csv_out: Path | None = typer.Option(None, "--csv", help="Write parsed transactions to a CSV file"),
    limit: int = typer.Option(20, "--limit", min=1, max=500, help="How many rows to preview in the terminal"),
):
    """
    Parse a Revolut statement PDF, preview results, and optionally export CSV.
    """
    if pdf.suffix.lower() != ".pdf":
        raise typer.BadParameter("File must be a .pdf")

    txs = parse_revolut_statement_pdf(str(pdf))

    # Normalize to dicts (keeps main decoupled from your internal Tx class)
    rows: list[dict] = []
    total_out = 0.0
    total_in = 0.0

    for t in txs:
        row = {
            "date": getattr(t, "booking_date", None).isoformat() if getattr(t, "booking_date", None) else None,
            "title": getattr(t, "title", "") or "",
            "details": getattr(t, "details", "") or "",
            "money_out": getattr(t, "money_out", None),
            "money_in": getattr(t, "money_in", None),
            "balance": getattr(t, "balance", None),
            "currency": getattr(t, "currency", "EUR") or "EUR",
        }
        rows.append(row)
        if row["money_out"]:
            total_out += float(row["money_out"])
        if row["money_in"]:
            total_in += float(row["money_in"])

    print(f"[green]Parsed {len(rows)} transactions[/green] from [bold]{pdf.name}[/bold]")
    print(f"Total out: [bold]€{total_out:.2f}[/bold]   Total in: [bold]€{total_in:.2f}[/bold]")

    # Preview table
    table = Table(show_lines=False)
    table.add_column("Date", style="dim")
    table.add_column("Title")
    table.add_column("Out", justify="right")
    table.add_column("In", justify="right")
    table.add_column("Balance", justify="right")

    for r in rows[:limit]:
        table.add_row(
            r["date"] or "",
            (r["title"] or "")[:60],
            f"€{r['money_out']:.2f}" if isinstance(r["money_out"], (int, float)) else "",
            f"€{r['money_in']:.2f}" if isinstance(r["money_in"], (int, float)) else "",
            f"€{r['balance']:.2f}" if isinstance(r["balance"], (int, float)) else "",
        )

    print(table)

    # Export
    if csv_out is not None:
        _export_csv(rows, csv_out)
        print(f"[cyan]Wrote CSV:[/cyan] {csv_out}")


def main():
    app()


if __name__ == "__main__":
    main()

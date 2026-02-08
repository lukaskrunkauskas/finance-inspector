# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Finance Inspector parses Revolut bank statement PDFs and provides spending analysis through both a CLI (Typer) and a web UI (Streamlit). Data is stored in SQLite.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
# Or editable install from pyproject.toml
pip install -e .

# Run Streamlit web app (opens at http://localhost:8501)
streamlit run app.py

# CLI: parse a PDF statement
python -m finance_inspector.main parse data/statements/statement.pdf
python -m finance_inspector.main parse data/statements/statement.pdf --csv output.csv
```

No test suite exists yet.

## Architecture

```
PDF → parsing/revolut_pdf.py → list[Transaction] → storage/sqlite_db.py → ui/pages/main_page.py
```

- **Models** (`models/`): `Transaction` and `Statement` dataclasses. Transactions track booking_date, title, details, money_in/out, balance, currency.
- **Parsing** (`parsing/revolut_pdf.py`): Uses `pdfplumber` to extract text, filters junk lines via regex, splits into transaction blocks by date pattern (`Mon DD, YYYY`), classifies income vs expense by keywords.
- **Storage** (`storage/sqlite_db.py`): Raw SQLite (no ORM). Two tables: `statements` (with PDF blob and SHA256 for deduplication) and `transactions` (FK to statement). Uses `upsert_statement()` with hash-based dedup and `replace_transactions()` for atomic re-import.
- **Web UI** (`ui/pages/main_page.py`): Streamlit app with sidebar for statement selection/upload, metrics row, daily bar chart (Altair), transaction table, and CSV export. Uses `@st.cache_data` for parsing.
- **CLI** (`main.py`): Typer app with `parse` command, Rich table output, optional CSV export.

## Key Details

- Python 3.9+ required
- Currency is EUR-only; amounts parsed via `€` regex pattern
- `streamlit` and `pandas` are in requirements.txt but not in pyproject.toml `[project.dependencies]`
- Database path is `data/app.db`; PDF samples go in `data/statements/`
- Windows development environment (PyCharm)

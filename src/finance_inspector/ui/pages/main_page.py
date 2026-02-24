from __future__ import annotations

import os
import sqlite3
import tempfile

import altair as alt
import pandas as pd
import streamlit as st

from finance_inspector.models.transaction import Transaction  # noqa: F401 — used for type via cache_data
from finance_inspector.parsing.revolut_pdf import parse_revolut_statement_pdf
from finance_inspector.storage.repositories.categories_repo import (
    add_keyword,
    list_categories,
)
from finance_inspector.storage.repositories.statements_repo import (
    list_statements,
    upsert_statement,
)
from finance_inspector.storage.repositories.transactions_repo import (
    categorize_transactions,
    load_transactions,
    replace_transactions,
)

_TX_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# PDF parsing (cached)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _parse_pdf_bytes(pdf_bytes: bytes) -> list[Transaction]:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(pdf_bytes)
        tmp.close()
        return parse_revolut_statement_pdf(tmp.name)
    finally:
        os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# Category-assignment dialog
# ---------------------------------------------------------------------------

@st.dialog("Assign Category")
def _assign_category_dialog(conn: sqlite3.Connection, user_id: int) -> None:
    tx = st.session_state.get("_categorize_tx")
    if tx is None:
        st.rerun()
        return

    title: str = tx["title"]
    statement_id: int = tx["statement_id"]

    st.markdown(f"**Transaction title**")
    st.code(title, language=None)

    categories = list_categories(conn, user_id, include_deleted=False)
    if not categories:
        st.info("No categories yet — create some on the Categories page first.")
        if st.button("Close"):
            del st.session_state["_categorize_tx"]
            st.rerun()
        return

    cat_map = {c.name: c.id for c in categories}
    selected_name = st.selectbox("Category", list(cat_map.keys()))

    keyword = st.text_input(
        "Keyword to match",
        value=title.lower(),
        help="This keyword will be added to the category and used to auto-classify transactions.",
    )

    col_apply, col_cancel = st.columns(2)
    if col_apply.button("Apply", type="primary", width='content'):
        if keyword.strip():
            add_keyword(conn, cat_map[selected_name], keyword.strip())
            categorize_transactions(conn, statement_id)
        del st.session_state["_categorize_tx"]
        st.rerun()

    if col_cancel.button("Cancel", width='content'):
        del st.session_state["_categorize_tx"]
        st.rerun()


# ---------------------------------------------------------------------------
# Transaction table
# ---------------------------------------------------------------------------

def _fmt_eur(val) -> str:
    try:
        return f"€{float(val):,.2f}" if val is not None else "—"
    except (TypeError, ValueError):
        return "—"


def _render_tx_table(statement_id: int, df: pd.DataFrame) -> None:
    total = len(df)
    n_pages = max(1, -(-total // _TX_PAGE_SIZE))  # ceiling division

    # Reset page when statement changes
    if st.session_state.get("_tx_table_stmt") != statement_id:
        st.session_state["_tx_table_stmt"] = statement_id
        st.session_state["_tx_page"] = 0

    page = st.session_state.get("_tx_page", 0)

    # Pagination controls
    if n_pages > 1:
        pc1, pc2, pc3 = st.columns([1, 4, 1])
        if pc1.button("← Prev", disabled=page == 0, width='content'):
            st.session_state["_tx_page"] = page - 1
            st.rerun()
        pc2.markdown(
            f"<div style='text-align:center;padding-top:6px'>Page {page + 1} / {n_pages} &nbsp;·&nbsp; {total} rows</div>",
            unsafe_allow_html=True,
        )
        if pc3.button("Next →", disabled=page == n_pages - 1, width='content'):
            st.session_state["_tx_page"] = page + 1
            st.rerun()

    page_df = df.iloc[page * _TX_PAGE_SIZE: (page + 1) * _TX_PAGE_SIZE]

    # Column layout: Date | Title | 🏷 | Category | Out | In | Balance
    col_widths = [1.6, 5, 0.6, 2, 1.4, 1.4, 1.6]

    # Header
    hcols = st.columns(col_widths)
    for hcol, label in zip(hcols, ["Date", "Title", "", "Category", "Out (€)", "In (€)", "Balance (€)"]):
        hcol.markdown(f"**{label}**")
    st.markdown("<hr style='margin:2px 0 6px 0'>", unsafe_allow_html=True)

    # Rows
    for row_idx, (_, row) in enumerate(page_df.iterrows()):
        global_idx = page * _TX_PAGE_SIZE + row_idx
        rcols = st.columns(col_widths)

        date_val = row["date"]
        date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)

        rcols[0].caption(date_str)
        indicator = "🔴" if pd.isna(row["money_in"]) else "🟢"
        rcols[1].caption(row["title"] + " " + indicator)

        if rcols[2].button("🏷️", key=f"cat_btn_{global_idx}", help="Assign category to this title"):
            st.session_state["_categorize_tx"] = {
                "title": row["title"],
                "statement_id": statement_id,
            }

        rcols[3].caption(row["category"] or "—")
        money_out_label = "" if pd.isna(row["money_out"]) else _fmt_eur(row["money_out"])
        rcols[4].caption(money_out_label)
        money_in_label = "" if pd.isna(row["money_in"]) else _fmt_eur(row["money_in"])
        rcols[5].caption(money_in_label)
        rcols[6].caption(_fmt_eur(row["balance"]))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render_home(conn: sqlite3.Connection, user_id: int) -> None:
    st.title("Finance Inspector")

    saved = list_statements(conn, user_id)

    with st.sidebar:
        st.header("Statements")

        if saved:
            labels = {(s.statement_title or s.filename): s.id for s in saved}
            selected_label = st.selectbox("Load saved", list(labels.keys()))
            selected_statement_id = labels[selected_label]
        else:
            st.caption("No saved statements yet.")
            selected_statement_id = st.session_state.get("selected_statement_id")

        st.divider()
        uploaded = st.file_uploader("Upload a Revolut statement PDF", type=["pdf"])

    if uploaded is not None:
        pdf_bytes = uploaded.getbuffer().tobytes()
        statement = upsert_statement(conn, uploaded.name, pdf_bytes, user_id)
        txs = _parse_pdf_bytes(pdf_bytes)
        replace_transactions(conn, statement.id, txs)
        selected_statement_id = statement.id

    # Persist for the categories page (re-categorize shortcut)
    st.session_state["selected_statement_id"] = selected_statement_id

    # Open dialog if a row button was clicked
    if "_categorize_tx" in st.session_state:
        _assign_category_dialog(conn, user_id)

    if selected_statement_id is None:
        st.info("Upload a PDF or select one from the sidebar.")
        return

    # Load transactions
    txs = load_transactions(conn, selected_statement_id)
    df = pd.DataFrame([
        {
            "date": t.booking_date,
            "title": t.title,
            "details": t.details,
            "money_out": t.money_out,
            "money_in": t.money_in,
            "balance": t.balance,
            "category": t.category,
        }
        for t in txs
    ])

    if df.empty:
        st.warning("No transactions found for this statement.")
        return

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    total_out = float(pd.to_numeric(df["money_out"], errors="coerce").fillna(0).sum())
    total_in = float(pd.to_numeric(df["money_in"], errors="coerce").fillna(0).sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Transactions", f"{len(df)}")
    c2.metric("Total out", f"€{total_out:,.2f}")
    c3.metric("Total in", f"€{total_in:,.2f}")

    # --- Daily chart ---
    st.subheader("Chart: daily money in/out")

    daily = (
        df.assign(
            day=df["date"].dt.date,
            money_out=pd.to_numeric(df["money_out"], errors="coerce").fillna(0),
            money_in=pd.to_numeric(df["money_in"], errors="coerce").fillna(0),
        )
        .groupby("day", as_index=False)[["money_out", "money_in"]]
        .sum()
    )
    daily["day"] = pd.to_datetime(daily["day"])
    daily_long = daily.melt("day", value_vars=["money_out", "money_in"], var_name="type", value_name="amount")
    daily_long["day_str"] = daily_long["day"].dt.strftime("%Y-%m-%d")
    daily_long = daily_long[daily_long["amount"].notna() & (daily_long["amount"] != 0)]

    if daily_long.empty:
        st.caption("No chart data available.")
    else:
        chart = (
            alt.Chart(daily_long)
            .mark_bar()
            .encode(
                x=alt.X("day_str:O", title="Day", sort="ascending"),
                xOffset=alt.XOffset("type:N"),
                y=alt.Y("amount:Q", title="Amount (€)", stack=False),
                color=alt.Color(
                    "type:N",
                    title="",
                    scale=alt.Scale(domain=["money_out", "money_in"], range=["#d62728", "#2ca02c"]),
                ),
                tooltip=[
                    alt.Tooltip("day_str:O", title="Day"),
                    alt.Tooltip("type:N", title="Type"),
                    alt.Tooltip("amount:Q", title="Amount", format=",.2f"),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(chart, width='stretch')

    # --- Pie chart ---
    st.subheader("Spending by category")

    cat_df = df.assign(money_out=pd.to_numeric(df["money_out"], errors="coerce").fillna(0))
    cat_df = cat_df[cat_df["money_out"] > 0].copy()

    if cat_df.empty:
        st.caption("No outgoing transactions to categorize.")
    else:
        cat_df["category"] = cat_df["category"].fillna("Uncategorized")
        by_cat = cat_df.groupby("category", as_index=False)["money_out"].sum()
        by_cat = by_cat.rename(columns={"money_out": "amount"})

        color_map = {c.name: c.color for c in list_categories(conn, user_id)}
        color_map.setdefault("Uncategorized", "#aaaaaa")
        by_cat["color"] = by_cat["category"].map(color_map).fillna("#aaaaaa")

        pie = (
            alt.Chart(by_cat)
            .mark_arc(innerRadius=50)
            .encode(
                theta=alt.Theta("amount:Q"),
                color=alt.Color(
                    "category:N",
                    title="Category",
                    scale=alt.Scale(
                        domain=by_cat["category"].tolist(),
                        range=by_cat["color"].tolist(),
                    ),
                ),
                tooltip=[
                    alt.Tooltip("category:N", title="Category"),
                    alt.Tooltip("amount:Q", title="Amount (€)", format=",.2f"),
                ],
            )
            .properties(height=400)
        )

        col_pie, col_table = st.columns(2)
        with col_pie:
            st.altair_chart(pie, width='stretch')
        with col_table:
            by_cat_display = by_cat[["category", "amount"]].sort_values("amount", ascending=False).copy()
            by_cat_display["amount"] = by_cat_display["amount"].apply(lambda x: f"€{x:,.2f}")
            by_cat_display.columns = ["Category", "Amount"]
            st.dataframe(by_cat_display, width='content', hide_index=True)

    # --- Transaction table ---
    st.subheader("Data")

    _render_tx_table(selected_statement_id, df)

    st.divider()
    st.download_button(
        "Download CSV",
        df.assign(date=df["date"].dt.date.astype(str)).to_csv(index=False).encode("utf-8"),
        file_name="transactions.csv",
        mime="text/csv",
    )

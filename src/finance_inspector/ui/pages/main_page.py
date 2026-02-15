# src/finance_inspector/ui/pages/home.py
from __future__ import annotations

import os
import sqlite3
import tempfile

import altair as alt
import pandas as pd
import streamlit as st

from finance_inspector.parsing.revolut_pdf import parse_revolut_statement_pdf
from finance_inspector.storage.sqlite_db import (
    add_keyword,
    categorize_transactions,
    create_category,
    list_categories,
    list_keywords,
    list_statements,
    load_transactions,
    remove_keyword,
    replace_transactions,
    restore_category,
    soft_delete_category,
    upsert_statement,
)


@st.cache_data(show_spinner=False)
def _parse_pdf_bytes(pdf_bytes: bytes) -> list[dict]:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(pdf_bytes)
        tmp.close()
        txs = parse_revolut_statement_pdf(tmp.name)
    finally:
        os.unlink(tmp.name)
    return txs


def _render_category_manager(conn: sqlite3.Connection, user_id: int, selected_statement_id: int | None) -> None:
    """Render the category management expander."""
    with st.expander("Manage Categories"):
        # --- Create new category ---
        with st.form("new_category_form", clear_on_submit=True):
            new_name = st.text_input("New category name")
            submitted = st.form_submit_button("Create category")
            if submitted and new_name.strip():
                try:
                    create_category(conn, new_name.strip(), user_id)
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Category '{new_name.strip()}' already exists.")

        st.divider()

        # --- List active categories with keywords ---
        categories = list_categories(conn, user_id, include_deleted=False)
        if not categories:
            st.caption("No categories yet. Create one above.")
            return

        for cat in categories:
            st.markdown(f"**{cat.name}**")
            keywords = list_keywords(conn, cat.id)

            # Show existing keywords with remove buttons
            if keywords:
                cols = st.columns([4, 1])
                for kw in keywords:
                    cols[0].code(kw.keyword, language=None)
                    if cols[1].button("X", key=f"rm_kw_{kw.id}"):
                        remove_keyword(conn, kw.id)
                        st.rerun()
            else:
                st.caption("No keywords yet.")

            # Add keyword form
            with st.form(f"add_kw_form_{cat.id}", clear_on_submit=True):
                kw_input = st.text_input("Add keyword", key=f"kw_input_{cat.id}")
                kw_submitted = st.form_submit_button("Add")
                if kw_submitted and kw_input.strip():
                    add_keyword(conn, cat.id, kw_input.strip())
                    st.rerun()

            # Delete category button
            if st.button(f"Delete '{cat.name}'", key=f"del_cat_{cat.id}"):
                soft_delete_category(conn, cat.id, user_id)
                st.rerun()

            st.divider()

        # --- Deleted categories (restore) ---
        deleted = [c for c in list_categories(conn, user_id, include_deleted=True) if c.deleted_at]
        if deleted:
            st.markdown("**Deleted categories**")
            for cat in deleted:
                col1, col2 = st.columns([3, 1])
                col1.text(cat.name)
                if col2.button("Restore", key=f"restore_cat_{cat.id}"):
                    restore_category(conn, cat.id, user_id)
                    st.rerun()

        # --- Re-categorize button ---
        if selected_statement_id is not None:
            st.divider()
            if st.button("Re-categorize current statement"):
                categorize_transactions(conn, selected_statement_id)
                st.rerun()


def render_home(conn: sqlite3.Connection, user_id: int) -> None:
    st.title("Finance Inspector")

    saved = list_statements(conn, user_id)

    with st.sidebar:
        st.header("Statements")

        selected_statement_id: int | None = None
        if saved:
            labels = {
                (s.statement_title or s.filename): s.id
                for s in saved
            }
            selected_statement_id = labels[st.selectbox("Load saved", list(labels.keys()))]
        else:
            st.caption("No saved statements yet.")

        st.divider()
        uploaded = st.file_uploader("Upload a Revolut statement PDF", type=["pdf"])

    if uploaded is not None:
        pdf_bytes = uploaded.getbuffer().tobytes()
        statement = upsert_statement(conn, uploaded.name, pdf_bytes, user_id)
        txs = _parse_pdf_bytes(pdf_bytes)
        replace_transactions(conn, statement.id, txs)
        selected_statement_id = statement.id

    if selected_statement_id is None:
        st.info("Upload a PDF or select one from the sidebar.")
        _render_category_manager(conn, user_id, None)
        return

    # Load transactions from DB — already Transaction objects
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
        _render_category_manager(conn, user_id, selected_statement_id)
        return

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    total_out = float(pd.to_numeric(df["money_out"], errors="coerce").fillna(0).sum())
    total_in = float(pd.to_numeric(df["money_in"], errors="coerce").fillna(0).sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Transactions", f"{len(df)}")
    c2.metric("Total out", f"€{total_out:,.2f}")
    c3.metric("Total in", f"€{total_in:,.2f}")

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

    chart = (
        alt.Chart(daily_long)
        .mark_bar()
        .encode(
            x=alt.X("day_str:O", title="Day", sort="ascending"),
            xOffset=alt.XOffset("type:N"),
            y=alt.Y("amount:Q", title="Amount (€)"),
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

    st.altair_chart(chart, use_container_width=True)

    # --- Pie chart: spending by category ---
    st.subheader("Spending by category")

    cat_df = df.assign(
        money_out=pd.to_numeric(df["money_out"], errors="coerce").fillna(0),
    )
    cat_df = cat_df[cat_df["money_out"] > 0].copy()

    if cat_df.empty:
        st.caption("No outgoing transactions to categorize.")
    else:
        cat_df["category"] = cat_df["category"].fillna("Uncategorized")
        by_cat = cat_df.groupby("category", as_index=False)["money_out"].sum()
        by_cat = by_cat.rename(columns={"money_out": "amount"})

        pie = (
            alt.Chart(by_cat)
            .mark_arc(innerRadius=50)
            .encode(
                theta=alt.Theta("amount:Q"),
                color=alt.Color("category:N", title="Category"),
                tooltip=[
                    alt.Tooltip("category:N", title="Category"),
                    alt.Tooltip("amount:Q", title="Amount (€)", format=",.2f"),
                ],
            )
            .properties(height=400)
        )

        col_pie, col_table = st.columns(2)
        with col_pie:
            st.altair_chart(pie, use_container_width=True)
        with col_table:
            by_cat_display = by_cat.sort_values("amount", ascending=False).copy()
            by_cat_display["amount"] = by_cat_display["amount"].apply(lambda x: f"€{x:,.2f}")
            by_cat_display.columns = ["Category", "Amount"]
            st.dataframe(by_cat_display, use_container_width=True, hide_index=True)

    st.subheader("Data")
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download CSV",
        df.assign(date=df["date"].dt.date.astype(str)).to_csv(index=False).encode("utf-8"),
        file_name="transactions.csv",
        mime="text/csv",
    )

    _render_category_manager(conn, user_id, selected_statement_id)

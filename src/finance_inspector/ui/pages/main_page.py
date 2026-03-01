from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile

import altair as alt
import pandas as pd
import pdfplumber
import streamlit as st

from finance_inspector.models.transaction import Transaction  # noqa: F401 — used for type via cache_data
from finance_inspector.models.user import User
from finance_inspector.parsing.revolut_pdf import parse_revolut_statement_pdf
from finance_inspector.parsing.swedbank_pdf import parse_swedbank_statement_pdf
from finance_inspector.storage.repositories.categories_repo import (
    add_keyword,
    list_categories,
)
from finance_inspector.storage.repositories.statements_repo import (
    get_statement_pdf_bytes,
    list_statements,
    upsert_statement,
)
from finance_inspector.storage.repositories.transactions_repo import (
    categorize_transactions,
    load_transactions,
    replace_transactions,
    set_transaction_irrelevant,
)

_TX_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# PDF parsing (cached)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _parse_pdf_bytes(pdf_bytes: bytes) -> tuple[list[Transaction], str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(pdf_bytes)
        tmp.close()
        with pdfplumber.open(tmp.name) as pdf:
            first_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        if "Swedbank" in first_text or "HABALT22" in first_text:
            return parse_swedbank_statement_pdf(tmp.name), "swedbank"
        return parse_revolut_statement_pdf(tmp.name), "revolut"
    finally:
        os.unlink(tmp.name)


def _make_statement_title(txs: list[Transaction], source: str) -> str:
    source_label = "Revolut" if source == "revolut" else "Swedbank"
    if not txs:
        return f"Unknown ({source_label})"
    max_date = max(t.booking_date for t in txs)
    return f"{max_date.strftime('%Y-%m')} ({source_label})"


def _backfill_statement_labels(conn: sqlite3.Connection, saved: list) -> bool:
    updated = False
    for stmt in saved:
        title = stmt.statement_title or ""
        already_labeled = "(Revolut)" in title or "(Swedbank)" in title
        if stmt.source and already_labeled:
            continue
        pdf_bytes = get_statement_pdf_bytes(conn, stmt.id)
        if not pdf_bytes:
            continue
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            tmp.write(pdf_bytes)
            tmp.close()
            with pdfplumber.open(tmp.name) as pdf:
                first_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        finally:
            os.unlink(tmp.name)
        source = "swedbank" if ("Swedbank" in first_text or "HABALT22" in first_text) else "revolut"
        source_label = "Revolut" if source == "revolut" else "Swedbank"
        txs = load_transactions(conn, stmt.id)
        if txs:
            max_date = max(t.booking_date for t in txs)
            title = f"{max_date.strftime('%Y-%m')} ({source_label})"
        else:
            title = f"Unknown ({source_label})"
        conn.execute(
            "UPDATE statements SET source = ?, statement_title = ? WHERE id = ?",
            (source, title, stmt.id),
        )
        updated = True
    if updated:
        conn.commit()
    return updated


def _default_statement_ids(saved: list, default_view: str) -> list[int]:
    if not saved:
        return []
    if default_view == "revolut_latest":
        for s in saved:
            if s.source == "revolut":
                return [s.id]
        return []
    if default_view == "swedbank_latest":
        for s in saved:
            if s.source == "swedbank":
                return [s.id]
        return []
    seen: set[str] = set()
    ids: list[int] = []
    for s in saved:
        src = s.source or "unknown"
        if src not in seen:
            seen.add(src)
            ids.append(s.id)
    return ids


@st.dialog("Assign Category")
def _assign_category_dialog(conn: sqlite3.Connection, user_id: int) -> None:
    tx = st.session_state.get("_categorize_tx")
    if tx is None:
        st.rerun()
        return

    title: str = tx["title"]
    statement_ids: list[int] = tx["statement_ids"]

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
            for sid in statement_ids:
                categorize_transactions(conn, sid)
        del st.session_state["_categorize_tx"]
        st.rerun()

    if col_cancel.button("Cancel", width='content'):
        del st.session_state["_categorize_tx"]
        st.rerun()


def _fmt_eur(val) -> str:
    try:
        return f"€{float(val):,.2f}" if val is not None else "—"
    except (TypeError, ValueError):
        return "—"


def _render_tx_table(
        conn: sqlite3.Connection,
        statement_ids: list[int],
        df: pd.DataFrame,
        show_source: bool = False,
) -> None:
    total = len(df)
    n_pages = max(1, -(-total // _TX_PAGE_SIZE))  # ceiling division

    # Reset page when statement selection changes
    stmt_key = tuple(sorted(statement_ids))
    if st.session_state.get("_tx_table_stmt") != stmt_key:
        st.session_state["_tx_table_stmt"] = stmt_key
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

    st.markdown(
        """<style>
        div[data-testid='stButton'] {
            display: flex !important;
            justify-content: center !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    col_offset = 1 if show_source else 0

    if show_source:
        col_widths = [1.6, 4, 2, 0.4, 0.4, 2.5, 1.4, 1.4, 1.6]
        headers = ["Date", "Title", "Source", "", "", "Category", "Out (€)", "In (€)", "Balance (€)"]
    else:
        col_widths = [1.6, 5, 0.4, 0.4, 2.5, 1.4, 1.4, 1.6]
        headers = ["Date", "Title", "", "", "Category", "Out (€)", "In (€)", "Balance (€)"]

    # Header
    hcols = st.columns(col_widths)
    for hcol, label in zip(hcols, headers):
        hcol.markdown(f"**{label}**" if label else "")
    st.markdown("<hr style='margin:2px 0 6px 0'>", unsafe_allow_html=True)

    # Inject background highlights for irrelevant rows in one pass before the loop
    irr_css = "".join(
        f'div[data-testid="stHorizontalBlock"]:has(.irr-{page * _TX_PAGE_SIZE + i})'
        f'{{background:rgba(220,50,50,0.1);border-radius:4px}}'
        for i, (_, row) in enumerate(page_df.iterrows())
        if bool(row["irrelevant"])
    )
    if irr_css:
        st.markdown(f"<style>{irr_css}</style>", unsafe_allow_html=True)

    # Rows
    for row_idx, (_, row) in enumerate(page_df.iterrows()):
        global_idx = page * _TX_PAGE_SIZE + row_idx
        is_irrelevant = bool(row["irrelevant"])

        rcols = st.columns(col_widths)

        date_val = row["date"]
        date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)

        if is_irrelevant:
            rcols[0].markdown(
                f'<span class="irr-{global_idx}" hidden></span>'
                f'<span style="font-size:0.875rem;color:rgba(49,51,63,0.6)">{date_str}</span>',
                unsafe_allow_html=True,
            )
        else:
            rcols[0].caption(date_str)

        indicator = "🔴" if pd.isna(row["money_in"]) else "🟢"
        rcols[1].caption(row["title"] + " " + indicator)

        if show_source:
            rcols[2].caption(row.get("source", ""))

        if rcols[2 + col_offset].button("🏷️", key=f"cat_btn_{global_idx}", help="Assign category to this title"):
            st.session_state["_categorize_tx"] = {
                "title": row["title"],
                "statement_ids": statement_ids,
            }

        mark_emoji = "🟢" if is_irrelevant else "🟡"
        mark_help = "Mark as relevant" if is_irrelevant else "Mark as irrelevant"
        if rcols[3 + col_offset].button(mark_emoji, key=f"mark_btn_{global_idx}", help=mark_help):
            set_transaction_irrelevant(conn, int(row["id"]), not is_irrelevant)
            st.rerun()

        rcols[4 + col_offset].caption(row["category"] or "—")
        money_out_label = "" if pd.isna(row["money_out"]) else _fmt_eur(row["money_out"])
        rcols[5 + col_offset].caption(money_out_label)
        money_in_label = "" if pd.isna(row["money_in"]) else _fmt_eur(row["money_in"])
        rcols[6 + col_offset].caption(money_in_label)
        rcols[7 + col_offset].caption(_fmt_eur(row["balance"]))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render_home(conn: sqlite3.Connection, user_id: int, user: User | None = None) -> None:
    st.title("Finance Inspector")

    default_view = (user.default_view or "all_latest") if user else "all_latest"

    saved = list_statements(conn, user_id)
    if _backfill_statement_labels(conn, saved):
        saved = list_statements(conn, user_id)
    stmt_labels = {s.id: (s.statement_title or s.filename) for s in saved}

    # Build label maps before sidebar
    label_to_id = {(s.statement_title or s.filename): s.id for s in saved}
    id_to_label = {v: k for k, v in label_to_id.items()}

    # Apply any pending selection queued by the upload handler on the previous run
    # (must happen before the widget is rendered)
    if "_home_multiselect_pending" in st.session_state:
        st.session_state["_home_multiselect"] = st.session_state.pop("_home_multiselect_pending")
        st.session_state["_home_saved_ids_key"] = tuple(s.id for s in saved)

    # Initialise default selection once per session (reset when statement list changes)
    saved_ids_key = tuple(s.id for s in saved)
    if (
            "_home_multiselect" not in st.session_state
            or st.session_state.get("_home_saved_ids_key") != saved_ids_key
    ):
        st.session_state["_home_saved_ids_key"] = saved_ids_key
        default_ids = _default_statement_ids(saved, default_view)
        st.session_state["_home_multiselect"] = [
            id_to_label[i] for i in default_ids if i in id_to_label
        ]

    with st.sidebar:
        st.header("Statements")

        if saved:
            selected_labels = st.multiselect(
                "Load saved",
                list(label_to_id.keys()),
                key="_home_multiselect",
            )
            selected_statement_ids = [label_to_id[l] for l in selected_labels]
        else:
            st.caption("No saved statements yet.")
            selected_statement_ids = []

        st.divider()
        uploaded = st.file_uploader("Upload a statement PDF", type=["pdf"])

    if uploaded is not None:
        pdf_bytes = uploaded.getbuffer().tobytes()
        upload_hash = hashlib.sha256(pdf_bytes).hexdigest()
        # Only process once per unique file — the widget keeps returning the same
        # file after st.rerun(), which would cause an infinite loop without this guard.
        if st.session_state.get("_last_upload_hash") != upload_hash:
            st.session_state["_last_upload_hash"] = upload_hash
            txs, source = _parse_pdf_bytes(pdf_bytes)
            title = _make_statement_title(txs, source)
            statement = upsert_statement(conn, uploaded.name, pdf_bytes, user_id, source=source, statement_title=title)
            replace_transactions(conn, statement.id, txs)
            # Queue the new label for selection on the next run, then rerun so the
            # widget picks it up before it is instantiated (avoids the post-render write error)
            refreshed = list_statements(conn, user_id)
            stmt_obj = next((s for s in refreshed if s.id == statement.id), None)
            pending_label = (stmt_obj.statement_title or stmt_obj.filename) if stmt_obj else title
            st.session_state["_home_multiselect_pending"] = [pending_label]
            st.rerun()

    # Persist for the categories page
    st.session_state["selected_statement_id"] = selected_statement_ids[0] if selected_statement_ids else None
    st.session_state["selected_statement_ids"] = selected_statement_ids

    # Open dialog if a row button was clicked
    if "_categorize_tx" in st.session_state:
        _assign_category_dialog(conn, user_id)

    if not selected_statement_ids:
        st.info("Upload a PDF or select one from the sidebar.")
        return

    # Load transactions from all selected statements, tagging each with its source label
    show_source = len(selected_statement_ids) > 1
    rows = []
    for sid in selected_statement_ids:
        label = stmt_labels.get(sid, str(sid))
        for t in load_transactions(conn, sid):
            rows.append({
                "date": t.booking_date,
                "title": t.title,
                "details": t.details,
                "money_out": t.money_out,
                "money_in": t.money_in,
                "balance": t.balance,
                "category": t.category,
                "irrelevant": t.irrelevant,
                "id": t.id,
                "source": label,
            })

    df = pd.DataFrame(rows)

    if df.empty:
        st.warning("No transactions found for the selected statement(s).")
        return

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    relevant_df = df[~df["irrelevant"].astype(bool)]

    total_out = float(pd.to_numeric(relevant_df["money_out"], errors="coerce").fillna(0).sum())
    total_in = float(pd.to_numeric(relevant_df["money_in"], errors="coerce").fillna(0).sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Transactions", f"{len(df)}")
    c2.metric("Total out", f"€{total_out:,.2f}")
    c3.metric("Total in", f"€{total_in:,.2f}")

    # --- Daily chart ---
    st.subheader("Chart: daily money in/out")

    daily = (
        relevant_df.assign(
            day=relevant_df["date"].dt.date,
            money_out=pd.to_numeric(relevant_df["money_out"], errors="coerce").fillna(0),
            money_in=pd.to_numeric(relevant_df["money_in"], errors="coerce").fillna(0),
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

    cat_df = relevant_df.assign(money_out=pd.to_numeric(relevant_df["money_out"], errors="coerce").fillna(0))
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

    _render_tx_table(conn, selected_statement_ids, df, show_source=show_source)

    st.divider()
    st.download_button(
        "Download CSV",
        df.assign(date=df["date"].dt.date.astype(str)).to_csv(index=False).encode("utf-8"),
        file_name="transactions.csv",
        mime="text/csv",
    )

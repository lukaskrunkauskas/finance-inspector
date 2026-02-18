from __future__ import annotations

import sqlite3

import streamlit as st

from finance_inspector.storage.sqlite_db import (
    add_keyword,
    categorize_transactions,
    create_category,
    list_categories,
    list_keywords,
    list_statements,
    remove_keyword,
    restore_category,
    soft_delete_category,
)


def render_categories(conn: sqlite3.Connection, user_id: int) -> None:
    st.title("Categories")

    # --- Create new category ---
    with st.form("new_category_form", clear_on_submit=True):
        col_input, col_btn = st.columns([5, 1])
        new_name = col_input.text_input("New category name", label_visibility="collapsed", placeholder="New category name")
        submitted = col_btn.form_submit_button("Create", use_container_width=True)
        if submitted and new_name.strip():
            try:
                create_category(conn, new_name.strip(), user_id)
                st.rerun()
            except sqlite3.IntegrityError:
                st.error(f"Category '{new_name.strip()}' already exists.")

    st.divider()

    # --- Active categories ---
    categories = list_categories(conn, user_id, include_deleted=False)

    if not categories:
        st.caption("No categories yet. Create one above.")
    else:
        for cat in categories:
            with st.expander(f"**{cat.name}**", expanded=False):
                keywords = list_keywords(conn, cat.id)

                if keywords:
                    for kw in keywords:
                        kw_col, rm_col = st.columns([6, 1])
                        kw_col.code(kw.keyword, language=None)
                        if rm_col.button("✕", key=f"rm_kw_{kw.id}", help="Remove keyword"):
                            remove_keyword(conn, kw.id)
                            st.rerun()
                else:
                    st.caption("No keywords yet.")

                with st.form(f"add_kw_form_{cat.id}", clear_on_submit=True):
                    kw_col, add_col = st.columns([5, 1])
                    kw_input = kw_col.text_input(
                        "Add keyword",
                        key=f"kw_input_{cat.id}",
                        label_visibility="collapsed",
                        placeholder="Add keyword…",
                    )
                    kw_submitted = add_col.form_submit_button("Add", use_container_width=True)
                    if kw_submitted and kw_input.strip():
                        add_keyword(conn, cat.id, kw_input.strip())
                        st.rerun()

                if st.button(f"🗑 Delete '{cat.name}'", key=f"del_cat_{cat.id}", type="secondary"):
                    soft_delete_category(conn, cat.id, user_id)
                    st.rerun()

    # --- Deleted categories ---
    deleted = [c for c in list_categories(conn, user_id, include_deleted=True) if c.deleted_at]
    if deleted:
        st.divider()
        with st.expander("Deleted categories", expanded=False):
            for cat in deleted:
                col1, col2 = st.columns([4, 1])
                col1.text(cat.name)
                if col2.button("Restore", key=f"restore_cat_{cat.id}"):
                    restore_category(conn, cat.id, user_id)
                    st.rerun()

    # --- Re-categorize ---
    st.divider()
    st.subheader("Re-categorize a statement")

    saved = list_statements(conn, user_id)
    if not saved:
        st.caption("No statements uploaded yet.")
    else:
        labels = {(s.statement_title or s.filename): s.id for s in saved}

        # Pre-select whatever is already active on the home page
        current_id = st.session_state.get("selected_statement_id")
        default_label = next(
            (lbl for lbl, sid in labels.items() if sid == current_id),
            list(labels.keys())[0],
        )
        selected_label = st.selectbox(
            "Statement",
            list(labels.keys()),
            index=list(labels.keys()).index(default_label),
        )
        if st.button("Re-categorize", type="primary"):
            categorize_transactions(conn, labels[selected_label])
            st.success("Done — categories updated.")
            st.rerun()

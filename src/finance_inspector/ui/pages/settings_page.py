from __future__ import annotations

import sqlite3

import streamlit as st

from finance_inspector.models.user import User
from finance_inspector.storage.repositories.users_repo import update_user_theme

_THEME_OPTIONS = {
    "light": "☀️  Light",
    "dark": "🌙  Dark",
}

DARK_CSS = """
<style>
/* Finance Inspector — dark theme */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: #0e1117 !important;
    color: #c9d1d9 !important;
}
[data-testid="stSidebar"] {
    background-color: #161b22 !important;
    border-right: 1px solid #21262d !important;
}
[data-testid="stHeader"] {
    background-color: rgba(14,17,23,0.95) !important;
}
[data-testid="metric-container"] {
    background-color: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 8px;
}
.stDataFrame, [data-testid="stDataFrame"] {
    background-color: #161b22 !important;
}
textarea, input, select {
    background-color: #21262d !important;
    color: #c9d1d9 !important;
    border-color: #30363d !important;
}
</style>
"""


def apply_theme(theme: str) -> None:
    """Inject CSS for the user's chosen theme.  Call once per render."""
    if theme == "dark":
        st.markdown(DARK_CSS, unsafe_allow_html=True)


def render_settings(conn: sqlite3.Connection, user: User) -> None:
    st.title("Settings")

    st.subheader("Appearance")

    current_theme = user.theme or "light"
    labels = list(_THEME_OPTIONS.values())
    keys = list(_THEME_OPTIONS.keys())

    chosen_label = st.radio(
        "Theme",
        labels,
        index=keys.index(current_theme),
        horizontal=True,
    )
    chosen_key = keys[labels.index(chosen_label)]

    if st.button("Save", type="primary"):
        update_user_theme(conn, user.id, chosen_key)
        st.success("Theme saved.")
        st.rerun()

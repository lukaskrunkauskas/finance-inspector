import streamlit as st

from finance_inspector.storage.sqlite_db import get_conn, init_db
from finance_inspector.ui.pages.main_page import render_home

st.set_page_config(page_title="Finance Inspector", layout="wide")

conn = get_conn()
init_db(conn)

render_home(conn)

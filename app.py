import streamlit as st
import streamlit_authenticator as stauth

from finance_inspector.storage.sqlite_db import (
    get_conn,
    get_all_users_credentials,
    get_user_by_username,
    init_db,
    register_user,
)
from finance_inspector.ui.pages.main_page import render_home

st.set_page_config(page_title="Finance Inspector", layout="wide")


def _save_registered_user(conn, authenticator, username):
    """Extract the newly registered user from authenticator internals and persist to DB."""
    creds = authenticator.authentication_controller.authentication_model.credentials
    user_data = creds["usernames"][username]
    register_user(
        conn,
        username=username,
        email=user_data["email"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        password_hash=user_data["password"],
    )

conn = get_conn()
init_db(conn)

# Build credentials from DB
credentials = get_all_users_credentials(conn)

authenticator = stauth.Authenticate(
    credentials,
    cookie_name="fi_auth",
    cookie_key="finance_inspector_secret_key",
    cookie_expiry_days=30,
)

# Login form
try:
    authenticator.login()
except Exception as e:
    st.error(e)

if st.session_state.get("authentication_status"):
    # Authenticated — resolve user_id
    username = st.session_state["username"]
    user = get_user_by_username(conn, username)
    if user is None:
        st.error("User not found in database.")
        st.stop()

    with st.sidebar:
        st.write(f"Logged in as **{user.first_name} {user.last_name}**")
        authenticator.logout("Logout", "sidebar")

    render_home(conn, user.id)

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect.")

    # Show registration below failed login
    try:
        email, username, name = authenticator.register_user()
        if email:
            _save_registered_user(conn, authenticator, username)
            st.success("User registered successfully. Please log in.")
            st.rerun()
    except Exception as e:
        st.error(e)

else:
    st.warning("Please enter your username and password.")

    # Show registration for new users
    try:
        email, username, name = authenticator.register_user()
        if email:
            _save_registered_user(conn, authenticator, username)
            st.success("User registered successfully. Please log in.")
            st.rerun()
    except Exception as e:
        st.error(e)

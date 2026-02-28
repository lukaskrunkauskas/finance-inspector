import streamlit as st
import streamlit_authenticator as stauth

from finance_inspector.category_configs import SUPPORTED_COUNTRIES
from finance_inspector.storage.connection import get_conn
from finance_inspector.storage.repositories.users_repo import (
    get_all_users_credentials,
    get_user_by_username,
    register_user,
    seed_default_categories,
)
from finance_inspector.storage.schema import init_db
from finance_inspector.ui.pages.categories_page import render_categories
from finance_inspector.ui.pages.main_page import render_home
from finance_inspector.ui.pages.settings_page import apply_theme, render_settings

st.set_page_config(page_title="Finance Inspector", layout="wide")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PAGES = {
    "home": ("🏠", "Home"),
    "categories": ("🏷️", "Categories"),
    "settings": ("⚙️", "Settings"),
}


def _save_registered_user(conn, authenticator, username: str, country: str) -> None:
    creds = authenticator.authentication_controller.authentication_model.credentials
    user_data = creds["usernames"][username]
    user = register_user(
        conn,
        username=username,
        email=user_data["email"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        password_hash=user_data["password"],
        country=country,
    )
    seed_default_categories(conn, user.id, country)


def _render_registration(conn, authenticator) -> None:
    country_options = list(SUPPORTED_COUNTRIES.keys())
    country_labels = [SUPPORTED_COUNTRIES[c] for c in country_options]

    selected_label = st.selectbox(
        "Your country (sets default spending categories)",
        options=country_labels,
        key="reg_country_label",
    )
    selected_country = country_options[country_labels.index(selected_label)]

    try:
        email, username, name = authenticator.register_user()
        if email:
            _save_registered_user(conn, authenticator, username, selected_country)
            st.success("Registered successfully. Please log in.")
            st.rerun()
    except Exception as e:
        st.error(e)


def _sidebar_nav(current_page: str) -> str:
    """Render navigation buttons at the bottom of the sidebar. Returns the active page key."""
    with st.sidebar:
        st.markdown("---")
        cols = st.columns(len(_PAGES))
        for col, (key, (icon, label)) in zip(cols, _PAGES.items()):
            btn_type = "primary" if key == current_page else "secondary"
            if col.button(icon, key=f"nav_{key}", help=label,
                          width='content', type=btn_type):
                st.session_state["page"] = key
                st.rerun()
    return current_page


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

conn = get_conn()
init_db(conn)

credentials = get_all_users_credentials(conn)
authenticator = stauth.Authenticate(
    credentials,
    cookie_name="fi_auth",
    cookie_key="finance_inspector_secret_key_v10",
    cookie_expiry_days=30,
)

# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

try:
    authenticator.login()
except Exception as e:
    if "Signature verification failed" in str(e):
        # Stale cookie from a previous key — delete it and reload cleanly
        try:
            authenticator.cookie_handler.delete_cookie()
        except Exception:
            pass
        st.rerun()
    else:
        st.error(e)

if st.session_state.get("authentication_status"):
    username = st.session_state["username"]
    user = get_user_by_username(conn, username)
    if user is None:
        st.error("User not found in database.")
        st.stop()

    # Apply persisted theme on every render
    apply_theme(user.theme)

    with st.sidebar:
        st.write(f"Logged in as **{user.first_name} {user.last_name}**")
        authenticator.logout("Logout", "sidebar")

    page = st.session_state.get("page", "home")

    # Render the current page (may add its own sidebar content)
    if page == "home":
        render_home(conn, user.id)
    elif page == "categories":
        render_categories(conn, user.id)
    elif page == "settings":
        render_settings(conn, user)

    # Navigation always at the bottom of the sidebar
    _sidebar_nav(page)

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect.")
    _render_registration(conn, authenticator)

else:
    st.warning("Please enter your username and password.")
    _render_registration(conn, authenticator)

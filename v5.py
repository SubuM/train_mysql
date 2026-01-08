import streamlit as st
import requests
import pandas as pd
from streamlit_ace import st_ace
import time

# -----------------------------
# STREAMLIT SECRETS
# -----------------------------
API_BASE = st.secrets["API_BASE"]          # e.g., "http://localhost:8000"
ADMIN_USERNAME = st.secrets["ADMIN_USERNAME"]
ADMIN_TOKEN = st.secrets["ADMIN_TOKEN"]

# -----------------------------
# SESSION STATE
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.password = ""
    st.session_state.admin_token = ""

if "query_log" not in st.session_state:
    st.session_state.query_log = []

if "confirming_delete" not in st.session_state:
    st.session_state.confirming_delete = False

if "pending_delete_user" not in st.session_state:
    st.session_state.pending_delete_user = None

# -----------------------------
# UTILITIES
# -----------------------------
def run_user_query(sql):
    r = requests.post(f"{API_BASE}/execute", json={
        "username": st.session_state.username,
        "password": st.session_state.password,
        "sql": sql
    })
    return r

def run_admin_query(sql, database=None):
    r = requests.post(f"{API_BASE}/admin/execute", json={
        "token": st.session_state.admin_token,
        "sql": sql,
        "database": database or None
    })
    return r, 0  # dummy elapsed time

def display_query_result(columns, rows):
    if rows:
        df = pd.DataFrame(rows, columns=columns)
        st.write(f"**Row count: {len(df)}**")
        st.dataframe(df)
        st.download_button(
            label="Download CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="query_result.csv",
            mime="text/csv"
        )
    else:
        st.info("No results returned")

# -----------------------------
# LOGIN / REGISTER
# -----------------------------
if not st.session_state.logged_in:
    st.title("SQL Lab Login / Register")
    tab1, tab2, tab3 = st.tabs(["User Login","New User","Admin Login"])

    # ----- User Login -----
    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            r = requests.post(f"{API_BASE}/login", json={"username": username,"password": password})
            if r.status_code == 200:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.password = password
                st.rerun()
            else:
                st.error(r.json().get("detail"))

    # ----- New User -----
    with tab2:
        username = st.text_input("New username", key="reg_user")
        password = st.text_input("New password", type="password", key="reg_pass")
        if st.button("Register"):
            r = requests.post(f"{API_BASE}/register", json={"username": username,"password": password})
            if r.status_code == 200:
                st.success("User registered. Please login.")
            else:
                st.error(r.json().get("detail"))

    # ----- Admin Login -----
    with tab3:
        token = st.text_input("Admin token", type="password")
        if st.button("Login as Admin"):
            if token == ADMIN_TOKEN:
                st.session_state.logged_in = True
                st.session_state.username = ADMIN_USERNAME
                st.session_state.admin_token = token
                st.rerun()
            else:
                st.error("Invalid admin token")

# -----------------------------
# MAIN APP AFTER LOGIN
# -----------------------------
else:
    st.title(f"Welcome, {st.session_state.username}")
    if st.session_state.username == ADMIN_USERNAME:
        tabs = st.tabs(["Admin SQL Console","DB Explorer","Manage Users"])
    else:
        tabs = st.tabs(["SQL Editor"])

    # -------------------------
    # USER SQL EDITOR
    # -------------------------
    if st.session_state.username != ADMIN_USERNAME:
        with tabs[0]:
            sql = st_ace(language="sql", theme="dracula", height=200, keybinding="vscode", placeholder="Write SQL here...")
            run_now = st.button("Run Query") or (st.session_state.get("ctrl_enter_pressed", False))
            if run_now and sql.strip():
                r = run_user_query(sql)
                if r.status_code == 200:
                    display_query_result(r.json()["columns"], r.json()["rows"])
                else:
                    st.error(r.json().get("detail"))

    # -------------------------
    # ADMIN SQL CONSOLE
    # -------------------------
    if st.session_state.username == ADMIN_USERNAME:
        # Admin SQL Console
        with tabs[0]:
            st.subheader("🧪 Admin SQL Console")

            # Fetch databases dynamically
            r = requests.get(f"{API_BASE}/admin/list_databases", params={"token": st.session_state.admin_token})
            user_dbs = r.json()["databases"] if r.status_code == 200 else []
            db_selected = st.selectbox("Select target database", [""] + user_dbs, key="admin_sql_console_db")

            sql = st_ace(language="sql", theme="solarized_dark", height=200, keybinding="vscode", placeholder="Write admin SQL here...")
            run_now = st.button("Run Admin Query")
            if run_now and sql.strip():
                r, elapsed = run_admin_query(sql, db_selected)
                if r.status_code == 200:
                    display_query_result(r.json()["columns"], r.json()["rows"])
                else:
                    st.error(r.json().get("detail"))

        # -------------------------
        # ADMIN DB EXPLORER
        # -------------------------
        with tabs[1]:
            st.subheader("🗂️ Database Explorer")
            db_selected = st.selectbox("Select database", [""] + user_dbs, key="admin_db_explorer")
            if db_selected:
                r2 = requests.get(f"{API_BASE}/admin/list_tables", params={"token": st.session_state.admin_token,"database": db_selected})
                tables = r2.json()["tables"] if r2.status_code == 200 else []
                if tables:
                    table_selected = st.selectbox("Select table", tables)
                    if table_selected:
                        sql = f"SELECT * FROM {table_selected} LIMIT 50"
                        r3, _ = run_admin_query(sql, db_selected)
                        if r3.status_code == 200:
                            st.write(f"Preview of table `{table_selected}`:")
                            display_query_result(r3.json()["columns"], r3.json()["rows"])
                        else:
                            st.error(r3.json().get("detail"))
                else:
                    st.info("No tables found")

        # -------------------------
        # MANAGE USERS
        # -------------------------
        with tabs[2]:
            st.subheader("❌ Manage Users")
            r = requests.get(f"{API_BASE}/admin/list_users", params={"token": st.session_state.admin_token})
            users = r.json()["users"] if r.status_code == 200 else []

            if not users:
                st.info("No users found")
            else:
                selected_user = st.selectbox("Select user", users, disabled=st.session_state.confirming_delete)
                username = selected_user

                # Delete user
                if not st.session_state.confirming_delete:
                    if st.button("Delete User"):
                        st.session_state.confirming_delete = True
                        st.session_state.pending_delete_user = username
                        st.rerun()

                if st.session_state.confirming_delete:
                    st.warning(f"⚠️ Permanently delete user **{username}** and their database.")
                    confirm = st.text_input(f"Type `{username}` to confirm")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("CONFIRM DELETE"):
                            if confirm != username:
                                st.error("Confirmation text does not match.")
                            else:
                                r = requests.post(f"{API_BASE}/admin/delete_user", json={"token": st.session_state.admin_token,"username": username})
                                if r.status_code == 200:
                                    st.success("User deleted")
                                    st.session_state.confirming_delete = False
                                    st.session_state.pending_delete_user = None
                                    st.rerun()
                                else:
                                    st.error(r.json().get("detail"))
                    with col2:
                        if st.button("Cancel"):
                            st.session_state.confirming_delete = False
                            st.session_state.pending_delete_user = None
                            st.rerun()

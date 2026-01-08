import streamlit as st
import requests
import time
import pandas as pd
from streamlit_ace import st_ace

# =========================
# CONFIG (STREAMLIT SECRETS)
# =========================
API_BASE = st.secrets["API_BASE"]
ADMIN_USERNAME = st.secrets["ADMIN_USERNAME"]

st.set_page_config(page_title="Personal SQL Lab", layout="wide")

# =========================
# SESSION STATE DEFAULTS
# =========================
defaults = {
    "authenticated": False,
    "role": None,
    "username": None,
    "password": None,
    "admin_token": None,
    "query_log": [],
    "admin_metadata": {"databases": [], "users": []},
    "confirming_delete": False,
    "pending_delete_user": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================
# HELPERS
# =========================
def logout():
    st.session_state.clear()
    st.rerun()

def log_query(sql, status, elapsed=None):
    st.session_state.query_log.append({
        "sql": sql,
        "status": status,
        "time": elapsed
    })

def display_query_result(columns, rows):
    if not rows:
        st.info("Query returned no rows.")
        return
    df = pd.DataFrame(rows, columns=columns)
    st.write(f"Rows: {len(df)}")
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="query_result.csv",
        mime="text/csv"
    )

# =========================
# RUN QUERY FUNCTIONS
# =========================
def run_user_query(sql):
    start = time.time()
    r = requests.post(f"{API_BASE}/execute",
                      json={"username": st.session_state.username,
                            "password": st.session_state.password,
                            "sql": sql})
    elapsed = round(time.time() - start, 3)
    return r, elapsed

def run_admin_query(sql, db_selected):
    start = time.time()
    r = requests.post(f"{API_BASE}/admin/execute",
                      json={"token": st.session_state.admin_token,
                            "sql": sql,
                            "database": db_selected or None})
    elapsed = round(time.time() - start, 3)
    return r, elapsed

# =========================
# SIDEBAR + LOGIN / REGISTER
# =========================
st.sidebar.title("🧪 SQL Lab")
if st.session_state.authenticated:
    st.sidebar.success(f"Logged in as {st.session_state.username}")
    if st.sidebar.button("Logout"):
        logout()
else:
    mode = st.sidebar.radio("Mode", ["User Login", "Register", "Admin Login"])

if not st.session_state.authenticated and mode == "Register":
    st.header("🆕 Register")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Register"):
        r = requests.post(f"{API_BASE}/register", json={"username": u, "password": p})
        if r.status_code == 200:
            st.success("User registered successfully")
        else:
            st.error(r.json().get("detail"))

if not st.session_state.authenticated and mode == "User Login":
    st.header("🔐 User Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        r = requests.post(f"{API_BASE}/login", json={"username": u, "password": p})
        if r.status_code == 200:
            st.session_state.authenticated = True
            st.session_state.username = u
            st.session_state.password = p
            st.session_state.role = "user"
            st.rerun()
        else:
            st.error("Invalid credentials")

if not st.session_state.authenticated and mode == "Admin Login":
    st.header("🛡️ Admin Login")
    token = st.text_input("Admin Token", type="password")
    if st.button("Login as Admin"):
        r = requests.post(f"{API_BASE}/admin/login", params={"token": token})
        if r.status_code == 200:
            st.session_state.authenticated = True
            st.session_state.username = ADMIN_USERNAME
            st.session_state.role = "admin"
            st.session_state.admin_token = token
            st.rerun()
        else:
            st.error("Invalid admin token")

# =========================
# USER SQL CONSOLE
# =========================
if st.session_state.authenticated and st.session_state.role == "user":
    st.header(f"🧪 SQL Console — {st.session_state.username}")
    sql = st_ace(language="sql", theme="dracula", height=200, auto_update=True, keybinding="vscode")
    can_run = bool(sql and sql.strip())
    if st.button("Run Query", disabled=not can_run):
        r, elapsed = run_user_query(sql)
        if r.status_code == 200:
            log_query(sql, "success", elapsed)
            st.success(f"Executed in {elapsed}s")
            display_query_result(r.json()["columns"], r.json()["rows"])
        else:
            log_query(sql, "error", elapsed)
            st.error(r.json().get("detail"))

    with st.expander("📜 Query Log"):
        for q in reversed(st.session_state.query_log):
            icon = "✅" if q["status"] == "success" else "❌"
            st.markdown(f"{icon} `{q['sql']}` ({q['time']}s)")

# =========================
# ADMIN PANEL
# =========================
if st.session_state.authenticated and st.session_state.role == "admin":
    st.header("👑 Admin Console")

    if st.button("🔄 Refresh Metadata"):
        fetch_admin_metadata()
        st.success("Metadata refreshed")

    tabs = st.tabs(["SQL Console", "DB Explorer", "Manage Users"])

    # -------------------------
    # ADMIN SQL CONSOLE
    # -------------------------
    with tabs[0]:
        st.subheader("🧪 Admin SQL Console")

        # Fetch dynamic databases
        r = requests.get(f"{API_BASE}/admin/list_databases", params={"token": st.session_state.admin_token})
        if r.status_code == 200:
            user_dbs = r.json()["databases"]
        else:
            st.error("Failed to fetch databases")
            user_dbs = []

        db_selected = st.selectbox("Select target database", [""] + user_dbs, key="admin_sql_console_db")

        sql = st_ace(
            language="sql",
            theme="solarized_dark",
            height=200,
            auto_update=True,
            keybinding="vscode",
            placeholder="Write admin SQL here..."
        )

        can_run = bool(sql and sql.strip())
        if st.button("Run Admin Query", disabled=not can_run):
            r, elapsed = run_admin_query(sql, db_selected)
            log_query(
                f"[DB={db_selected or 'NONE'}] {sql}",
                "success" if r.status_code == 200 else "error",
                elapsed
            )
            if r.status_code == 200:
                st.success(f"Executed in {elapsed}s")
                display_query_result(r.json()["columns"], r.json()["rows"])
            else:
                st.error(r.json().get("detail"))

    # -------------------------
    # DB EXPLORER
    # -------------------------
    with tabs[1]:
        st.subheader("🗂️ Database Explorer")
        # Fetch dynamic databases
        r = requests.get(f"{API_BASE}/admin/list_databases", params={"token": st.session_state.admin_token})
        if r.status_code == 200:
            user_dbs = r.json()["databases"]
        else:
            st.error("Failed to fetch databases")
            user_dbs = []

        db_selected = st.selectbox("Select database", [""] + user_dbs, key="admin_db_explorer")
        
        if db_selected:
            # Fetch tables dynamically for selected DB
            r2 = requests.get(f"{API_BASE}/admin/list_tables",
                            params={"token": st.session_state.admin_token, "database": db_selected})
            if r2.status_code == 200:
                tables = r2.json()["tables"]
                if tables:
                    table_selected = st.selectbox("Select table", tables)
                    if table_selected:
                        # Optionally, show table preview
                        sql = f"SELECT * FROM {table_selected} LIMIT 50"
                        r3, _ = run_admin_query(sql, db_selected)
                        if r3.status_code == 200:
                            st.write(f"Preview of table `{table_selected}`:")
                            display_query_result(r3.json()["columns"], r3.json()["rows"])
                        else:
                            st.error(r3.json().get("detail"))
                else:
                    st.info("No tables found in this database")
            else:
                st.error("Failed to fetch tables")


    # -------------------------
    # MANAGE USERS
    # -------------------------
    with tabs[2]:
        st.subheader("❌ Manage Users")

        # Fetch dynamic user list
        r = requests.get(f"{API_BASE}/admin/list_users", params={"token": st.session_state.admin_token})
        if r.status_code == 200:
            users = r.json().get("users", [])
        else:
            st.error("Failed to fetch users")
            users = []

        if not users:
            st.info("No users found.")
        else:
            selected_user = st.selectbox(
                "Select user",
                users,
                disabled=st.session_state.confirming_delete
            )
            username = selected_user

            # DELETE USER
            if not st.session_state.confirming_delete:
                if st.button("Delete User", type="primary"):
                    st.session_state.confirming_delete = True
                    st.session_state.pending_delete_user = username
                    st.rerun()

            if st.session_state.confirming_delete:
                st.warning(
                    f"⚠️ Permanently delete user **{username}** and their database."
                )
                confirm = st.text_input(f"Type `{username}` to confirm")

                col1, col2 = st.columns(2)

                with col1:
                    if st.button("CONFIRM DELETE", type="primary"):
                        if confirm != username:
                            st.error("Confirmation text does not match.")
                        else:
                            r = requests.post(
                                f"{API_BASE}/admin/delete_user",
                                json={
                                    "token": st.session_state.admin_token,
                                    "username": username
                                }
                            )
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

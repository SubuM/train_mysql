import streamlit as st
import requests
import time
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


def is_destructive(sql):
    keywords = ["drop", "truncate", "delete"]
    return any(k in sql.lower() for k in keywords)


def fetch_admin_metadata():
    r = requests.get(
        f"{API_BASE}/admin/list",
        params={"token": st.session_state.admin_token}
    )
    if r.status_code == 200:
        st.session_state.admin_metadata = r.json()


# =========================
# SIDEBAR
# =========================
st.sidebar.title("🧪 SQL Lab")

if st.session_state.authenticated:
    st.sidebar.success(f"Logged in as {st.session_state.username}")
    if st.sidebar.button("Logout"):
        logout()
else:
    mode = st.sidebar.radio(
        "Choose Mode",
        ["User Login", "Register", "Admin Login"]
    )

# =========================
# REGISTER
# =========================
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

# =========================
# USER LOGIN
# =========================
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

# =========================
# ADMIN LOGIN
# =========================
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
            fetch_admin_metadata()
            st.rerun()
        else:
            st.error("Invalid admin token")

# =========================
# USER SQL CONSOLE
# =========================
if st.session_state.authenticated and st.session_state.role == "user":
    st.header(f"🧪 SQL Console — {st.session_state.username}")

    sql = st_ace(
            language="sql", 
            theme="dracula",
            height=200,
            keybinding="vscode",
            auto_update=True
        )
    can_run = bool(sql and sql.strip())

    if is_destructive(sql):
        st.warning("⚠️ This query modifies or deletes data.")
        confirm = st.checkbox("I understand the risk")
        if not confirm:
            can_run = False

    if st.button("Run Query", disabled=not can_run):
        start = time.time()
        r = requests.post(
            f"{API_BASE}/execute",
            json={
                "username": st.session_state.username,
                "password": st.session_state.password,
                "sql": sql
            }
        )
        elapsed = round(time.time() - start, 3)

        if r.status_code == 200:
            log_query(sql, "success", elapsed)
            st.success(f"Executed in {elapsed}s")
            st.write(r.json()["result"])
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
        data = st.session_state.admin_metadata
        user_dbs = sorted(db for db in data["databases"] if db.endswith("_db"))

        protected_dbs = {"mysql", "information_schema", "performance_schema", "sys"}

        db_selected = st.selectbox(
            "Select target database",
            [""] + user_dbs
        )

        if db_selected in protected_dbs:
            st.error("🚫 System databases are not allowed.")
            st.stop()

        sql = st_ace(
            language="sql", 
            theme="solarized_dark",
            height=200,
            keybinding="vscode",
            auto_update=True
        )
        can_run = bool(sql and sql.strip())

        if st.button("Run Admin Query", disabled=not can_run):
            start = time.time()
            r = requests.post(
                f"{API_BASE}/admin/execute",
                json={
                    "token": st.session_state.admin_token,
                    "sql": sql,
                    "database": db_selected or None
                }
            )
            elapsed = round(time.time() - start, 3)

            log_query(f"[DB={db_selected or 'NONE'}] {sql}",
                      "success" if r.status_code == 200 else "error",
                      elapsed)

            if r.status_code == 200:
                st.success(f"Executed in {elapsed}s")
                st.write(r.json()["result"])
            else:
                st.error(r.json().get("detail"))

    # -------------------------
    # DB EXPLORER
    # -------------------------
    with tabs[1]:
        st.subheader("🗂️ Database Explorer")

        db = st.selectbox("Select database", user_dbs)
        if db:
            r = requests.get(
                f"{API_BASE}/admin/list_tables",
                params={
                    "token": st.session_state.admin_token,
                    "database": db
                }
            )
            if r.status_code == 200:
                st.write("Tables:", r.json()["tables"])
            else:
                st.error(r.json().get("detail"))

    # -------------------------
    # MANAGE USERS
    # -------------------------
    with tabs[2]:
        st.subheader("❌ Delete User")

        users = sorted(
            u for u in st.session_state.admin_metadata["users"]
            if u.startswith("user_")
        )

        if not users:
            st.info("No users found.")
        else:
            selected_user = st.selectbox(
                "Select user",
                users,
                disabled=st.session_state.confirming_delete
            )

            username = selected_user.replace("user_", "")

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
                                fetch_admin_metadata()
                                st.rerun()
                            else:
                                st.error(r.json().get("detail"))

                with col2:
                    if st.button("Cancel"):
                        st.session_state.confirming_delete = False
                        st.session_state.pending_delete_user = None
                        st.rerun()

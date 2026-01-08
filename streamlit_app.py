import streamlit as st
import requests
from streamlit_ace import st_ace

# =========================
# CONFIG (SECRETS)
# =========================
API_BASE = st.secrets["API_BASE"]
ADMIN_USERNAME = st.secrets["ADMIN_USERNAME"]

st.set_page_config(page_title="SQL Lab", layout="wide")

def fetch_admin_metadata():
    r = requests.get(
        f"{API_BASE}/admin/list",
        params={"token": st.session_state.admin_token}
    )
    if r.status_code == 200:
        st.session_state.admin_metadata = r.json()
    else:
        st.session_state.admin_metadata = {"databases": [], "users": []}

# =========================
# SESSION STATE
# =========================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.query_log = []

if "admin_metadata" not in st.session_state:
    st.session_state.admin_metadata = {"databases": [], "users": []}


def logout():
    st.session_state.clear()
    st.rerun()


def log_query(sql):
    st.session_state.query_log.append(sql)


# =========================
# SIDEBAR
# =========================
st.sidebar.title("SQL Lab")
if st.session_state.authenticated:
    st.sidebar.success(f"Logged in as {st.session_state.username}")
    if st.sidebar.button("Logout"):
        logout()
else:
    mode = st.sidebar.radio("Mode", ["User Login", "Register", "Admin Login"])

# =========================
# USER REGISTER
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
    sql = st_ace(language="sql", height=200)
    if st.button("Run Query"):
        payload = {
            "username": st.session_state.username,
            "password": st.session_state.password,
            "sql": sql
        }
        r = requests.post(f"{API_BASE}/execute", json=payload)
        log_query(sql)
        if r.status_code == 200:
            st.write(r.json()["result"])
        else:
            st.error(r.json().get("detail"))

    st.subheader("📜 Query Log")
    for q in st.session_state.query_log:
        st.code(q, language="sql")

# =========================
# ADMIN PANEL
# =========================
if st.session_state.authenticated and st.session_state.role == "admin":
    st.header("👑 Admin Console")

    tabs = st.tabs(["SQL Console", "DB Explorer", "Manage Users"])

    # ---- SQL Console
    with tabs[0]:
        st.subheader("🖥️ SQL Console")
        sql = st_ace(language="sql", height=200)
        db_selected = st.selectbox("Select target database (optional)", [""] + st.session_state.admin_metadata["databases"])

        if st.button("Run Admin Query"):
            payload = {
                "token": st.session_state.admin_token,
                "sql": sql,
                "database": db_selected if db_selected else None
            }
            r = requests.post(f"{API_BASE}/admin/execute", json=payload)
            log_query(f"[DB={db_selected}] {sql}")
            if r.status_code == 200:
                st.write(r.json()["result"])
            else:
                st.error(r.json().get("detail"))

        st.subheader("📜 Admin Query Log")
        for q in st.session_state.query_log:
            st.code(q, language="sql")

    # ---- DB Explorer
    with tabs[1]:
        st.subheader("🗂️ DB Explorer")

        if st.button("Refresh Metadata"):
            fetch_admin_metadata()

        data = st.session_state.admin_metadata

        st.write("Databases:", data["databases"])
        st.write("Users:", data["users"])

        db_select = st.selectbox(
            "Select database to view tables",
            data["databases"]
        )

        if db_select:
            r2 = requests.get(
                f"{API_BASE}/admin/list_tables",
                params={
                    "token": st.session_state.admin_token,
                    "database": db_select
                }
            )
            if r2.status_code == 200:
                st.write("Tables:", r2.json()["tables"])


    # ---- Manage Users
    with tabs[2]:
        st.subheader("❌ Delete User")
        r = requests.get(f"{API_BASE}/admin/list", params={"token": st.session_state.admin_token})
        if r.status_code == 200:
            users = [u for u in r.json()["users"] if u.startswith("user_")]
            del_user = st.selectbox("Select user to delete", users)
            if st.button("Delete User"):
                username = del_user.replace("user_", "")
                r = requests.post(f"{API_BASE}/admin/delete_user", json={"token": st.session_state.admin_token, "username": username})
                if r.status_code == 200:
                    st.success(f"User {username} deleted")
                else:
                    st.error(r.json().get("detail"))

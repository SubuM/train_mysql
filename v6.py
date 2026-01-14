import streamlit as st
from streamlit_ace import st_ace
import pandas as pd
import requests

# ------------------------------------------------------------------
# 1. CONFIGURATION & SECRETS
# ------------------------------------------------------------------
st.set_page_config(page_title="MySQL Lab", page_icon="🐬", layout="wide")

# Verify Secrets exist to prevent runtime crashes
required_secrets = ["AWS_IP", "ADMIN_TOKEN", "ROOT_PASSWORD"]
missing_secrets = [s for s in required_secrets if s not in st.secrets]
if missing_secrets:
    st.error(f"🚨 Missing Secrets: {', '.join(missing_secrets)}")
    st.stop()

# Construct API URL
API_URL = f"http://{st.secrets['AWS_IP']}:8000"
ADMIN_TOKEN = st.secrets["ADMIN_TOKEN"]
ROOT_PASSWORD = st.secrets["ROOT_PASSWORD"]

# ------------------------------------------------------------------
# 2. API HELPERS
# ------------------------------------------------------------------
def api_register(username, password):
    """Registers a new user via the backend."""
    try:
        # Backend expects: { "username": "...", "password": "..." }
        res = requests.post(
            f"{API_URL}/register", 
            json={"username": username, "password": password}, 
            timeout=5
        )
        if res.status_code == 200:
            return {"status": "success", "message": "User created!"}
        else:
            # Parse FastAPI error details
            try:
                err = res.json().get("detail", "Unknown Error")
            except:
                err = res.text
            return {"status": "error", "message": err}
    except Exception as e:
        return {"status": "error", "message": f"Connection Failed: {e}"}

def api_execute(username, password, sql):
    """Executes SQL. Backend handles authentication."""
    try:
        # Backend expects: { "username": "...", "password": "...", "sql": "..." }
        payload = {"username": username, "password": password, "sql": sql}
        
        res = requests.post(f"{API_URL}/execute", json=payload, timeout=10)
        
        if res.status_code == 200:
            return res.json() # Returns {status, columns, rows} or {status, message}
        elif res.status_code == 401:
             return {"status": "error", "message": "🔐 Authentication Failed"}
        else:
            try:
                err = res.json().get("detail", "SQL Error")
            except:
                err = res.text
            return {"status": "error", "message": err}
    except Exception as e:
        return {"status": "error", "message": f"Connection Failed: {e}"}

def api_admin_list_users():
    """Fetches list of databases/users for the Admin dashboard."""
    try:
        res = requests.get(f"{API_URL}/admin/users?token={ADMIN_TOKEN}", timeout=5)
        if res.status_code == 200:
            return res.json().get("users", [])
        return []
    except:
        return []

def api_admin_delete(username):
    """Deletes a user."""
    try:
        res = requests.post(
            f"{API_URL}/admin/delete_user", 
            json={"token": ADMIN_TOKEN, "username": username},
            timeout=5
        )
        return res.status_code == 200
    except:
        return False

# ------------------------------------------------------------------
# 3. SESSION STATE
# ------------------------------------------------------------------
if "username" not in st.session_state: st.session_state["username"] = None
if "password" not in st.session_state: st.session_state["password"] = None
if "role" not in st.session_state: st.session_state["role"] = None # 'user' or 'admin'
if "query_history" not in st.session_state: st.session_state["query_history"] = []

# ------------------------------------------------------------------
# 4. SIDEBAR: AUTHENTICATION
# ------------------------------------------------------------------
if st.session_state["role"] is None:
    st.sidebar.title("🔐 Login")
    option = st.sidebar.radio("Select Mode", ["User Login", "New User Registration", "Admin Login"])

    # --- REGISTER ---
    if option == "New User Registration":
        st.sidebar.subheader("Create Account")
        new_u = st.sidebar.text_input("Username")
        new_p = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Register"):
            if new_u and new_p:
                with st.sidebar.status("Creating database..."):
                    res = api_register(new_u, new_p)
                if res["status"] == "success":
                    st.sidebar.success(res["message"])
                else:
                    st.sidebar.error(res["message"])
            else:
                st.sidebar.warning("Fields cannot be empty")

    # --- USER LOGIN ---
    elif option == "User Login":
        st.sidebar.subheader("Access Lab")
        u = st.sidebar.text_input("Username")
        p = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            # Validate credentials by running a lightweight query (SELECT 1)
            check = api_execute(u, p, "SELECT 1")
            if check.get("status") == "success":
                st.session_state["username"] = u
                st.session_state["password"] = p
                st.session_state["role"] = "user"
                st.rerun()
            else:
                st.sidebar.error(check.get("message", "Login Failed"))

    # --- ADMIN LOGIN ---
    elif option == "Admin Login":
        st.sidebar.subheader("Admin Access")
        token = st.sidebar.text_input("Admin Token", type="password")
        if st.sidebar.button("Enter"):
            if token == ADMIN_TOKEN:
                st.session_state["username"] = "root" # Admin acts as Root
                st.session_state["password"] = ROOT_PASSWORD
                st.session_state["role"] = "admin"
                st.rerun()
            else:
                st.sidebar.error("Invalid Token")

# ------------------------------------------------------------------
# 5. MAIN DASHBOARD
# ------------------------------------------------------------------
else:
    # Header & Logout
    col1, col2 = st.columns([6, 1])
    with col1:
        if st.session_state["role"] == "admin":
            st.title("🛡️ Admin Dashboard")
        else:
            st.title(f"🐬 Workspace: db_{st.session_state['username']}")
    with col2:
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

    # --- ADMIN VIEW ---
    if st.session_state["role"] == "admin":
        tab1, tab2 = st.tabs(["👥 User Management", "💻 Global SQL Console"])

        # Tab 1: Manage Users
        with tab1:
            users = api_admin_list_users()
            if users:
                st.write(f"**Active Users ({len(users)}):**")
                df_users = pd.DataFrame(users, columns=["Username"])
                st.dataframe(df_users, use_container_width=True)

                st.write("---")
                col_del, col_btn = st.columns([3, 1])
                user_to_del = col_del.selectbox("Select User to Delete", users)
                if col_btn.button("🗑️ Delete User", type="primary"):
                    if api_admin_delete(user_to_del):
                        st.success(f"User '{user_to_del}' and their database deleted.")
                        st.rerun()
                    else:
                        st.error("Failed to delete user.")
            else:
                st.info("No users found.")

        # Tab 2: Admin SQL
        with tab2:
            st.info("💡 As Admin (Root), you must use fully qualified names to access user tables. Example: `SELECT * FROM db_alice.users`")
            
            # Helper to insert table template
            users = api_admin_list_users()
            target_user = st.selectbox("Quick Context Helper", ["Select a user..."] + users)
            if target_user != "Select a user...":
                st.caption(f"Table prefix: `db_{target_user}.`")

            sql_code = st_ace(language="sql", theme="monokai", height=250, key="admin_ace", placeholder="SHOW DATABASES;")
            
            if st.button("Run Admin Query"):
                # Note: Admin uses ROOT_PASSWORD via session_state
                res = api_execute(st.session_state["username"], st.session_state["password"], sql_code)
                
                if res.get("status") == "success":
                    if "rows" in res:
                        df = pd.DataFrame(res["rows"], columns=res["columns"])
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.success(res.get("message"))
                else:
                    st.error(res.get("message"))

    # --- USER VIEW ---
    else:
        # Standard User Dashboard
        col_editor, col_history = st.columns([2, 1])

        with col_editor:
            st.subheader("SQL Editor")
            sql_code = st_ace(
                language="sql", 
                theme="monokai", 
                height=300, 
                placeholder="CREATE TABLE demo (id INT);\nINSERT INTO demo VALUES (1);\nSELECT * FROM demo;"
            )
            
            if st.button("Run Query", type="primary"):
                # 1. Log to history
                st.session_state["query_history"].append(sql_code)
                
                # 2. Execute
                with st.spinner("Executing..."):
                    res = api_execute(st.session_state["username"], st.session_state["password"], sql_code)
                
                # 3. Display
                if res.get("status") == "success":
                    if "rows" in res:
                        # It's a table result
                        df = pd.DataFrame(res["rows"], columns=res["columns"])
                        st.dataframe(df, use_container_width=True)
                        st.caption(f"Returned {len(df)} rows")
                    else:
                        # It's a message (Update/Insert/Delete)
                        st.success(res.get("message"))
                else:
                    st.error(res.get("message"))

        with col_history:
            st.subheader("Session Log")
            if st.session_state["query_history"]:
                for i, q in enumerate(reversed(st.session_state["query_history"])):
                    with st.expander(f"Query {len(st.session_state['query_history']) - i}"):
                        st.code(q, language="sql")
            else:
                st.info("No queries yet.")
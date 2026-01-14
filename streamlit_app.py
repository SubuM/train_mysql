import streamlit as st
from streamlit_ace import st_ace
import pandas as pd
import requests

# -------------------------------
# Config & Secrets
# -------------------------------
st.set_page_config(page_title="SQL Lab", page_icon="🐬", layout="wide")

if 'AWS_IP' not in st.secrets:
    st.error("🚨 Missing 'AWS_IP' in Secrets!")
    st.stop()

# URL Safety Fix
aws_ip = st.secrets['AWS_IP'].strip()
if aws_ip.startswith("http://"): aws_ip = aws_ip.replace("http://", "")
if aws_ip.startswith("https://"): aws_ip = aws_ip.replace("https://", "")
    
API_URL = f"http://{aws_ip}:8000"

ADMIN_TOKEN = st.secrets.get("ADMIN_TOKEN", "supersecretadmintoken")
ROOT_PASSWORD = st.secrets.get("ROOT_PASSWORD", "super_root_password")

# -------------------------------
# API Helpers
# -------------------------------
def api_register(username, password):
    try:
        res = requests.post(f"{API_URL}/register", json={"username": username, "password": password}, timeout=5)
        if res.status_code == 200:
            return {"status": "success", "message": "User registered successfully!"}
        else:
            try: err = res.json().get("detail", res.text)
            except: err = res.text
            return {"status": "error", "message": err}
    except Exception as e:
        return {"status": "error", "message": f"Connection Error: {e}"}

def api_execute(username, password, sql):
    try:
        payload = {"username": username, "password": password, "sql": sql}
        res = requests.post(f"{API_URL}/execute", json=payload, timeout=10)
        
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            return {"status": "error", "message": "Invalid Credentials"}
        else:
            try: err = res.json().get("detail", res.text)
            except: err = res.text
            return {"status": "error", "message": err}
    except Exception as e:
        return {"status": "error", "message": f"Connection Error: {e}"}

def api_admin_list_users():
    try:
        res = requests.get(f"{API_URL}/admin/users?token={ADMIN_TOKEN}", timeout=5)
        return res.json().get("users", []) if res.status_code == 200 else []
    except:
        return []

def api_admin_delete(username):
    try:
        res = requests.post(f"{API_URL}/admin/delete_user", json={"token": ADMIN_TOKEN, "username": username}, timeout=5)
        return res.status_code == 200
    except:
        return False

# -------------------------------
# Session State
# -------------------------------
if "username" not in st.session_state: st.session_state["username"] = None
if "password" not in st.session_state: st.session_state["password"] = None
if "token" not in st.session_state: st.session_state["token"] = None
if "query_history" not in st.session_state: st.session_state["query_history"] = []
if "last_executed_sql" not in st.session_state: st.session_state["last_executed_sql"] = ""

# -------------------------------
# Sidebar: Auth
# -------------------------------
if st.session_state["token"] is None:
    st.sidebar.subheader("Authentication")
    login_option = st.sidebar.radio("Select Option", ["User Login", "New User Registration", "Admin Login"])

    if login_option == "User Login":
        username = st.sidebar.text_input("Username", key="login_user")
        password = st.sidebar.text_input("Password", type="password", key="login_pass")
        if st.sidebar.button("Login"):
            check = api_execute(username, password, "SELECT 1")
            if check.get("status") == "success":
                st.session_state["username"] = username
                st.session_state["password"] = password
                st.session_state["token"] = True
                st.success(f"Logged in as {username}")
                st.rerun()
            else:
                st.error("Invalid credentials")

    elif login_option == "New User Registration":
        new_user = st.sidebar.text_input("Username", key="reg_user")
        new_password = st.sidebar.text_input("Password", type="password", key="reg_pass")
        if st.sidebar.button("Register"):
            result = api_register(new_user, new_password)
            if result["status"] == "error":
                st.error(result["message"])
            else:
                st.success(result["message"])
                st.info("You can now login from the sidebar.")

    elif login_option == "Admin Login":
        admin_token = st.sidebar.text_input("Admin Token", type="password", key="admin_token")
        if st.sidebar.button("Admin Login"):
            if admin_token == ADMIN_TOKEN:
                st.session_state["username"] = "admin"
                st.session_state["password"] = ROOT_PASSWORD
                st.session_state["token"] = True
                st.success("Admin logged in successfully!")
                st.rerun()
            else:
                st.error("Invalid admin token")

# -------------------------------
# Main Dashboard
# -------------------------------
if st.session_state["token"]:
    username = st.session_state["username"]
    st.sidebar.success(f"Logged in as {username}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    # --- ADMIN DASHBOARD ---
    if username == "admin":
        st.subheader("Admin Dashboard")
        tabs = st.tabs(["List Users", "Manage Users", "SQL Console"])
        
        with tabs[0]:
            st.write("All users:")
            users = api_admin_list_users()
            st.write(users)

        with tabs[1]:
            st.write("Delete a user:")
            users = api_admin_list_users()
            if users:
                user_to_delete = st.selectbox("Select user", users)
                confirm = st.checkbox(f"Confirm delete `{user_to_delete}`")
                if st.button("Delete User"):
                    if confirm:
                        if api_admin_delete(user_to_delete):
                            st.success(f"User `{user_to_delete}` deleted successfully!")
                            st.rerun()
                        else: st.error("Error deleting user.")
                    else: st.warning("Please confirm deletion first.")
            else: st.info("No users found.")

        with tabs[2]:
            st.write("Execute SQL on admin database:")
            st.caption("Tip: Use `db_username.table` to access user data.")
            
            ace_themes = ["dracula", "monokai", "github", "tomorrow", "twilight", "xcode", "solarized_dark", "solarized_light", "terminal"]
            selected_theme = st.selectbox("Select ACE Editor Theme", ace_themes)
            
            sql_query = st_ace(
                value="", language="sql", theme=selected_theme, height=300,
                key="admin_sql_editor", font_size=14, tab_size=4, show_gutter=True, wrap=True,
                placeholder="SHOW DATABASES;"
            )
            
            if sql_query.strip() and sql_query != st.session_state.get("last_executed_sql"):
                st.session_state["last_executed_sql"] = sql_query
                # 1. Add to History (FIXED)
                st.session_state["query_history"].append(sql_query)
                
                # 2. Run
                result = api_execute(username, st.session_state["password"], sql_query)
                
                if result.get("status") == "success":
                    if "rows" in result:
                        df = pd.DataFrame(result["rows"], columns=result["columns"])
                        st.dataframe(df, use_container_width=True)
                    else: st.success(result.get("message"))
                else: st.error(result.get("message"))
            
            # 3. Show History (FIXED)
            if st.session_state.get("query_history"):
                st.subheader("Query History")
                for i, q in enumerate(reversed(st.session_state["query_history"]), 1):
                    st.code(f"{i}: {q}", language="sql")

    # --- USER DASHBOARD ---
    else:
        st.subheader(f"User Dashboard - {username}")
        st.write(f"Hello {username}! Practice SQL below:")

        ace_themes = ["dracula", "monokai", "github", "tomorrow", "twilight", "xcode", "solarized_dark", "solarized_light", "terminal"]
        selected_theme = st.selectbox("Select ACE Editor Theme", ace_themes)
        
        sql_query = st_ace(
            value="", language="sql", theme=selected_theme, height=300,
            key="sql_editor", font_size=14, tab_size=4, show_gutter=True, wrap=True,
            placeholder="Write your SQL query here..."
        )

        if sql_query.strip() and sql_query != st.session_state.get("last_executed_sql"):
            st.session_state["last_executed_sql"] = sql_query
            st.session_state["query_history"].append(sql_query)
            
            result = api_execute(username, st.session_state["password"], sql_query)

            if result.get("status") == "success":
                if "rows" in result:
                    df = pd.DataFrame(result["rows"], columns=result["columns"])
                    st.dataframe(df, use_container_width=True)
                else: st.success(result.get("message"))
            else: st.error(result.get("message"))

        if st.session_state.get("query_history"):
            st.subheader("Query History")
            for i, q in enumerate(reversed(st.session_state["query_history"]), 1):
                st.code(f"{i}: {q}", language="sql")



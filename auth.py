import streamlit as st
from supabase import create_client, Client
import re

# --- 1. INITIALIZE SUPABASE CLIENT ---
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

def check_password_strength(password):
    """
    Returns (is_valid, list_of_problems).
    Requires: 8+ chars, at least one uppercase, one lowercase, one digit,
    and rejects a short list of extremely common weak passwords.
    """
    problems = []

    if len(password) < 8:
        problems.append("Debe tener al menos 8 caracteres")
    if not re.search(r"[A-Z]", password):
        problems.append("Debe incluir al menos una letra mayúscula")
    if not re.search(r"[a-z]", password):
        problems.append("Debe incluir al menos una letra minúscula")
    if not re.search(r"[0-9]", password):
        problems.append("Debe incluir al menos un número")

    common_weak_passwords = {
        "12345678", "123456789", "password", "password1", "qwerty123",
        "letmein", "admin123", "welcome1", "abc12345", "iloveyou",
        "11111111", "00000000", "hello123", "football", "monkey123"
    }
    if password.lower() in common_weak_passwords:
        problems.append("Esta contraseña es demasiado común, elige otra")

    return len(problems) == 0, problems

# --- 2. AUTHENTICATION FUNCTIONS ---
def login(email, password):
    supabase = get_supabase()
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = response.user
        st.toast("Welcome back!", icon="👋")
        st.rerun()
    except Exception as e:
        st.error(f"Login failed: {e}")

def signup(email, password):
    supabase = get_supabase()
    try:
        response = supabase.auth.sign_up({"email": email, "password": password})
        st.success("Account created successfully! Check your email for verification (if required), or log in.")
    except Exception as e:
        st.error(f"Sign-up failed: {e}")

def logout():
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
        st.session_state.user = None
        st.toast("Logged out successfully.")
        st.rerun()
    except Exception as e:
        st.error(f"Logout failed: {e}")

def is_blocked_from_app(user_id, app_name):
    """Checks the app_blocks table for a row that blocks this user from this app."""
    supabase = get_supabase()
    try:
        result = (
            supabase.table("app_blocks")
            .select("blocked")
            .eq("user_id", user_id)
            .eq("app_name", app_name)
            .execute()
        )
        if result.data:
            return result.data[0]["blocked"] is True
        return False
    except Exception:
        # If the check itself fails, default to NOT blocking (fail open) so a
        # transient DB error doesn't lock everyone out. Adjust if you'd rather
        # fail closed (safer, but riskier if Supabase has a hiccup).
        return False

# --- 3. LOGIN / SIGNUP UI ---
def render_login_ui():
    """Renders the login and signup forms. Returns True if logged in, False otherwise."""
    st.title("🔐 Acceso Requerido")
    st.write("Inicia sesión para acceder al sistema.")

    tab_login, tab_signup = st.tabs(["🔑 Iniciar Sesión", "📝 Crear Cuenta"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Correo Electrónico", placeholder="usuario@ejemplo.com")
            password = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            if submit_login:
                if email and password:
                    login(email, password)
                else:
                    st.warning("Please enter both email and password.")

    with tab_signup:
        with st.form("signup_form"):
            new_email = st.text_input("Correo Electrónico", placeholder="nuevo@ejemplo.com")
            new_password = st.text_input("Contraseña", type="password", help="Mínimo 8 caracteres, con mayúscula, minúscula y número")
            confirm_password = st.text_input("Confirmar Contraseña", type="password")
            submit_signup = st.form_submit_button("Crear Cuenta", use_container_width=True)
            if submit_signup:
                if not new_email or not new_password:
                    st.warning("Please fill out all fields.")
                elif new_password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters long.")
                else:
                    signup(new_email, new_password)

# --- 4. MAIN AUTH GATEKEEPER FUNCTION ---
def require_auth(app_name: str):
    """
    Call this at the top of any Streamlit app, passing a unique app_name string.
    Returns the user object if authenticated AND not blocked from this app.
    Otherwise shows the login form or a blocked message, and stops execution.
    """
    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        render_login_ui()
        st.stop()

    # Check per-app block status
    if is_blocked_from_app(st.session_state.user.id, app_name):
        st.error("🚫 Tu acceso a esta aplicación ha sido deshabilitado. Contacta al administrador.")
        with st.sidebar:
            st.write("👤 **Logged in as:**")
            st.caption(st.session_state.user.email)
            if st.button("🚪 Log Out", use_container_width=True):
                logout()
        st.stop()

    # Render user profile & logout button in the sidebar
    with st.sidebar:
        st.write("👤 **Logged in as:**")
        st.caption(st.session_state.user.email)
        if st.button("🚪 Log Out", use_container_width=True):
            logout()
        st.divider()

    return st.session_state.user

import streamlit as st

def check_login():
    if not st.session_state.get("logged_in", False):
        st.warning("⚠️ 로그인이 필요합니다. 메인 페이지에서 로그인해주세요.")
        st.stop()

def check_admin():
    check_login()
    if not st.session_state.get("is_admin", False):
        st.error("❌ 관리자만 접근할 수 있습니다.")
        st.stop()

def get_username():
    return st.session_state.get("username", "")

def is_admin():
    return st.session_state.get("is_admin", False)

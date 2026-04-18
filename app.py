import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import json
import hashlib
import time
import re

# ── 폴더 ID 상수 ──
SYSTEM_FOLDER_ID = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"
USERS_FILE       = "users.json"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@st.cache_resource
def get_drive_service():
    info = st.secrets["google_oauth"]
    creds = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=['https://www.googleapis.com/auth/drive']
    )
    if not creds.valid:
        creds.refresh(Request())
    return build('drive', 'v3', credentials=creds)

def load_users():
    svc = get_drive_service()
    query = f"name='{USERS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if not files:
        return {}
    data = svc.files().get_media(fileId=files[0]['id']).execute()
    return json.loads(data.decode('utf-8'))

def save_users(users_dict):
    svc = get_drive_service()
    content = json.dumps(users_dict, ensure_ascii=False, indent=2).encode('utf-8')
    media = MediaInMemoryUpload(content, mimetype='application/json')
    query = f"name='{USERS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if files:
        svc.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        svc.files().create(
            body={'name': USERS_FILE, 'parents': [SYSTEM_FOLDER_ID]},
            media_body=media
        ).execute()

def is_admin_credentials(username, password):
    try:
        admin_id = st.secrets.get("admin", {}).get("username", "admin")
        admin_pw = st.secrets.get("admin", {}).get("password", "admin1234")
        return username == admin_id and hash_password(password) == hash_password(admin_pw)
    except:
        return False

# ── 세션 초기화 ──
st.set_page_config(page_title="AI 학습 플랫폼", page_icon="🚀", layout="wide")

for key, val in {
    "logged_in": False,
    "username": "",
    "is_admin": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ── 로그인 전 ──
if not st.session_state.logged_in:
    st.title("🚀 AI 학습 플랫폼")
    st.markdown("#### 비전AI · 빅데이터 · 머신러닝을 배우고 실습해보세요!")
    st.divider()

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        tab_login, tab_signup = st.tabs(["🔑 로그인", "📝 회원가입"])

        with tab_login:
            login_id = st.text_input("아이디", key="login_id")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw")
            if st.button("로그인", type="primary", use_container_width=True):
                if not login_id or not login_pw:
                    st.error("아이디와 비밀번호를 입력하세요.")
                elif is_admin_credentials(login_id, login_pw):
                    st.session_state.logged_in = True
                    st.session_state.username = login_id
                    st.session_state.is_admin = True
                    st.rerun()
                else:
                    users = load_users()
                    if login_id in users and users[login_id]['password'] == hash_password(login_pw):
                        st.session_state.logged_in = True
                        st.session_state.username = login_id
                        st.session_state.is_admin = False
                        st.rerun()
                    else:
                        st.error("❌ 아이디 또는 비밀번호가 틀렸습니다.")

        with tab_signup:
            new_id  = st.text_input("아이디 (영문/숫자 4~20자)", key="signup_id")
            new_pw  = st.text_input("비밀번호 (6자 이상)", type="password", key="signup_pw")
            new_pw2 = st.text_input("비밀번호 확인", type="password", key="signup_pw2")
            if st.button("회원가입", type="primary", use_container_width=True):
                if not new_id or not new_pw or not new_pw2:
                    st.error("모든 항목을 입력하세요.")
                elif not re.match(r'^[a-zA-Z0-9]{4,20}$', new_id):
                    st.error("아이디는 영문/숫자 4~20자로 입력하세요.")
                elif len(new_pw) < 6:
                    st.error("비밀번호는 6자 이상이어야 합니다.")
                elif new_pw != new_pw2:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    users = load_users()
                    if new_id in users:
                        st.error("❌ 이미 존재하는 아이디입니다.")
                    else:
                        users[new_id] = {
                            'password': hash_password(new_pw),
                            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        save_users(users)
                        st.success(f"✅ '{new_id}' 가입 완료! 로그인하세요.")

# ── 로그인 후 홈 ──
else:
    # 사이드바
    with st.sidebar:
        st.title("🚀 AI 학습 플랫폼")
        st.divider()
        if st.session_state.is_admin:
            st.success(f"👑 관리자: {st.session_state.username}")
        else:
            st.info(f"👤 {st.session_state.username}")
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username  = ""
            st.session_state.is_admin  = False
            st.rerun()

    # 홈 화면
    st.title(f"🚀 AI 학습 플랫폼")
    st.markdown(f"### 안녕하세요, **{st.session_state.username}**님! 👋")
    st.markdown("배우고 싶은 과목을 선택하세요.")
    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        ### 🔍 비전 AI
        - 컴퓨터 비전 이론
        - 이미지 분류 / 객체 탐지
        - 데이터 수집 · 라벨링
        - YOLO 모델 실습
        """)
        st.page_link("pages/1_비전AI.py", label="📖 비전AI 학습하기", use_container_width=True)

    with col2:
        st.markdown("""
        ### 📊 빅데이터 분석
        - 데이터란 무엇인가
        - 데이터 수집 · 전처리
        - 시각화 기초
        - 실습: 데이터 분석
        """)
        st.page_link("pages/2_빅데이터.py", label="📖 빅데이터 학습하기", use_container_width=True)

    with col3:
        st.markdown("""
        ### 🤖 머신러닝 기초
        - 머신러닝이란?
        - 지도 / 비지도 학습
        - 모델 학습 과정
        - 실습: 간단한 분류기
        """)
        st.page_link("pages/3_머신러닝.py", label="📖 머신러닝 학습하기", use_container_width=True)

    if st.session_state.is_admin:
        st.divider()
        st.page_link("pages/4_관리자.py", label="👑 관리자 페이지", use_container_width=True)

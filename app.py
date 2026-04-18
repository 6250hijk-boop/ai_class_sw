import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import json
import hashlib
import time
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

# ── 이메일 발송 ──
def send_email(to_email, subject, body):
    try:
        sender_email    = st.secrets["email"]["sender"]
        sender_password = st.secrets["email"]["password"]

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = sender_email
        msg["To"]      = to_email

        html = f"""
        <html><body>
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;
                    padding:30px;border:1px solid #ddd;border-radius:10px;">
            <h2 style="color:#4A90D9;">🚀 AI 학습 플랫폼</h2>
            <hr/>
            {body}
            <hr/>
            <p style="color:#999;font-size:12px;">본 메일은 자동 발송된 메일입니다.</p>
        </div>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"이메일 발송 실패: {e}")
        return False

def send_account_info(to_email, username):
    """아이디 찾기 이메일 발송"""
    body = f"""
    <p>안녕하세요! 아이디 찾기 요청이 접수되었습니다.</p>
    <div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:15px 0;">
        <p style="margin:0;font-size:16px;">📧 이메일: <b>{to_email}</b></p>
        <p style="margin:0;font-size:16px;">👤 아이디: <b>{username}</b></p>
    </div>
    <p>비밀번호는 보안상 확인이 불가능합니다.<br/>
    비밀번호를 잊으셨다면 <b>비밀번호 재설정</b>을 이용해주세요.</p>
    """
    return send_email(to_email, "[AI 학습 플랫폼] 아이디 안내", body)

def send_temp_password(to_email, username, temp_pw):
    """임시 비밀번호 이메일 발송"""
    body = f"""
    <p>안녕하세요, <b>{username}</b>님! 임시 비밀번호가 발급되었습니다.</p>
    <div style="background:#fff3cd;padding:15px;border-radius:8px;margin:15px 0;
                border-left:4px solid #ffc107;">
        <p style="margin:0;font-size:18px;">🔑 임시 비밀번호: <b style="color:#d63031;">{temp_pw}</b></p>
    </div>
    <p>⚠️ 로그인 후 반드시 비밀번호를 변경해주세요!</p>
    """
    return send_email(to_email, "[AI 학습 플랫폼] 임시 비밀번호 안내", body)

def generate_temp_password():
    """임시 비밀번호 생성 (8자리)"""
    import random, string
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=8))

# ── 세션 초기화 ──
st.set_page_config(page_title="AI 학습 플랫폼", page_icon="🚀", layout="wide")

for key, val in {
    "logged_in": False,
    "username": "",
    "is_admin": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ════════════════════════════════════════════
#  로그인 전
# ════════════════════════════════════════════
if not st.session_state.logged_in:
    st.title("🚀 AI 학습 플랫폼")
    st.markdown("#### 비전AI · 빅데이터 · 머신러닝을 배우고 실습해보세요!")
    st.divider()

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        tab_login, tab_signup, tab_find = st.tabs(["🔑 로그인", "📝 회원가입", "🔍 아이디/비밀번호 찾기"])

        # ── 로그인 ──
        with tab_login:
            login_id = st.text_input("아이디", key="login_id")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw")
            if st.button("로그인", type="primary", use_container_width=True):
                if not login_id or not login_pw:
                    st.error("아이디와 비밀번호를 입력하세요.")
                elif is_admin_credentials(login_id, login_pw):
                    st.session_state.logged_in = True
                    st.session_state.username  = login_id
                    st.session_state.is_admin  = True
                    st.rerun()
                else:
                    users = load_users()
                    if login_id in users and users[login_id]['password'] == hash_password(login_pw):
                        st.session_state.logged_in = True
                        st.session_state.username  = login_id
                        st.session_state.is_admin  = False
                        st.rerun()
                    else:
                        st.error("❌ 아이디 또는 비밀번호가 틀렸습니다.")

        # ── 회원가입 ──
        with tab_signup:
            new_id    = st.text_input("아이디 (영문/숫자 4~20자)", key="signup_id")
            new_email = st.text_input("이메일 주소", key="signup_email", placeholder="example@gmail.com")
            new_pw    = st.text_input("비밀번호 (6자 이상)", type="password", key="signup_pw")
            new_pw2   = st.text_input("비밀번호 확인", type="password", key="signup_pw2")

            if st.button("회원가입", type="primary", use_container_width=True):
                if not new_id or not new_email or not new_pw or not new_pw2:
                    st.error("모든 항목을 입력하세요.")
                elif not re.match(r'^[a-zA-Z0-9]{4,20}$', new_id):
                    st.error("아이디는 영문/숫자 4~20자로 입력하세요.")
                elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', new_email):
                    st.error("올바른 이메일 주소를 입력하세요.")
                elif len(new_pw) < 6:
                    st.error("비밀번호는 6자 이상이어야 합니다.")
                elif new_pw != new_pw2:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    users = load_users()
                    if new_id in users:
                        st.error("❌ 이미 존재하는 아이디입니다.")
                    elif any(u.get('email') == new_email for u in users.values()):
                        st.error("❌ 이미 사용 중인 이메일입니다.")
                    else:
                        users[new_id] = {
                            'password':   hash_password(new_pw),
                            'email':      new_email,
                            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        save_users(users)
                        st.success(f"✅ '{new_id}' 가입 완료! 로그인하세요.")

        # ── 아이디/비밀번호 찾기 ──
        with tab_find:
            find_tab1, find_tab2 = st.tabs(["👤 아이디 찾기", "🔑 비밀번호 찾기"])

            # 아이디 찾기
            with find_tab1:
                st.markdown("가입 시 등록한 이메일을 입력하면 아이디를 보내드려요.")
                find_id_email = st.text_input("이메일 주소", key="find_id_email", placeholder="example@gmail.com")
                if st.button("아이디 찾기", type="primary", use_container_width=True, key="btn_find_id"):
                    if not find_id_email:
                        st.error("이메일을 입력하세요.")
                    else:
                        users = load_users()
                        matched = [uid for uid, info in users.items() if info.get('email') == find_id_email]
                        if matched:
                            with st.spinner("이메일 발송 중..."):
                                ok = send_account_info(find_id_email, matched[0])
                            if ok:
                                st.success("✅ 아이디를 이메일로 발송했습니다!")
                        else:
                            st.error("❌ 해당 이메일로 가입된 계정이 없습니다.")

            # 비밀번호 찾기
            with find_tab2:
                st.markdown("가입 시 등록한 이메일을 입력하면 임시 비밀번호를 보내드려요.")
                find_pw_email = st.text_input("이메일 주소", key="find_pw_email", placeholder="example@gmail.com")
                if st.button("임시 비밀번호 발급", type="primary", use_container_width=True, key="btn_find_pw"):
                    if not find_pw_email:
                        st.error("이메일을 입력하세요.")
                    else:
                        users = load_users()
                        matched = [uid for uid, info in users.items() if info.get('email') == find_pw_email]
                        if matched:
                            temp_pw = generate_temp_password()
                            users[matched[0]]['password'] = hash_password(temp_pw)
                            save_users(users)
                            with st.spinner("이메일 발송 중..."):
                                ok = send_temp_password(find_pw_email, matched[0], temp_pw)
                            if ok:
                                st.success("✅ 임시 비밀번호를 이메일로 발송했습니다!\n로그인 후 비밀번호를 변경해주세요.")
                        else:
                            st.error("❌ 해당 이메일로 가입된 계정이 없습니다.")

# ════════════════════════════════════════════
#  로그인 후 홈
# ════════════════════════════════════════════
else:
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

    st.title("🚀 AI 학습 플랫폼")
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

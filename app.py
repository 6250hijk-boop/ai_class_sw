import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import os
import re
import sys
import json
import hashlib
import time

# YOLO 라이브러리 로드
YOLO = None
YOLO_ERROR = None
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception as e:
    YOLO_AVAILABLE = False
    YOLO_ERROR = str(e)

@st.cache_resource
def load_yolo_model(model_path):
    if not YOLO_AVAILABLE:
        st.error(f"❌ ultralytics import 실패 원인: {YOLO_ERROR}")
        return None
    if not os.path.exists(model_path):
        st.error(f"❌ 모델 파일 없음: '{model_path}'")
        return None
    try:
        model = YOLO(model_path)
        model.to('cpu')
        return model
    except Exception as e:
        st.error(f"❌ 모델 로드 오류: {e}")
        return None

# ── 비밀번호 암호화 ──
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ── Google Drive 서비스 ──
@st.cache_resource
def get_drive_service():
    if "google_oauth" in st.secrets:
        try:
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
        except Exception as e:
            st.error(f"Google 인증 실패: {e}")
            st.stop()
    else:
        st.error("Streamlit Secrets에 'google_oauth' 설정이 필요합니다.")
        st.stop()

service = get_drive_service()
PARENT_FOLDER_ID = "1VO3EIJ7lFLOo85dSngpDdzbaGRhZ0RUw"
USERS_FILE = "users.json"

# ── 관리자 계정 확인 ──
def is_admin_credentials(username, password):
    try:
        admin_id = st.secrets.get("admin", {}).get("username", "admin")
        admin_pw = st.secrets.get("admin", {}).get("password", "admin1234")
        return username == admin_id and hash_password(password) == hash_password(admin_pw)
    except:
        return username == "admin" and password == "admin1234"

# ── users.json 불러오기 ──
def load_users():
    query = f"name = '{USERS_FILE}' and '{PARENT_FOLDER_ID}' in parents and trashed = false"
    response = service.files().list(q=query, fields="files(id)").execute()
    files = response.get('files', [])
    if not files:
        return {}
    file_id = files[0]['id']
    data = service.files().get_media(fileId=file_id).execute()
    return json.loads(data.decode('utf-8'))

# ── users.json 저장 ──
def save_users(users_dict):
    content = json.dumps(users_dict, ensure_ascii=False, indent=2).encode('utf-8')
    media = MediaInMemoryUpload(content, mimetype='application/json')
    query = f"name = '{USERS_FILE}' and '{PARENT_FOLDER_ID}' in parents and trashed = false"
    response = service.files().list(q=query, fields="files(id)").execute()
    files = response.get('files', [])
    if files:
        service.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        service.files().create(
            body={'name': USERS_FILE, 'parents': [PARENT_FOLDER_ID]},
            media_body=media
        ).execute()

# ── 유저 폴더 ID 가져오기 or 생성 ──
def get_or_create_user_folder(username):
    folder_name = f"user_{username}"
    query = f"name = '{folder_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    response = service.files().list(q=query, fields="files(id)").execute()
    files = response.get('files', [])
    if files:
        return files[0]['id']
    folder = service.files().create(
        body={'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [PARENT_FOLDER_ID]},
        fields='id'
    ).execute()
    return folder['id']

# ── 유저 폴더 내 다음 인덱스 ──
def get_next_index_in_folder(folder_id):
    try:
        query = f"'{folder_id}' in parents and name contains 'data' and trashed = false"
        results = service.files().list(q=query, fields="files(name)").execute()
        files = results.get('files', [])
        indices = [int(re.search(r'data(\d+)', f['name']).group(1)) for f in files if re.search(r'data(\d+)', f['name'])]
        return max(indices) + 1 if indices else 1
    except:
        return 1

# ── 이미지 업로드 (유저 폴더에) ──
def upload_images_to_user_folder(files, username):
    folder_id = get_or_create_user_folder(username)
    idx = get_next_index_in_folder(folder_id)
    count = 0
    for f in files:
        img = Image.open(f).convert("RGB").resize((640, 640), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        service.files().create(
            body={'name': f"data{idx}.jpg", 'parents': [folder_id]},
            media_body=MediaInMemoryUpload(buf.getvalue(), mimetype='image/jpeg')
        ).execute()
        idx += 1
        count += 1
    return count

# ── TXT 저장 (유저 폴더에) ──
def save_txt_to_user_folder(file_name, content, username):
    folder_id = get_or_create_user_folder(username)
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    response = service.files().list(q=query, fields="files(id)").execute()
    files = response.get('files', [])
    media = MediaInMemoryUpload(content, mimetype='text/plain')
    if files:
        service.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        service.files().create(
            body={'name': file_name, 'parents': [folder_id]},
            media_body=media
        ).execute()

# ── 유저 폴더 이미지 목록 ──
def get_user_images(username):
    folder_id = get_or_create_user_folder(username)
    query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false"
    items = service.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    return items, folder_id

# ── 관리자: 모든 유저 이미지 목록 ──
def get_all_user_images():
    query = f"'{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and name contains 'user_' and trashed = false"
    folders = service.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    all_items = []
    for folder in folders:
        uname = folder['name'].replace('user_', '')
        q2 = f"'{folder['id']}' in parents and mimeType contains 'image/' and trashed = false"
        imgs = service.files().list(q=q2, fields="files(id, name)").execute().get('files', [])
        for img in imgs:
            all_items.append({'username': uname, 'folder_id': folder['id'], **img})
    return all_items

# ════════════════════════════════════════════
#  세션 초기화
# ════════════════════════════════════════════
st.set_page_config(page_title="AI 데이터 센터", layout="wide")

for key, val in {
    "logged_in": False,
    "username": "",
    "is_admin": False,
    "auth_page": "login",
    "labels": ["apple"],
    "loaded_image_id": None,
    "loaded_image_pil": None,
    "click_coords": [],
    "temp_boxes": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ════════════════════════════════════════════
#  로그인 / 회원가입 화면
# ════════════════════════════════════════════
if not st.session_state.logged_in:
    st.title("🚀 AI 데이터 센터")

    tab_login, tab_signup = st.tabs(["🔑 로그인", "📝 회원가입"])

    # ── 로그인 탭 ──
    with tab_login:
        st.subheader("로그인")
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

    # ── 회원가입 탭 ──
    with tab_signup:
        st.subheader("회원가입")
        new_id = st.text_input("아이디 (영문/숫자, 4~20자)", key="signup_id")
        new_pw = st.text_input("비밀번호 (6자 이상)", type="password", key="signup_pw")
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
                elif new_id == st.secrets.get("admin", {}).get("username", "admin"):
                    st.error("❌ 사용할 수 없는 아이디입니다.")
                else:
                    users[new_id] = {
                        'password': hash_password(new_pw),
                        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    save_users(users)
                    st.success(f"✅ 회원가입 완료! '{new_id}'로 로그인하세요.")

# ════════════════════════════════════════════
#  메인 앱 (로그인 후)
# ════════════════════════════════════════════
else:
    # 사이드바
    st.sidebar.title("🚀 AI 데이터 센터")
    if st.session_state.is_admin:
        st.sidebar.success(f"👑 관리자: {st.session_state.username}")
    else:
        st.sidebar.info(f"👤 {st.session_state.username}")

    if st.sidebar.button("🚪 로그아웃"):
        for key in ["logged_in", "username", "is_admin", "loaded_image_id", "loaded_image_pil", "click_coords", "temp_boxes"]:
            st.session_state[key] = False if key == "logged_in" else ([] if key in ["click_coords", "temp_boxes"] else ("" if key in ["username"] else None))
        st.session_state.is_admin = False
        st.rerun()

    st.sidebar.divider()

    # 메뉴
    if st.session_state.is_admin:
        MENUS = ["1. 사진 업로드", "2. 데이터 라벨링", "3. AI 모델 분석", "👑 관리자 페이지"]
    else:
        MENUS = ["1. 사진 업로드", "2. 데이터 라벨링", "3. AI 모델 분석"]

    menu = st.sidebar.radio("메뉴 선택", MENUS)

    # ── 1. 사진 업로드 ──
    if menu == "1. 사진 업로드":
        st.header("📸 학습 데이터 업로드 (640x640)")
        tab1, tab2 = st.tabs(["🖼️ 갤러리 선택", "📷 카메라 촬영"])

        with tab1:
            gallery_files = st.file_uploader("사진 선택", type=['jpg','jpeg','png'], accept_multiple_files=True)
            if st.button("📤 드라이브 전송", key="gallery_send") and gallery_files:
                with st.spinner("업로드 중..."):
                    count = upload_images_to_user_folder(gallery_files, st.session_state.username)
                st.success(f"🎉 {count}장 업로드 완료!")

        with tab2:
            camera_photo = st.camera_input("사진 찍기")
            if camera_photo:
                if st.button("📤 드라이브 전송", key="camera_send"):
                    with st.spinner("업로드 중..."):
                        count = upload_images_to_user_folder([camera_photo], st.session_state.username)
                    st.success(f"🎉 {count}장 업로드 완료!")

    # ── 2. 라벨링 ──
    elif menu == "2. 데이터 라벨링":
        st.header("🏷️ 데이터 라벨링 (YOLO 형식)")
        with st.sidebar.expander("📝 라벨 이름 관리", expanded=True):
            new_name = st.text_input("라벨 이름", value=st.session_state.labels[0])
            if st.button("적용"):
                st.session_state.labels[0] = new_name
                st.rerun()

        items, folder_id = get_user_images(st.session_state.username)

        if not items:
            st.info("📂 업로드된 사진이 없습니다. 먼저 사진을 업로드하세요.")
        else:
            target = st.selectbox("사진 선택", [i['name'] for i in items])
            tid = [i['id'] for i in items if i['name'] == target][0]

            if st.button("📥 사진 불러오기"):
                st.session_state.temp_boxes, st.session_state.click_coords = [], []
                img_data = service.files().get_media(fileId=tid).execute()
                st.session_state.loaded_image_pil = Image.open(io.BytesIO(img_data)).convert("RGB").resize((640, 640))
                st.session_state.loaded_image_id = tid

            if st.session_state.loaded_image_id == tid:
                col1, col2 = st.columns([3, 1])
                with col1:
                    img_draw = st.session_state.loaded_image_pil.copy()
                    draw = ImageDraw.Draw(img_draw)
                    for p in st.session_state.click_coords:
                        draw.ellipse((p[0]-5, p[1]-5, p[0]+5, p[1]+5), fill="red")
                    val = streamlit_image_coordinates(img_draw, key=f"label_{tid}_{len(st.session_state.temp_boxes)}")
                    if val:
                        curr_point = (val["x"], val["y"])
                        if curr_point not in st.session_state.click_coords:
                            st.session_state.click_coords.append(curr_point)
                            if len(st.session_state.click_coords) == 2:
                                c = st.session_state.click_coords
                                l, r = min(c[0][0], c[1][0]), max(c[0][0], c[1][0])
                                t, b = min(c[0][1], c[1][1]), max(c[0][1], c[1][1])
                                x = (l + r) / 2.0 / 640
                                y = (t + b) / 2.0 / 640
                                w = (r - l) / 640
                                h = (b - t) / 640
                                st.session_state.temp_boxes.append(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
                                st.session_state.click_coords = []
                                st.rerun()
                with col2:
                    st.write(f"라벨링 수: **{len(st.session_state.temp_boxes)}**")
                    if st.button("💾 드라이브 저장", type="primary"):
                        txt_name = target.rsplit('.', 1)[0] + ".txt"
                        txt_content = "\n".join(st.session_state.temp_boxes).encode()
                        save_txt_to_user_folder(txt_name, txt_content, st.session_state.username)
                        st.success("저장 완료!")

    # ── 3. AI 모델 분석 ──
    elif menu == "3. AI 모델 분석":
        st.header("🔍 AI 모델 분석")
        model = load_yolo_model("best.pt")
        if model is not None:
            test_file = st.file_uploader("분석할 이미지 선택", type=['jpg','jpeg','png'])
            if test_file:
                img_pil = Image.open(test_file).convert("RGB")
                if st.button("🚀 분석 시작"):
                    with st.spinner("AI가 분석 중입니다..."):
                        img_input = img_pil.resize((640, 640))
                        results = model.predict(img_input, conf=0.25)
                        res = results[0]
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            res_plotted = res.plot()
                            st.image(res_plotted, channels="BGR", use_column_width=True)
                        with col2:
                            if len(res.boxes) > 0:
                                st.success(f"검출 개수: {len(res.boxes)}개")
                                for i, box in enumerate(res.boxes):
                                    conf = float(box.conf[0]) * 100
                                    st.info(f"**대상 {i+1}**: {conf:.1f}%")
                                    st.progress(conf / 100)
                            else:
                                st.warning("검출된 사물이 없습니다.")

    # ── 관리자 페이지 ──
    elif menu == "👑 관리자 페이지":
        st.header("👑 관리자 페이지")

        tab_users, tab_files = st.tabs(["👥 회원 목록", "🖼️ 전체 파일 보기"])

        with tab_users:
            st.subheader("등록된 회원 목록")
            users = load_users()
            if not users:
                st.info("등록된 회원이 없습니다.")
            else:
                for uid, info in users.items():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"👤 **{uid}** — 가입일: {info.get('created_at', '알 수 없음')}")
                    with col2:
                        if st.button("🗑️ 삭제", key=f"del_{uid}"):
                            del users[uid]
                            save_users(users)
                            st.success(f"'{uid}' 삭제 완료!")
                            st.rerun()

        with tab_files:
            st.subheader("전체 학생 업로드 파일")
            all_items = get_all_user_images()
            if not all_items:
                st.info("업로드된 파일이 없습니다.")
            else:
                # 학생별로 그룹핑
                from collections import defaultdict
                grouped = defaultdict(list)
                for item in all_items:
                    grouped[item['username']].append(item)

                for uname, imgs in grouped.items():
                    with st.expander(f"👤 {uname} ({len(imgs)}장)"):
                        cols = st.columns(4)
                        for i, img in enumerate(imgs):
                            with cols[i % 4]:
                                img_data = service.files().get_media(fileId=img['id']).execute()
                                st.image(Image.open(io.BytesIO(img_data)), caption=img['name'], use_column_width=True)

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
import random
from collections import defaultdict

# ── YOLO ──
YOLO = None
YOLO_ERROR = None
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception as e:
    YOLO_AVAILABLE = False
    YOLO_ERROR = str(e)

@st.cache_resource
def load_yolo_model(model_path_id):
    if not YOLO_AVAILABLE:
        st.error(f"❌ ultralytics import 실패: {YOLO_ERROR}")
        return None
    # Drive에서 best.pt 다운로드
    try:
        svc = get_drive_service()
        data = svc.files().get_media(fileId=model_path_id).execute()
        with open("/tmp/best.pt", "wb") as f:
            f.write(data)
        model = YOLO("/tmp/best.pt")
        model.to('cpu')
        return model
    except Exception as e:
        st.error(f"❌ 모델 로드 오류: {e}")
        return None

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ── Google Drive ──
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

# ── 폴더 ID 상수 ──
ROOT_FOLDER_ID    = "1i7dospy3B3f4U6Nc3ZEzTk8hB3TCeaWL"  # 디지털연구대회
SYSTEM_FOLDER_ID  = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"  # system
TRAIN_IMG_ID      = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"  # train/images
TRAIN_LBL_ID      = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"  # train/labels
VAL_IMG_ID        = "1Q6yhtuoJiJ5b35tIdQyk0KSbskXGheXI"  # val/images
VAL_LBL_ID        = "1Iym0dtRQ3aTIcdtfzCQa_vtgJRKmfU39"  # val/labels
USERS_FILE        = "users.json"
BEST_PT_NAME      = "best.pt"

def get_drive_service_plain():
    return get_drive_service()

# ── users.json ──
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

# ── best.pt ID 가져오기 ──
def get_best_pt_id():
    svc = get_drive_service()
    query = f"name='{BEST_PT_NAME}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    return files[0]['id'] if files else None

# ── 관리자 확인 ──
def is_admin_credentials(username, password):
    try:
        admin_id = st.secrets.get("admin", {}).get("username", "admin")
        admin_pw = st.secrets.get("admin", {}).get("password", "admin1234")
        return username == admin_id and hash_password(password) == hash_password(admin_pw)
    except:
        return username == "admin" and password == "admin1234"

# ── train/images에 업로드 ──
def upload_images_to_train(files, username):
    svc = get_drive_service()
    # 기존 파일 목록 (중복 인덱스 방지)
    query = f"'{TRAIN_IMG_ID}' in parents and name contains '{username}_data' and trashed=false"
    existing = svc.files().list(q=query, fields="files(name)").execute().get('files', [])
    indices = [int(re.search(r'data(\d+)', f['name']).group(1)) for f in existing if re.search(r'data(\d+)', f['name'])]
    idx = max(indices) + 1 if indices else 1
    count = 0
    for f in files:
        img = Image.open(f).convert("RGB").resize((640, 640), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        fname = f"{username}_data{idx}.jpg"
        svc.files().create(
            body={'name': fname, 'parents': [TRAIN_IMG_ID]},
            media_body=MediaInMemoryUpload(buf.getvalue(), mimetype='image/jpeg')
        ).execute()
        idx += 1
        count += 1
    return count

# ── 본인 이미지 목록 ──
def get_user_images(username):
    svc = get_drive_service()
    query = f"'{TRAIN_IMG_ID}' in parents and name contains '{username}_data' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

# ── 라벨 저장 ──
def save_label_to_drive(file_name, content):
    svc = get_drive_service()
    media = MediaInMemoryUpload(content, mimetype='text/plain')
    query = f"name='{file_name}' and '{TRAIN_LBL_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if files:
        svc.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        svc.files().create(
            body={'name': file_name, 'parents': [TRAIN_LBL_ID]},
            media_body=media
        ).execute()

# ── 관리자: 전체 이미지 목록 ──
def get_all_train_images():
    svc = get_drive_service()
    query = f"'{TRAIN_IMG_ID}' in parents and mimeType contains 'image/' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

# ── 검증용 데이터 추출 (train → val, 비율 지정) ──
def extract_val_data(ratio=0.2):
    svc = get_drive_service()
    # train/images 전체
    all_imgs = get_all_train_images()
    if not all_imgs:
        return 0, 0

    # train/labels 목록
    query = f"'{TRAIN_LBL_ID}' in parents and trashed=false"
    all_lbls = svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    lbl_map = {f['name']: f['id'] for f in all_lbls}

    # 라벨 있는 이미지만 추출 대상
    labeled_imgs = [img for img in all_imgs if img['name'].replace('.jpg', '.txt') in lbl_map]
    if not labeled_imgs:
        return 0, 0

    n_val = max(1, int(len(labeled_imgs) * ratio))
    selected = random.sample(labeled_imgs, n_val)

    # val 폴더에 복사
    copied_imgs = 0
    copied_lbls = 0
    for img in selected:
        # 이미지 복사
        img_data = svc.files().get_media(fileId=img['id']).execute()
        # val/images에 같은 이름으로 저장 (덮어쓰기)
        q = f"name='{img['name']}' and '{VAL_IMG_ID}' in parents and trashed=false"
        exist = svc.files().list(q=q, fields="files(id)").execute().get('files', [])
        media = MediaInMemoryUpload(img_data, mimetype='image/jpeg')
        if exist:
            svc.files().update(fileId=exist[0]['id'], media_body=media).execute()
        else:
            svc.files().create(
                body={'name': img['name'], 'parents': [VAL_IMG_ID]},
                media_body=media
            ).execute()
        copied_imgs += 1

        # 라벨 복사
        lbl_name = img['name'].replace('.jpg', '.txt')
        if lbl_name in lbl_map:
            lbl_data = svc.files().get_media(fileId=lbl_map[lbl_name]).execute()
            q2 = f"name='{lbl_name}' and '{VAL_LBL_ID}' in parents and trashed=false"
            exist2 = svc.files().list(q2, fields="files(id)").execute().get('files', [])
            media2 = MediaInMemoryUpload(lbl_data, mimetype='text/plain')
            if exist2:
                svc.files().update(fileId=exist2[0]['id'], media_body=media2).execute()
            else:
                svc.files().create(
                    body={'name': lbl_name, 'parents': [VAL_LBL_ID]},
                    media_body=media2
                ).execute()
            copied_lbls += 1

    return copied_imgs, copied_lbls

# ════════════════════════════════════════════
#  세션 초기화
# ════════════════════════════════════════════
st.set_page_config(page_title="AI 데이터 센터", layout="wide")

for key, val in {
    "logged_in": False,
    "username": "",
    "is_admin": False,
    "labels": ["apple"],
    "loaded_image_id": None,
    "loaded_image_pil": None,
    "click_coords": [],
    "temp_boxes": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ════════════════════════════════════════════
#  로그인 / 회원가입
# ════════════════════════════════════════════
if not st.session_state.logged_in:
    st.title("🚀 AI 데이터 센터")
    tab_login, tab_signup = st.tabs(["🔑 로그인", "📝 회원가입"])

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
                else:
                    users[new_id] = {
                        'password': hash_password(new_pw),
                        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    save_users(users)
                    st.success(f"✅ '{new_id}' 회원가입 완료! 로그인하세요.")

# ════════════════════════════════════════════
#  메인 앱
# ════════════════════════════════════════════
else:
    st.sidebar.title("🚀 AI 데이터 센터")
    if st.session_state.is_admin:
        st.sidebar.success(f"👑 관리자: {st.session_state.username}")
    else:
        st.sidebar.info(f"👤 {st.session_state.username}")

    if st.sidebar.button("🚪 로그아웃"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.is_admin = False
        st.session_state.loaded_image_id = None
        st.session_state.loaded_image_pil = None
        st.session_state.click_coords = []
        st.session_state.temp_boxes = []
        st.rerun()

    st.sidebar.divider()

    MENUS = ["1. 사진 업로드", "2. 데이터 라벨링", "3. AI 모델 분석"]
    if st.session_state.is_admin:
        MENUS.append("👑 관리자 페이지")
    menu = st.sidebar.radio("메뉴 선택", MENUS)

    # ── 1. 사진 업로드 ──
    if menu == "1. 사진 업로드":
        st.header("📸 학습 데이터 업로드 (640x640)")
        st.info(f"📁 저장 위치: train/images/{st.session_state.username}_data*.jpg")
        tab1, tab2 = st.tabs(["🖼️ 갤러리 선택", "📷 카메라 촬영"])

        with tab1:
            gallery_files = st.file_uploader("사진 선택", type=['jpg','jpeg','png'], accept_multiple_files=True)
            if st.button("📤 드라이브 전송", key="gallery_send") and gallery_files:
                with st.spinner("업로드 중..."):
                    count = upload_images_to_train(gallery_files, st.session_state.username)
                st.success(f"🎉 {count}장 업로드 완료!")

        with tab2:
            camera_photo = st.camera_input("사진 찍기")
            if camera_photo:
                if st.button("📤 드라이브 전송", key="camera_send"):
                    with st.spinner("업로드 중..."):
                        count = upload_images_to_train([camera_photo], st.session_state.username)
                    st.success(f"🎉 {count}장 업로드 완료!")

    # ── 2. 라벨링 ──
    elif menu == "2. 데이터 라벨링":
        st.header("🏷️ 데이터 라벨링 (YOLO 형식)")
        with st.sidebar.expander("📝 라벨 이름 관리", expanded=True):
            new_name = st.text_input("라벨 이름", value=st.session_state.labels[0])
            if st.button("적용"):
                st.session_state.labels[0] = new_name
                st.rerun()

        items = get_user_images(st.session_state.username)
        if not items:
            st.info("📂 업로드된 사진이 없습니다. 먼저 사진을 업로드하세요.")
        else:
            target = st.selectbox("사진 선택", [i['name'] for i in items])
            tid = [i['id'] for i in items if i['name'] == target][0]

            if st.button("📥 사진 불러오기"):
                st.session_state.temp_boxes = []
                st.session_state.click_coords = []
                svc = get_drive_service()
                img_data = svc.files().get_media(fileId=tid).execute()
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
                        save_label_to_drive(txt_name, txt_content)
                        st.success("저장 완료!")

    # ── 3. AI 모델 분석 ──
    elif menu == "3. AI 모델 분석":
        st.header("🔍 AI 모델 분석")
        best_pt_id = get_best_pt_id()
        if not best_pt_id:
            st.error("❌ system 폴더에 best.pt 파일이 없습니다.")
        else:
            model = load_yolo_model(best_pt_id)
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
        tab_users, tab_files, tab_val = st.tabs(["👥 회원 목록", "🖼️ 전체 파일", "🔬 검증 데이터 추출"])

        # 회원 목록
        with tab_users:
            st.subheader("등록된 회원 목록")
            users = load_users()
            if not users:
                st.info("등록된 회원이 없습니다.")
            else:
                for uid, info in users.items():
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"👤 **{uid}** — 가입일: {info.get('created_at','알 수 없음')}")
                    with col2:
                        if st.button("🗑️ 삭제", key=f"del_{uid}"):
                            del users[uid]
                            save_users(users)
                            st.success(f"'{uid}' 삭제!")
                            st.rerun()

        # 전체 파일
        with tab_files:
            st.subheader("train/images 전체 파일")
            all_imgs = get_all_train_images()
            if not all_imgs:
                st.info("업로드된 파일이 없습니다.")
            else:
                grouped = defaultdict(list)
                for img in all_imgs:
                    username = img['name'].split('_data')[0] if '_data' in img['name'] else '기타'
                    grouped[username].append(img)

                st.write(f"총 **{len(all_imgs)}장** / **{len(grouped)}명**")
                for uname, imgs in grouped.items():
                    with st.expander(f"👤 {uname} ({len(imgs)}장)"):
                        svc = get_drive_service()
                        cols = st.columns(4)
                        for i, img in enumerate(imgs):
                            with cols[i % 4]:
                                img_data = svc.files().get_media(fileId=img['id']).execute()
                                st.image(Image.open(io.BytesIO(img_data)), caption=img['name'], use_column_width=True)

        # 검증 데이터 추출
        with tab_val:
            st.subheader("🔬 검증용 데이터 추출")
            st.info("train 폴더에서 일부를 랜덤 추출하여 val 폴더로 복사합니다.")

            all_imgs = get_all_train_images()
            st.write(f"현재 train/images: **{len(all_imgs)}장**")

            ratio = st.slider("검증 데이터 비율", min_value=5, max_value=40, value=20, step=5)
            n_expected = max(1, int(len(all_imgs) * ratio / 100))
            st.write(f"추출 예정: 약 **{n_expected}장**")

            if st.button("🚀 검증 데이터 추출 시작", type="primary"):
                with st.spinner("추출 중..."):
                    copied_imgs, copied_lbls = extract_val_data(ratio / 100)
                st.success(f"✅ 완료! 이미지 {copied_imgs}장, 라벨 {copied_lbls}개를 val 폴더로 복사했습니다.")

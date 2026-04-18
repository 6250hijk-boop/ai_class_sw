import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_login, get_username
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import re
import json

SYSTEM_FOLDER_ID = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"
TRAIN_IMG_ID     = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"
TRAIN_LBL_ID     = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"
USERS_FILE       = "users.json"
BEST_PT_NAME     = "best.pt"

st.set_page_config(page_title="비전AI", page_icon="🔍", layout="wide")
check_login()

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception as e:
    YOLO_ERROR = str(e)

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

@st.cache_resource
def load_yolo_model(file_id):
    if not YOLO_AVAILABLE:
        return None
    try:
        svc = get_drive_service()
        data = svc.files().get_media(fileId=file_id).execute()
        with open("/tmp/best.pt", "wb") as f:
            f.write(data)
        model = YOLO("/tmp/best.pt")
        model.to('cpu')
        return model
    except Exception as e:
        st.error(f"❌ 모델 로드 오류: {e}")
        return None

def get_best_pt_id():
    svc = get_drive_service()
    query = f"name='{BEST_PT_NAME}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    return files[0]['id'] if files else None

def load_users():
    svc = get_drive_service()
    query = f"name='{USERS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if not files:
        return {}
    data = svc.files().get_media(fileId=files[0]['id']).execute()
    return json.loads(data.decode('utf-8'))

def get_file_prefix(username):
    """학번_이름 prefix 생성"""
    users = load_users()
    if username in users:
        stunum = users[username].get('student_num', username)
        name   = users[username].get('name', username)
        return f"{stunum}_{name}"
    return username

def get_user_images(prefix):
    svc = get_drive_service()
    query = f"'{TRAIN_IMG_ID}' in parents and name contains '{prefix}_data' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

def upload_images(files, prefix):
    svc = get_drive_service()
    query = f"'{TRAIN_IMG_ID}' in parents and name contains '{prefix}_data' and trashed=false"
    existing = svc.files().list(q=query, fields="files(name)").execute().get('files', [])
    indices = [int(re.search(r'data(\d+)', f['name']).group(1)) for f in existing if re.search(r'data(\d+)', f['name'])]
    idx = max(indices) + 1 if indices else 1
    count = 0
    for f in files:
        img = Image.open(f).convert("RGB").resize((640, 640), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        fname = f"{prefix}_data{idx}.jpg"
        svc.files().create(
            body={'name': fname, 'parents': [TRAIN_IMG_ID]},
            media_body=MediaInMemoryUpload(buf.getvalue(), mimetype='image/jpeg')
        ).execute()
        idx += 1
        count += 1
    return count

def save_label(file_name, content):
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

# ── 세션 초기화 ──
for key, val in {
    "vision_labels": ["apple"],
    "loaded_image_id": None,
    "loaded_image_pil": None,
    "click_coords": [],
    "temp_boxes": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

username = get_username()

st.title("🔍 비전 AI")
st.markdown(f"👤 **{username}**")
st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📖 이론 학습", "📝 퀴즈", "📸 데이터 수집", "🤖 AI 실습"])

# ════════ 탭1: 이론 ════════
with tab1:
    st.header("📖 비전 AI 이론")
    with st.expander("1️⃣ 컴퓨터 비전이란?", expanded=True):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")
    with st.expander("2️⃣ 객체 탐지(Object Detection)란?"):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")
    with st.expander("3️⃣ YOLO 모델이란?"):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")
    with st.expander("4️⃣ 데이터 수집과 라벨링"):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")

# ════════ 탭2: 퀴즈 ════════
with tab2:
    st.header("📝 비전AI 퀴즈")
    QUIZZES = [
        {
            "q": "컴퓨터 비전에서 이미지 안의 물체를 찾고 위치를 표시하는 기술은?",
            "options": ["이미지 분류", "객체 탐지", "이미지 생성", "음성 인식"],
            "answer": "객체 탐지",
            "explain": "객체 탐지(Object Detection)는 이미지에서 물체의 위치(바운딩 박스)와 종류를 동시에 찾아냅니다."
        },
        {
            "q": "YOLO는 무엇의 약자인가요?",
            "options": ["You Only Look Once", "Your Object Looks Obvious", "Yellow Orange Light Output", "You Only Learn Once"],
            "answer": "You Only Look Once",
            "explain": "YOLO는 'You Only Look Once'의 약자로, 이미지를 한 번만 보고 빠르게 객체를 탐지하는 모델입니다."
        },
        {
            "q": "AI 모델을 학습시키기 위해 이미지에 물체의 위치를 표시하는 작업은?",
            "options": ["전처리", "라벨링", "증강", "추론"],
            "answer": "라벨링",
            "explain": "라벨링(Labeling)은 AI가 학습할 수 있도록 이미지에 정답을 표시하는 작업입니다."
        },
    ]
    score = 0
    for i, quiz in enumerate(QUIZZES):
        st.markdown(f"**Q{i+1}. {quiz['q']}**")
        choice = st.radio("답을 선택하세요", quiz['options'], key=f"quiz_{i}", index=None)
        if choice:
            if choice == quiz['answer']:
                st.success(f"✅ 정답! {quiz['explain']}")
                score += 1
            else:
                st.error(f"❌ 오답! 정답은 **{quiz['answer']}** 입니다. {quiz['explain']}")
        st.divider()
    answered = sum(1 for i in range(len(QUIZZES)) if st.session_state.get(f"quiz_{i}"))
    if answered == len(QUIZZES):
        st.markdown(f"### 🎯 최종 점수: {score} / {len(QUIZZES)}")
        if score == len(QUIZZES):
            st.balloons()

# ════════ 탭3: 데이터 수집 ════════
with tab3:
    st.header("📸 학습 데이터 수집")
    prefix = get_file_prefix(username)
    st.info(f"📁 저장 파일명: `{prefix}_data*.jpg`")

    upload_tab1, upload_tab2 = st.tabs(["🖼️ 갤러리", "📷 카메라"])
    with upload_tab1:
        gallery_files = st.file_uploader("사진 선택", type=['jpg','jpeg','png'], accept_multiple_files=True)
        if st.button("📤 업로드", key="gallery_up") and gallery_files:
            with st.spinner("업로드 중..."):
                count = upload_images(gallery_files, prefix)
            st.success(f"🎉 {count}장 완료!")
    with upload_tab2:
        cam = st.camera_input("사진 찍기")
        if cam and st.button("📤 업로드", key="cam_up"):
            with st.spinner("업로드 중..."):
                count = upload_images([cam], prefix)
            st.success(f"🎉 {count}장 완료!")

    st.divider()
    st.subheader("🏷️ 라벨링")
    with st.sidebar:
        new_label = st.text_input("라벨 이름", value=st.session_state.vision_labels[0])
        if st.button("적용"):
            st.session_state.vision_labels[0] = new_label
            st.rerun()

    items = get_user_images(prefix)
    if not items:
        st.info("업로드된 사진이 없습니다.")
    else:
        target = st.selectbox("라벨링할 사진 선택", [i['name'] for i in items])
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
                val = streamlit_image_coordinates(img_draw, key=f"lbl_{tid}_{len(st.session_state.temp_boxes)}")
                if val:
                    pt = (val["x"], val["y"])
                    if pt not in st.session_state.click_coords:
                        st.session_state.click_coords.append(pt)
                        if len(st.session_state.click_coords) == 2:
                            c = st.session_state.click_coords
                            l, r = min(c[0][0],c[1][0]), max(c[0][0],c[1][0])
                            t, b = min(c[0][1],c[1][1]), max(c[0][1],c[1][1])
                            x = (l+r)/2/640; y = (t+b)/2/640
                            w = (r-l)/640;   h = (b-t)/640
                            st.session_state.temp_boxes.append(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
                            st.session_state.click_coords = []
                            st.rerun()
            with col2:
                st.write(f"박스 수: **{len(st.session_state.temp_boxes)}**")
                if st.button("💾 저장", type="primary"):
                    txt_name = target.rsplit('.',1)[0] + ".txt"
                    save_label(txt_name, "\n".join(st.session_state.temp_boxes).encode())
                    st.success("저장 완료!")

# ════════ 탭4: AI 실습 ════════
with tab4:
    st.header("🤖 AI 모델 분석 실습")
    best_pt_id = get_best_pt_id()
    if not best_pt_id:
        st.error("❌ system 폴더에 best.pt가 없습니다.")
    else:
        model = load_yolo_model(best_pt_id)
        if model:
            test_file = st.file_uploader("분석할 이미지", type=['jpg','jpeg','png'])
            if test_file:
                img_pil = Image.open(test_file).convert("RGB")
                if st.button("🚀 분석 시작"):
                    with st.spinner("분석 중..."):
                        results = model.predict(img_pil.resize((640,640)), conf=0.25)
                        res = results[0]
                        col1, col2 = st.columns([2,1])
                        with col1:
                            st.image(res.plot(), channels="BGR", use_column_width=True)
                        with col2:
                            if len(res.boxes) > 0:
                                st.success(f"검출: {len(res.boxes)}개")
                                for i, box in enumerate(res.boxes):
                                    conf = float(box.conf[0]) * 100
                                    st.info(f"**{i+1}**: {conf:.1f}%")
                                    st.progress(conf/100)
                            else:
                                st.warning("검출된 사물이 없습니다.")

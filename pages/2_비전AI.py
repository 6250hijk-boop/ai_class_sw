import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_login, get_username
from utils.firebase import get_db
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io, re, json

TRAIN_IMG_ID = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"
TRAIN_LBL_ID = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"

st.set_page_config(page_title="비전AI", page_icon="🔍", layout="wide")
check_login()

# ── CSS ──
st.markdown("""
<style>
div[data-testid="stSpinner"] {
    position: fixed !important;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    background: rgba(0,0,0,0.65);
    backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
    z-index: 9999;
}
div[data-testid="stSpinner"] > div {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border: 2px solid #4A90D9;
    border-radius: 20px;
    padding: 48px 72px;
    display: flex; flex-direction: column;
    align-items: center; gap: 20px;
    box-shadow: 0 0 60px rgba(74,144,217,0.5);
}
div[data-testid="stSpinner"] p {
    color: #e0e0ff !important; font-size: 18px !important;
    font-weight: 600 !important;
}
div[data-testid="stSpinner"] svg {
    width: 56px !important; height: 56px !important;
    stroke: #4A90D9 !important;
}
</style>
""", unsafe_allow_html=True)

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception as e:
    YOLO_ERROR = str(e)

@st.cache_resource
def load_yolo_model():
    if not YOLO_AVAILABLE:
        return None
    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "best.pt")
    if not os.path.exists(model_path):
        model_path = "best.pt"
    if not os.path.exists(model_path):
        st.error(f"❌ best.pt 파일을 찾을 수 없습니다.")
        return None
    try:
        model = YOLO(model_path)
        model.to('cpu')
        return model
    except Exception as e:
        st.error(f"❌ 모델 로드 오류: {e}")
        return None

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

# ── Firebase 라벨 ──
def load_labels():
    db = get_db()
    doc = db.collection("settings").document("labels").get()
    if doc.exists:
        return doc.to_dict().get("list", ["vicpie"])
    return ["vicpie"]

# ── 사용자 정보 ──
def get_file_prefix(username):
    db = get_db()
    doc = db.collection("users").document(username).get()
    if doc.exists:
        info = doc.to_dict()
        stunum = info.get('student_num', username)
        name   = info.get('name', username)
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
        svc.files().create(
            body={'name': f"{prefix}_data{idx}.jpg", 'parents': [TRAIN_IMG_ID]},
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
        svc.files().create(body={'name': file_name, 'parents': [TRAIN_LBL_ID]}, media_body=media).execute()

def get_label_status(prefix):
    svc = get_drive_service()
    query = f"'{TRAIN_IMG_ID}' in parents and name contains '{prefix}_data' and trashed=false"
    imgs = svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    query2 = f"'{TRAIN_LBL_ID}' in parents and name contains '{prefix}_data' and trashed=false"
    lbls = svc.files().list(q=query2, fields="files(id, name)").execute().get('files', [])
    lbl_names = {f['name'] for f in lbls}
    return [{'id': img['id'], 'name': img['name'], 'labeled': img['name'].replace('.jpg','.txt') in lbl_names} for img in imgs]

def draw_label_overlay(img_pil, click_coords, temp_boxes):
    img_draw = img_pil.copy()
    draw = ImageDraw.Draw(img_draw)
    W, H = img_draw.size
    GRID_N = 11
    for i in range(1, GRID_N):
        draw.line([int(W*i/GRID_N), 0, int(W*i/GRID_N), H], fill=(200,200,200), width=1)
        draw.line([0, int(H*i/GRID_N), W, int(H*i/GRID_N)], fill=(200,200,200), width=1)
    for box_str in temp_boxes:
        parts = box_str.strip().split()
        if len(parts) == 5:
            _, cx, cy, bw, bh = map(float, parts)
            x1=int((cx-bw/2)*W); y1=int((cy-bh/2)*H)
            x2=int((cx+bw/2)*W); y2=int((cy+bh/2)*H)
            draw.rectangle([x1,y1,x2,y2], outline="#00FF00", width=3)
            corner=12
            for px2,py2 in [(x1,y1),(x2,y1),(x1,y2),(x2,y2)]:
                dx=1 if px2==x1 else -1; dy=1 if py2==y1 else -1
                draw.line([px2,py2,px2+dx*corner,py2], fill="#00FF00", width=4)
                draw.line([px2,py2,px2,py2+dy*corner], fill="#00FF00", width=4)
    for px, py in click_coords:
        draw.line([0, py, W, py], fill="#FF3333", width=1)
        draw.line([px, 0, px, H], fill="#FF3333", width=1)
        r=6
        draw.ellipse([px-r,py-r,px+r,py+r], fill="#FF3333", outline="white", width=2)
    return img_draw

# ── 세션 초기화 ──
for key, val in {
    "vision_labels": ["vicpie"],
    "cached_labels": None,
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

with tab2:
    st.header("📝 비전AI 퀴즈")
    QUIZZES = [
        {"q": "컴퓨터 비전에서 이미지 안의 물체를 찾고 위치를 표시하는 기술은?",
         "options": ["이미지 분류", "객체 탐지", "이미지 생성", "음성 인식"],
         "answer": "객체 탐지",
         "explain": "객체 탐지(Object Detection)는 이미지에서 물체의 위치와 종류를 동시에 찾아냅니다."},
        {"q": "YOLO는 무엇의 약자인가요?",
         "options": ["You Only Look Once", "Your Object Looks Obvious", "Yellow Orange Light Output", "You Only Learn Once"],
         "answer": "You Only Look Once",
         "explain": "YOLO는 'You Only Look Once'의 약자로, 이미지를 한 번만 보고 빠르게 객체를 탐지합니다."},
        {"q": "AI 모델을 학습시키기 위해 이미지에 물체의 위치를 표시하는 작업은?",
         "options": ["전처리", "라벨링", "증강", "추론"],
         "answer": "라벨링",
         "explain": "라벨링은 AI가 학습할 수 있도록 이미지에 정답을 표시하는 작업입니다."},
    ]
    for i, quiz in enumerate(QUIZZES):
        st.markdown(f"**Q{i+1}. {quiz['q']}**")
        choice = st.radio("답을 선택하세요", quiz['options'], key=f"quiz_{i}", index=None)
        if choice:
            if choice == quiz['answer']:
                st.success(f"✅ 정답! {quiz['explain']}")
            else:
                st.error(f"❌ 오답! 정답은 **{quiz['answer']}** 입니다.")
        st.divider()

with tab3:
    st.header("📸 학습 데이터 수집")
    prefix = get_file_prefix(username)
    st.info(f"📁 저장 파일명: `{prefix}_data*.jpg`")

    upload_tab1, upload_tab2 = st.tabs(["🖼️ 갤러리", "📷 카메라"])
    with upload_tab1:
        gallery_files = st.file_uploader("사진 선택", type=['jpg','jpeg','png'], accept_multiple_files=True)
        if st.button("📤 업로드", key="gallery_up") and gallery_files:
            with st.spinner("☁️ 구글 드라이브에 업로드 중입니다..."):
                count = upload_images(gallery_files, prefix)
            st.success(f"🎉 {count}장 완료!")
    with upload_tab2:
        cam = st.camera_input("사진 찍기")
        if cam and st.button("📤 업로드", key="cam_up"):
            with st.spinner("☁️ 구글 드라이브에 업로드 중입니다..."):
                count = upload_images([cam], prefix)
            st.success(f"🎉 {count}장 완료!")

    st.divider()
    st.subheader("🏷️ 라벨링")

    with st.sidebar:
        st.subheader("⚙️ 라벨 설정")
        if st.session_state.cached_labels is None:
            with st.spinner("라벨 목록 불러오는 중..."):
                st.session_state.cached_labels = load_labels()
        drive_labels = st.session_state.cached_labels or ["vicpie"]

        if st.button("🔄 라벨 새로고침", use_container_width=True):
            with st.spinner("라벨 목록 갱신 중..."):
                st.session_state.cached_labels = load_labels()
            st.rerun()

        options = drive_labels + ["✏️ 직접 입력"]
        current_label = st.session_state.vision_labels[0]
        default_idx = drive_labels.index(current_label) if current_label in drive_labels else 0
        label_choice = st.selectbox("라벨 선택", options, index=default_idx)
        if label_choice == "✏️ 직접 입력":
            custom_label = st.text_input("직접 입력", placeholder="라벨명 입력")
            if custom_label:
                st.session_state.vision_labels[0] = custom_label
        else:
            st.session_state.vision_labels[0] = label_choice

        st.info(f"현재 라벨: **{st.session_state.vision_labels[0]}**")
        st.divider()
        st.markdown("""
        **📌 라벨링 방법**
        1. 사진을 불러오세요
        2. 물체의 **왼쪽 위** 클릭 🔴
        3. 물체의 **오른쪽 아래** 클릭 🔴
        4. 박스가 자동으로 그려져요 🟩
        5. 저장 버튼을 누르세요 💾
        """)
        if st.session_state.temp_boxes:
            if st.button("↩️ 마지막 박스 취소"):
                st.session_state.temp_boxes.pop()
                st.rerun()
        if st.button("🗑️ 전체 초기화"):
            st.session_state.temp_boxes = []
            st.session_state.click_coords = []
            st.rerun()

    with st.spinner("📂 사진 목록 불러오는 중..."):
        img_status_list = get_label_status(prefix)

    if not img_status_list:
        st.info("업로드된 사진이 없습니다.")
    else:
        labeled_count   = sum(1 for i in img_status_list if i['labeled'])
        unlabeled_count = sum(1 for i in img_status_list if not i['labeled'])
        col1, col2, col3 = st.columns(3)
        col1.metric("전체", f"{len(img_status_list)}장")
        col2.metric("🟢 라벨링 완료", f"{labeled_count}장")
        col3.metric("🔴 라벨링 미완료", f"{unlabeled_count}장")
        st.divider()

        filter_opt = st.radio("표시할 사진", ["전체", "🔴 미완료만", "🟢 완료만"], horizontal=True)
        if filter_opt == "🔴 미완료만":
            filtered = [i for i in img_status_list if not i['labeled']]
        elif filter_opt == "🟢 완료만":
            filtered = [i for i in img_status_list if i['labeled']]
        else:
            filtered = img_status_list

        if not filtered:
            st.info("해당하는 사진이 없습니다.")
        else:
            options = [f"{'🟢' if i['labeled'] else '🔴'} {i['name']}" for i in filtered]
            selected_opt = st.selectbox("라벨링할 사진 선택", options)
            selected_idx = options.index(selected_opt)
            target = filtered[selected_idx]['name']
            tid    = filtered[selected_idx]['id']

            if st.button("📥 사진 불러오기"):
                st.session_state.temp_boxes = []
                st.session_state.click_coords = []
                with st.spinner("🖼️ 사진을 불러오는 중입니다..."):
                    svc = get_drive_service()
                    img_data = svc.files().get_media(fileId=tid).execute()
                    st.session_state.loaded_image_pil = Image.open(io.BytesIO(img_data)).convert("RGB").resize((640,640))
                    st.session_state.loaded_image_id = tid

            if 'tid' in dir() and st.session_state.loaded_image_id == tid:
                col1, col2 = st.columns([3, 1])
                with col1:
                    img_overlay = draw_label_overlay(
                        st.session_state.loaded_image_pil,
                        st.session_state.click_coords,
                        st.session_state.temp_boxes
                    )
                    if len(st.session_state.click_coords) == 0:
                        st.info("📍 물체의 **왼쪽 위** 모서리를 클릭하세요")
                    else:
                        st.warning("📍 물체의 **오른쪽 아래** 모서리를 클릭하세요")

                    val = streamlit_image_coordinates(
                        img_overlay,
                        key=f"lbl_{tid}_{len(st.session_state.temp_boxes)}_{len(st.session_state.click_coords)}"
                    )
                    if val:
                        pt = (val["x"], val["y"])
                        if pt not in st.session_state.click_coords:
                            st.session_state.click_coords.append(pt)
                            if len(st.session_state.click_coords) == 2:
                                c = st.session_state.click_coords
                                l,r = min(c[0][0],c[1][0]), max(c[0][0],c[1][0])
                                t,b = min(c[0][1],c[1][1]), max(c[0][1],c[1][1])
                                x=(l+r)/2/640; y=(t+b)/2/640
                                w=(r-l)/640;   h=(b-t)/640
                                cached = st.session_state.get("cached_labels") or ["vicpie"]
                                cur_label = st.session_state.vision_labels[0]
                                label_idx = cached.index(cur_label) if cur_label in cached else 0
                                st.session_state.temp_boxes.append(f"{label_idx} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
                                st.session_state.click_coords = []
                                st.rerun()
                            else:
                                st.rerun()

                with col2:
                    st.markdown("### 📊 현황")
                    st.metric("완성된 박스", f"{len(st.session_state.temp_boxes)}개")
                    if st.session_state.temp_boxes:
                        st.markdown("**박스 목록:**")
                        for i, box in enumerate(st.session_state.temp_boxes):
                            st.caption(f"박스 {i+1}: {box[:20]}...")
                    st.divider()
                    if st.button("💾 저장", type="primary", use_container_width=True):
                        if not st.session_state.temp_boxes:
                            st.error("박스가 없습니다!")
                        else:
                            txt_name = target.rsplit('.',1)[0] + ".txt"
                            save_label(txt_name, "\n".join(st.session_state.temp_boxes).encode())
                            st.success("✅ 저장 완료!")
                    if st.button("↩️ 마지막 박스 취소", use_container_width=True):
                        if st.session_state.temp_boxes:
                            st.session_state.temp_boxes.pop()
                            st.session_state.click_coords = []
                            st.rerun()
                        else:
                            st.warning("취소할 박스가 없습니다.")

with tab4:
    st.header("🤖 AI 모델 분석 실습")
    model = load_yolo_model()
    if model:
        with st.expander("🔎 모델 정보 확인"):
            st.write(f"**클래스 목록:** {model.names}")
            st.write(f"**클래스 수:** {len(model.names)}")

        test_file = st.file_uploader("분석할 이미지", type=['jpg','jpeg','png'])
        if test_file:
            img_pil = Image.open(test_file).convert("RGB")
            st.image(img_pil, caption="업로드된 이미지", width=400)
            conf_val = st.slider("신뢰도 임계값", 0.01, 0.9, 0.25, 0.01)
            if st.button("🚀 분석 시작"):
                with st.spinner("🤖 AI가 이미지를 분석 중입니다..."):
                    try:
                        img_input = img_pil.resize((640,640))
                        results = model.predict(img_input, conf=conf_val, verbose=False)
                        res = results[0]
                        img_result = img_input.copy()
                        draw = ImageDraw.Draw(img_result)
                        col1, col2 = st.columns([2,1])
                        with col1:
                            if len(res.boxes) > 0:
                                for box in res.boxes:
                                    x1,y1,x2,y2 = map(int, box.xyxy[0].tolist())
                                    label = model.names[int(box.cls[0])]
                                    conf  = float(box.conf[0])
                                    draw.rectangle([x1,y1,x2,y2], outline="#00FF00", width=3)
                                    label_text = f"{label} {conf*100:.0f}%"
                                    draw.rectangle([x1,y1-22,x1+len(label_text)*8,y1], fill="#00FF00")
                                    draw.text((x1+2,y1-20), label_text, fill="black")
                            st.image(img_result, width=400)
                        with col2:
                            if len(res.boxes) > 0:
                                st.success(f"✅ {len(res.boxes)}개 검출!")
                                for i, box in enumerate(res.boxes):
                                    label = model.names[int(box.cls[0])]
                                    conf  = float(box.conf[0]) * 100
                                    st.info(f"**{i+1}. {label}**: {conf:.1f}%")
                                    st.progress(conf/100)
                            else:
                                st.warning("검출된 사물이 없습니다.")
                                st.info("💡 신뢰도 임계값을 낮춰보세요 (예: 0.05)")
                    except Exception as e:
                        st.error(f"❌ 분석 오류: {e}")

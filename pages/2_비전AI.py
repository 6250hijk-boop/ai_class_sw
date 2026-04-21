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

# ── 전체 로딩 + 스피너 커스텀 CSS ──
st.markdown("""
<style>
/* ── 페이지 전환 로딩 오버레이 ── */
[data-testid="stAppViewContainer"] > div:first-child {
    animation: fadeIn 0.3s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ── 전체 로딩바 (상단) ── */
div[data-testid="stProgressBar"] > div {
    background: linear-gradient(90deg, #4A90D9, #7B68EE, #4A90D9) !important;
    background-size: 200% !important;
    animation: shimmer 1.5s infinite !important;
}
@keyframes shimmer {
    0%   { background-position: 200% center; }
    100% { background-position: -200% center; }
}

/* ── 스피너 오버레이 ── */
div[data-testid="stSpinner"] {
    position: fixed !important;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    background: rgba(0, 0, 0, 0.65);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
}
div[data-testid="stSpinner"] > div {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border: 2px solid #4A90D9;
    border-radius: 20px;
    padding: 48px 72px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
    box-shadow: 0 0 60px rgba(74,144,217,0.5),
                0 20px 40px rgba(0,0,0,0.4);
}
div[data-testid="stSpinner"] p {
    color: #e0e0ff !important;
    font-size: 18px !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px !important;
    margin: 0 !important;
}
div[data-testid="stSpinner"] svg {
    width: 56px !important;
    height: 56px !important;
    stroke: #4A90D9 !important;
    filter: drop-shadow(0 0 8px #4A90D9);
}

/* ── Streamlit 기본 앱 로딩 화면 ── */
div.stApp > header {
    background: transparent;
}
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception as e:
    YOLO_ERROR = str(e)

@st.cache_resource
def get_drive_credentials():
    """credentials만 캐싱 (서비스 객체는 캐싱 안 함)"""
    info = st.secrets["google_oauth"]
    creds = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return info

def get_drive_service():
    """매번 새로운 서비스 객체 생성 (SSL 오류 방지)"""
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
def load_yolo_model():
    if not YOLO_AVAILABLE:
        st.error(f"❌ ultralytics 설치 필요")
        return None
    # 깃허브 루트의 best.pt 직접 사용
    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "best.pt")
    if not os.path.exists(model_path):
        # 현재 디렉토리에서도 찾기
        model_path = "best.pt"
    if not os.path.exists(model_path):
        st.error(f"❌ best.pt 파일을 찾을 수 없습니다. (경로: {model_path})")
        return None
    try:
        model = YOLO(model_path)
        model.to('cpu')
        return model
    except Exception as e:
        st.error(f"❌ 모델 로드 오류: {e}")
        return None

def load_users():
    svc = get_drive_service()
    query = f"name='{USERS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if not files:
        return {}
    data = svc.files().get_media(fileId=files[0]['id']).execute()
    return json.loads(data.decode('utf-8'))

def load_labels():
    """관리자가 설정한 라벨 목록 불러오기"""
    svc = get_drive_service()
    query = f"name='labels.json' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if not files:
        return ["vicpie"]
    data = svc.files().get_media(fileId=files[0]['id']).execute()
    return json.loads(data.decode('utf-8'))

def get_label_status(prefix):
    """학생의 이미지별 라벨링 완료 여부 반환"""
    svc = get_drive_service()
    query = f"'{TRAIN_IMG_ID}' in parents and name contains '{prefix}_data' and trashed=false"
    imgs = svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    query2 = f"'{TRAIN_LBL_ID}' in parents and name contains '{prefix}_data' and trashed=false"
    lbls = svc.files().list(q=query2, fields="files(id, name)").execute().get('files', [])
    lbl_names = {f['name'] for f in lbls}
    result = []
    for img in imgs:
        txt_name = img['name'].replace('.jpg', '.txt')
        result.append({
            'id': img['id'],
            'name': img['name'],
            'labeled': txt_name in lbl_names
        })
    return result

def get_file_prefix(username):
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

def draw_label_overlay(img_pil, click_coords, temp_boxes):
    """이미지에 격자 + 십자선 + 완성된 박스를 그려서 반환"""
    img_draw = img_pil.copy()
    draw = ImageDraw.Draw(img_draw)
    W, H = img_draw.size

    # ── 격자무늬 (가로 11칸, 세로 11칸 = 선 10개씩) ──
    GRID_N = 11
    for i in range(1, GRID_N):
        x = int(W * i / GRID_N)
        y = int(H * i / GRID_N)
        draw.line([x, 0, x, H], fill=(200, 200, 200), width=1)  # 세로선
        draw.line([0, y, W, y], fill=(200, 200, 200), width=1)  # 가로선

    # ── 완성된 박스 그리기 (초록색) ──
    for box_str in temp_boxes:
        parts = box_str.strip().split()
        if len(parts) == 5:
            _, cx, cy, bw, bh = map(float, parts)
            x1 = int((cx - bw/2) * W)
            y1 = int((cy - bh/2) * H)
            x2 = int((cx + bw/2) * W)
            y2 = int((cy + bh/2) * H)
            # 박스 테두리
            draw.rectangle([x1, y1, x2, y2], outline="#00FF00", width=3)
            # 모서리 강조
            corner = 12
            for cx2, cy2 in [(x1,y1),(x2,y1),(x1,y2),(x2,y2)]:
                dx = 1 if cx2 == x1 else -1
                dy = 1 if cy2 == y1 else -1
                draw.line([cx2, cy2, cx2 + dx*corner, cy2], fill="#00FF00", width=4)
                draw.line([cx2, cy2, cx2, cy2 + dy*corner], fill="#00FF00", width=4)

    # ── 클릭 포인트 + 전체 십자선 그리기 (빨간색) ──
    for px, py in click_coords:
        # 이미지 전체를 가로지르는 십자선
        draw.line([0, py, W, py], fill="#FF3333", width=1)
        draw.line([px, 0, px, H], fill="#FF3333", width=1)
        # 중앙 원
        r = 6
        draw.ellipse([px-r, py-r, px+r, py+r], fill="#FF3333", outline="white", width=2)

    return img_draw

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
# ════════ 탭1: 이론 ════════
with tab1:
    st.header("📖 비전 AI: 컴퓨터의 똑똑한 눈")
    
    with st.expander("1️⃣ 컴퓨터 비전이란?", expanded=True):
        st.markdown("""
        컴퓨터 비전은 컴퓨터에게 **'시각(눈)'**과 **'이해력(뇌)'**을 주는 기술이에요.  
        사람이 눈으로 물체를 보고 "저건 사과네!"라고 아는 것처럼, 컴퓨터도 사진이나 영상 속의 데이터를 분석해서 무엇인지 알아내는 것이죠.
        """)
        # 

    with st.expander("2️⃣ 객체 탐지(Object Detection)란?"):
        st.markdown("""
        단순히 "이 사진은 강아지 사진이야"라고 말하는 것을 넘어, **"강아지가 사진의 어디(위치)에 있는지"** 사각형 박스를 그려서 찾아내는 기술이에요.  
        '무엇(What)'인지와 '어디(Where)'에 있는지를 동시에 알아내는 것이 핵심입니다!
        """)
        # 

    with st.expander("3️⃣ YOLO 모델이란?"):
        st.markdown("""
        **YOLO**는 'You Only Look Once'의 약자로, **"딱 한 번만 보고 바로 알아낸다"**는 뜻이에요.  
        다른 AI들보다 훨씬 빨라서 자율주행 자동차처럼 실시간으로 빠르게 물체를 찾아야 할 때 아주 많이 쓰이는 인기 모델이랍니다.
        """)
        # 

    with st.expander("4️⃣ 데이터 수집과 라벨링"):
        st.markdown("""
        AI가 물체를 잘 찾으려면 공부를 해야 해요. 사람이 직접 사진 속 물체에 박스를 그려서 **"이게 정답이야!"**라고 알려주는 과정을 **'라벨링(Labeling)'**이라고 불러요.  
        여러분이 정성껏 그린 박스 하나하나가 AI의 똑똑한 학습 데이터가 된답니다.
        """)
        # 

[Image of data labeling for machine learning]

# ════════ 탭2: 퀴즈 ════════
with tab2:
    st.header("📝 비전 AI 실력 테스트")
    st.write("방금 공부한 내용을 잘 기억하고 있나요?")
    
    QUIZZES = [
        {
            "q": "이미지에서 물체가 '무엇'인지 맞히고, '어디'에 있는지 박스를 그려 찾는 기술은?",
            "options": ["이미지 생성", "객체 탐지(Object Detection)", "음성 변환", "글자 읽기"],
            "answer": "객체 탐지(Object Detection)",
            "explain": "객체 탐지는 물체의 종류와 위치(박스)를 한꺼번에 찾아내는 기술이에요."
        },
        {
            "q": "YOLO라는 이름의 뜻으로 가장 알맞은 것은?",
            "options": ["한 번만 봐도 다 알아", "매일매일 공부하자", "노란색 오렌지 빛깔", "너는 혼자가 아니야"],
            "answer": "한 번만 봐도 다 알아",
            "explain": "You Only Look Once(딱 한 번만 본다)의 줄임말로, 아주 빠른 분석 속도를 자랑해요."
        },
        {
            "q": "AI 모델이 공부할 수 있도록 사진 속 물체에 정답 박스를 그려주는 작업은?",
            "options": ["필터 씌우기", "사진 찍기", "라벨링(Labeling)", "게임하기"],
            "answer": "라벨링(Labeling)",
            "explain": "AI에게 정답을 가르쳐주는 '라벨링'이 잘 되어야 똑똑한 AI가 만들어져요."
        },
    ]
    # (이하 퀴즈 처리 로직은 기존 코드와 동일하게 사용)

# ════════ 탭3: 데이터 수집 ════════
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

        # 드라이브에서 라벨 목록 불러오기
        drive_labels = load_labels()
        if drive_labels:
            label_choice = st.selectbox("라벨 선택", drive_labels + ["✏️ 직접 입력"])
            if label_choice == "✏️ 직접 입력":
                custom_label = st.text_input("직접 입력", placeholder="라벨명 입력")
                if custom_label:
                    st.session_state.vision_labels[0] = custom_label
            else:
                st.session_state.vision_labels[0] = label_choice
        else:
            custom_label = st.text_input("라벨 이름 입력", placeholder="라벨명 입력")
            if custom_label:
                st.session_state.vision_labels[0] = custom_label

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

    # 라벨링 완료/미완료 구분해서 이미지 목록 표시
    with st.spinner("📂 사진 목록 불러오는 중..."):
        img_status_list = get_label_status(prefix)

    if not img_status_list:
        st.info("업로드된 사진이 없습니다.")
    else:
        # 완료/미완료 통계
        labeled_count   = sum(1 for i in img_status_list if i['labeled'])
        unlabeled_count = sum(1 for i in img_status_list if not i['labeled'])

        col1, col2, col3 = st.columns(3)
        col1.metric("전체", f"{len(img_status_list)}장")
        col2.metric("🟢 라벨링 완료", f"{labeled_count}장")
        col3.metric("🔴 라벨링 미완료", f"{unlabeled_count}장")

        st.divider()

        # 필터 선택
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
            # 선택박스에 완료 여부 표시
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
                    st.session_state.loaded_image_pil = Image.open(io.BytesIO(img_data)).convert("RGB").resize((640, 640))
                    st.session_state.loaded_image_id = tid

        if 'tid' in dir() and st.session_state.loaded_image_id == tid:
            col1, col2 = st.columns([3, 1])
            with col1:
                # 이미지에 십자선 + 박스 오버레이
                img_overlay = draw_label_overlay(
                    st.session_state.loaded_image_pil,
                    st.session_state.click_coords,
                    st.session_state.temp_boxes
                )

                # 안내 메시지
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
                            l, r = min(c[0][0],c[1][0]), max(c[0][0],c[1][0])
                            t, b = min(c[0][1],c[1][1]), max(c[0][1],c[1][1])
                            x = (l+r)/2/640
                            y = (t+b)/2/640
                            w = (r-l)/640
                            h = (b-t)/640
                            st.session_state.temp_boxes.append(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
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

# ════════ 탭4: AI 실습 ════════

with col2:
    st.write(f"**🤖 AI의 확신 점수(신뢰도):** {conf_val}")
    st.write(f"**찾아낸 물체 개수:** {len(boxes)}개")
    
    if len(boxes) > 0:
        st.success(f"✅ 와우! {len(boxes)}개의 물체를 찾았어요!")
        for i, box in enumerate(boxes):
            label = model.names[int(box.cls[0])]
            conf  = float(box.conf[0]) * 100
            st.info(f"**{i+1}. {label}** 발견! (확신도: {conf:.1f}%)")
            st.progress(conf / 100)
    else:
        st.warning("🧐 음... 아무것도 찾지 못했어요.")
        st.write("💡 **팁:** 아래 슬라이더를 왼쪽으로 밀어서 AI가 '조금이라도 의심되면 다 찾아봐!'라고 시켜보세요.")

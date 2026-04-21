import streamlit as st
import sys, os
import io
import re
import json
from PIL import Image, ImageDraw
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# utils.auth 모듈은 기존 환경에 맞춰 구성되어 있다고 가정합니다.
from utils.auth import check_login, get_username
from streamlit_image_coordinates import streamlit_image_coordinates

# ── 설정 및 세션 초기화 ──
st.set_page_config(page_title="비전 AI 마스터", page_icon="🔍", layout="wide")
check_login()
username = get_username()

# 아래 변수 선언 시 공백을 표준 공백으로 수정했습니다.
SYSTEM_FOLDER_ID = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"
TRAIN_IMG_ID = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"
TRAIN_LBL_ID = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"
USERS_FILE = "users.json"

# ── YOLO 모델 로드 함수 (캐싱) ──
YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except:
    pass

@st.cache_resource
def load_yolo_model():
    if not YOLO_AVAILABLE:
        return None
    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "best.pt")
    if not os.path.exists(model_path):
        model_path = "best.pt"
    if not os.path.exists(model_path):
        return None
    try:
        model = YOLO(model_path)
        model.to('cpu')
        return model
    except:
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

# ── 앱 메인 화면 ──
st.title("🔍 비전 AI: 컴퓨터의 똑똑한 눈")
st.markdown(f"학생 이름: **{username}**")
st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📖 이론 학습", "📝 퀴즈", "📸 데이터 수집", "🤖 AI 실습"])

# ════════ 탭1: 이론 학습 ════════
with tab1:
    st.header("📖 비전 AI가 무엇일까요?")
    with st.expander("1️⃣ 컴퓨터 비전이란?", expanded=True):
        st.markdown("컴퓨터 비전은 컴퓨터에게 **'시각(눈)'**과 **'이해력(뇌)'**을 주는 기술이에요.")
    with st.expander("2️⃣ 객체 탐지(Object Detection)란?"):
        st.markdown("물체가 **'무엇'**인지 맞히고, **'어디'**에 있는지 박스를 그려 찾는 기술이에요.")

# ════════ 탭2: 퀴즈 ════════
with tab2:
    st.header("📝 비전 AI 실력 테스트")
    QUIZZES = [
        {
            "q": "이미지에서 물체의 위치를 박스로 찾아내는 기술은?",
            "options": ["이미지 생성", "객체 탐지(Object Detection)", "음성 변환", "글자 읽기"],
            "answer": "객체 탐지(Object Detection)",
            "explain": "객체 탐지는 위치와 종류를 동시에 찾아냅니다."
        }
    ]
    for i, quiz in enumerate(QUIZZES):
        st.markdown(f"**Q{i+1}. {quiz['q']}**")
        st.radio("답을 선택하세요", quiz['options'], key=f"vision_q_{i}", index=None)

# ════════ 탭4: AI 실습 ════════
with tab4:
    st.header("🤖 완성된 AI로 분석해보기")
    model = load_yolo_model()
    if model:
        test_file = st.file_uploader("분석하고 싶은 사진을 올려보세요", type=['jpg','jpeg','png'])
        if test_file:
            img_pil = Image.open(test_file).convert("RGB")
            st.image(img_pil, caption="업로드된 이미지", width=400)
            
            conf_val = st.slider("AI의 확신 점수(신뢰도) 임계값", 0.01, 0.9, 0.25, 0.01)
            
            if st.button("🚀 분석 시작", type="primary", use_container_width=True):
                with st.spinner("🤖 분석 중..."):
                    img_input = img_pil.resize((640, 640))
                    results = model.predict(img_input, conf=conf_val, verbose=False)
                    res = results[0]
                    
                    img_result = img_input.copy()
                    draw = ImageDraw.Draw(img_result)
                    if len(res.boxes) > 0:
                        for box in res.boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                            label = model.names[int(box.cls[0])]
                            draw.rectangle([x1, y1, x2, y2], outline="#00FF00", width=3)
                        st.image(img_result, caption="분석 결과")
                        st.success(f"✅ {len(res.boxes)}개를 찾았습니다!")
                    else:
                        st.warning("찾은 사물이 없습니다.")

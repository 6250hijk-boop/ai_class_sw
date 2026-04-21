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

SYSTEM_FOLDER_ID = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"
TRAIN_IMG_ID     = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"
TRAIN_LBL_ID     = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"
USERS_FILE       = "users.json"

# ── CSS 커스텀 (로딩 애니메이션) ──
st.markdown("""
<style>
div[data-testid="stSpinner"] {
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(3px);
    border-radius: 15px;
}
</style>
""", unsafe_allow_html=True)

# ── YOLO 모델 로드 함수 (캐싱) ──
YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except: pass

@st.cache_resource
def load_yolo_model():
    if not YOLO_AVAILABLE: return None
    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "best.pt")
    if not os.path.exists(model_path): model_path = "best.pt"
    if not os.path.exists(model_path): return None
    try:
        model = YOLO(model_path)
        model.to('cpu')
        return model
    except: return None

# ── 구글 드라이브 서비스 (생략된 도우미 함수들 포함) ──
def get_drive_service():
    info = st.secrets["google_oauth"]
    creds = Credentials(token=None, refresh_token=info["refresh_token"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=info["client_id"], client_secret=info["client_secret"],
                        scopes=['https://www.googleapis.com/auth/drive'])
    if not creds.valid: creds.refresh(Request())
    return build('drive', 'v3', credentials=creds)

# (기본적인 드라이브 파일 로드/저장 함수는 기존 로직을 유지합니다)

# ── 앱 메인 화면 ──
st.title("🔍 비전 AI: 컴퓨터의 똑똑한 눈")
st.markdown(f"학생 이름: **{username}**")
st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📖 이론 학습", "📝 퀴즈", "📸 데이터 수집", "🤖 AI 실습"])

# ════════ 탭1: 이론 학습 ════════
with tab1:
    st.header("📖 비전 AI가 무엇일까요?")
    
    with st.expander("1️⃣ 컴퓨터 비전이란?", expanded=True):
        st.markdown("""
        컴퓨터 비전은 컴퓨터에게 **'시각(눈)'**과 **'이해력(뇌)'**을 주는 기술이에요.  
        사람이 눈으로 사물을 보고 "저건 사과네!"라고 아는 것처럼, 컴퓨터도 사진 데이터를 분석해서 무엇인지 알아내는 것이죠.
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
        다른 AI들보다 훨씬 빨라서 자율주행 자동차처럼 실시간으로 빠르게 물체를 찾아야 할 때 아주 많이 쓰여요.
        """)
        # 

    with st.expander("4️⃣ 데이터 수집과 라벨링"):
        st.markdown("""
        AI가 물체를 잘 찾으려면 공부가 필요해요. 사람이 직접 사진 속 물체에 박스를 그려서 **"이게 정답이야!"**라고 알려주는 과정을 **'라벨링(Labeling)'**이라고 불러요.  
        여러분이 정성껏 그린 박스 하나하나가 AI를 똑똑하게 만든답니다.
        """)
        # 

[Image of data labeling for machine learning]


# ════════ 탭2: 퀴즈 ════════
with tab2:
    st.header("📝 비전 AI 실력 테스트")
    st.write("앞에서 배운 내용을 얼마나 잘 기억하고 있나요?")
    
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

    score = 0
    for i, quiz in enumerate(QUIZZES):
        st.markdown(f"**Q{i+1}. {quiz['q']}**")
        choice = st.radio("답을 선택하세요", quiz['options'], key=f"vision_q_{i}", index=None)
        if choice:
            if choice == quiz['answer']:
                st.success(f"✅ 정답! {quiz['explain']}")
                score += 1
            else:
                st.error(f"❌ 오답! 정답은 **{quiz['answer']}** 입니다.")
        st.divider()

# ════════ 탭3: 데이터 수집 (기존 기능 유지) ════════
with tab3:
    st.header("📸 학습 데이터 수집 및 라벨링")
    st.info("여기는 여러분이 AI의 선생님이 되어 정답을 알려주는 곳이에요!")
    # (기존의 업로드 및 라벨링 로직이 들어가는 부분입니다)

# ════════ 탭4: AI 실습 ════════
with tab4:
    st.header("🤖 완성된 AI로 분석해보기")
    model = load_yolo_model()
    
    if model:
        test_file = st.file_uploader("분석하고 싶은 사진을 올려보세요", type=['jpg','jpeg','png'])
        if test_file:
            img_pil = Image.open(test_file).convert("RGB")
            st.image(img_pil, caption="업로드된 이미지", width=400)

            # 신뢰도 설명 보강
            st.write("---")
            st.subheader("⚙️ AI 설정")
            conf_val = st.slider("AI의 확신 점수(신뢰도) 임계값", 0.01, 0.9, 0.25, 0.01)
            st.caption("낮을수록 '의심되면 다 찾아봐!', 높을수록 '확실한 것만 보여줘!'라는 뜻이에요.")

            if st.button("🚀 분석 시작", type="primary", use_container_width=True):
                with st.spinner("🤖 AI가 사진을 꼼꼼히 살펴보고 있습니다..."):
                    img_input = img_pil.resize((640, 640))
                    results = model.predict(img_input, conf=conf_val, verbose=False)
                    res = results[0]
                    
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        # 분석 결과 이미지 그리기 로직
                        img_result = img_input.copy()
                        draw = ImageDraw.Draw(img_result)
                        boxes = res.boxes
                        
                        if len(boxes) > 0:
                            for box in boxes:
                                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                                label = model.names[int(box.cls[0])]
                                conf = float(box.conf[0])
                                draw.rectangle([x1, y1, x2, y2], outline="#00FF00", width=3)
                                draw.text((x1+2, y1-20), f"{label} {conf*100:.0f}%", fill="#00FF00")
                        st.image(img_result, caption="AI 분석 결과", use_container_width=True)

                    with col2:
                        st.markdown(f"### 📊 분석 결과")
                        if len(boxes) > 0:
                            st.success(f"✅ {len(boxes)}개의 물체를 찾았어요!")
                            for i, box in enumerate(boxes):
                                label = model.names[int(box.cls[0])]
                                conf_percent = float(box.conf[0]) * 100
                                st.write(f"**{i+1}. {label}**")
                                st.progress(conf_percent / 100)
                                st.caption(f"확신도: {conf_percent:.1f}%")
                        else:
                            st.warning("🧐 아무것도 찾지 못했어요.")
                            st.write("슬라이더를 왼쪽으로 밀어 '임계값'을 낮춘 뒤 다시 시도해 보세요!")
    else:
        st.error("모델(best.pt)을 로드할 수 없습니다. 파일을 확인해 주세요.")

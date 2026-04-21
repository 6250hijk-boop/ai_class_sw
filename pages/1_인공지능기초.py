import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_login, get_username
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import json
import time

st.set_page_config(page_title="인공지능 기초 학습", page_icon="🧠", layout="wide")
check_login()
username = get_username()

SYSTEM_FOLDER_ID  = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"
QUIZ_RESULTS_FILE = "quiz_results.json"

# ── 구글 드라이브 서비스 설정 ──
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

def load_quiz_results():
    try:
        svc = get_drive_service()
        query = f"name='{QUIZ_RESULTS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
        files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
        if not files: return {}
        data = svc.files().get_media(fileId=files[0]['id']).execute()
        return json.loads(data.decode('utf-8'))
    except: return {}

def save_quiz_result(username, quiz_name, score, total, wrong_list):
    try:
        svc = get_drive_service()
        results = load_quiz_results()
        if username not in results: results[username] = {}
        if quiz_name not in results[username]: results[username][quiz_name] = []

        results[username][quiz_name].append({
            "score": score, "total": total, "wrong": wrong_list,
            "date": time.strftime('%Y-%m-%d %H:%M')
        })
        content = json.dumps(results, ensure_ascii=False, indent=2).encode('utf-8')
        media = MediaInMemoryUpload(content, mimetype='application/json')
        query = f"name='{QUIZ_RESULTS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
        files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
        if files: svc.files().update(fileId=files[0]['id'], media_body=media).execute()
        else: svc.files().create(body={'name': QUIZ_RESULTS_FILE, 'parents': [SYSTEM_FOLDER_ID]}, media_body=media).execute()
        return True
    except Exception as e:
        st.error(f"결과 저장 실패: {e}")
        return False

# ── 퀴즈 데이터 (이론 학습과 연동) ──
QUIZZES = [
    {
        "q": "컴퓨터에게 정답(라벨)이 포함된 데이터를 주고 학습시키는 방식은 무엇인가요?",
        "options": ["비지도학습", "지도학습", "강화학습", "전이학습"],
        "answer": "지도학습",
        "explain": "선생님이 정답을 알려주듯 학습시키는 방식이 '지도학습'입니다."
    },
    {
        "q": "정답 없이 데이터의 특징만을 보고 비슷한 것끼리 그룹을 만드는 방식은?",
        "options": ["지도학습", "군집화(비지도학습)", "회귀 분석", "딥러닝"],
        "answer": "군집화(비지도학습)",
        "explain": "정답 없이 끼리끼리 묶는 방식을 비지도학습의 '군집화'라고 합니다."
    },
    {
        "q": "머신러닝 모델을 만들기 위한 5단계 과정 중 첫 번째 단계는?",
        "options": ["모델 학습", "데이터 수집", "결과 평가", "인공지능 배포"],
        "answer": "데이터 수집",
        "explain": "학습을 위한 재료인 '데이터'를 모으는 것이 가장 먼저 할 일입니다."
    },
    {
        "q": "AI가 전체 학습 데이터를 한 번 다 훑어보는 학습 단위를 무엇이라 하나요?",
        "options": ["Step", "Batch", "에포크(Epoch)", "Layer"],
        "answer": "에포크(Epoch)",
        "explain": "문제집 전체를 한 번 다 푸는 단위를 '에포크'라고 부릅니다."
    },
    {
        "q": "학습 데이터에만 너무 과하게 적응되어 새로운 데이터는 잘 못 맞히는 현상은?",
        "options": ["과소적합", "정상학습", "과적합(Overfitting)", "정규화"],
        "answer": "과적합(Overfitting)",
        "explain": "문제집의 정답만 달달 외워서 응용력이 떨어지는 것을 '과적합'이라고 합니다."
    },
]

# ── 세션 초기화 ──
if "ml_answers" not in st.session_state: st.session_state.ml_answers = {}
if "ml_submitted" not in st.session_state: st.session_state.ml_submitted = False
if "ml_saved" not in st.session_state: st.session_state.ml_saved = False

# ── UI 시작 ──
st.title("🧠 인공지능(AI) 기초 마스터")
st.markdown(f"학생 이름: **{username}**")

tab1, tab2, tab3 = st.tabs(["📖 핵심 이론 공부", "📝 도전! 퀴즈", "💻 AI 체험"])

# ════════ 탭1: 이론 학습 ════════
with tab1:
    st.header("📖 머신러닝의 기본 원리")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("### 1. 지도학습 (정답이 있어요)\n"
                "선생님이 **문제와 정답(라벨)**을 함께 보여주며 공부시키는 방법이에요.\n"
                "- **사례:** 개/고양이 사진 분류, 스팸 메일 판별\n"
                "- **포인트:** 정답을 보고 배우기 때문에 정확도가 높아요.")
    with col2:
        st.success("### 2. 비지도학습 (정답이 없어요)\n"
                "정답 없이 데이터만 주고 **'비슷한 것끼리 묶어봐'**라고 시키는 방법이에요.\n"
                "- **사례:** 넷플릭스 영화 추천, 고객 그룹 나누기\n"
                "- **포인트:** 데이터 속에 숨겨진 규칙을 발견해요.")

    st.markdown("---")
    st.subheader("🚀 인공지능이 만들어지는 5단계")
    st.write("인공지능은 마치 학생이 시험을 준비하는 과정과 같아요!")
    
    steps = [
        "**1단계: 데이터 수집** (공부할 문제집 모으기)",
        "**2단계: 모델 학습** (문제집 열심히 풀며 공부하기)",
        "**3단계: 모델 평가** (모의고사 풀어서 실력 확인하기)",
        "**4단계: 평가 및 수정** (틀린 문제 분석하고 오답노트 쓰기)",
        "**5단계: 배포** (실제 시험 보러 가기 / 서비스 출시)"
    ]
    for step in steps:
        st.write(step)

    st.markdown("---")
    st.subheader("⚠️ 인공지능 학습 용어 사전")
    with st.expander("에포크(Epoch)란 무엇인가요?"):
        st.write("문제집 전체를 **한 번 다 푼 것**을 의미해요. 에포크가 10이면 전체 문제를 10번 반복해서 학습했다는 뜻이죠.")
    
    with st.expander("과적합(Overfitting)이란 무엇인가요?"):
        st.write("학습용 문제집의 정답을 통째로 외워버린 상태예요! 문제집은 100점 맞지만, **새로운 문제(실전)에서는 빵점**을 맞는 현상이죠.")

# ════════ 탭2: 퀴즈 ════════
with tab2:
    st.header("📝 실력 확인 퀴즈")
    if st.session_state.ml_submitted:
        st.info("학습을 마쳤습니다. 결과를 확인하세요!")
    else:
        st.write("앞의 이론 내용을 잘 읽었다면 모두 맞힐 수 있어요!")

    for i, quiz in enumerate(QUIZZES):
        st.markdown(f"**Q{i+1}. {quiz['q']}**")
        choice = st.radio("보기", quiz['options'], key=f"ml_q_{i}", index=None, 
                          disabled=st.session_state.ml_submitted)
        
        if choice: st.session_state.ml_answers[i] = choice

        if st.session_state.ml_submitted:
            if st.session_state.ml_answers.get(i) == quiz['answer']:
                st.success("✅ 정답입니다!")
            else:
                st.error(f"❌ 오답입니다. (정답: {quiz['answer']})")
                st.write(f"💡 해설: {quiz['explain']}")
        st.divider()

    if not st.session_state.ml_submitted:
        if st.button("제출하고 점수 확인", type="primary", use_container_width=True):
            if len(st.session_state.ml_answers) < len(QUIZZES):
                st.warning("모든 문제를 풀어주세요!")
            else:
                st.session_state.ml_submitted = True
                st.rerun()

    if st.session_state.ml_submitted:
        score = sum(1 for i, q in enumerate(QUIZZES) if st.session_state.ml_answers.get(i) == q['answer'])
        st.subheader(f"내 점수: {int(score/len(QUIZZES)*100)}점 ({score}/{len(QUIZZES)})")
        
        if not st.session_state.ml_saved:
            save_quiz_result(username, "ML_기초", score, len(QUIZZES), [])
            st.session_state.ml_saved = True

        if st.button("다시 도전하기"):
            st.session_state.ml_submitted = False
            st.session_state.ml_answers = {}
            st.session_state.ml_saved = False
            st.rerun()

# ════════ 탭3: 실습 ════════
with tab3:
    st.header("💻 간단 AI 체험")
    st.write("에포크(학습 횟수)를 조절하며 AI의 마음을 이해해 봅시다.")
    
    epochs = st.slider("학습 횟수(Epochs)를 설정해 보세요", 1, 100, 10)
    
    if epochs < 10:
        st.warning(f"에포크 {epochs}: 아직 공부가 부족해요! (과소적합 위험)")
    elif epochs > 80:
        st.error(f"에포크 {epochs}: 너무 정답을 외우고 있어요! (과적합 위험)")
    else:
        st.success(f"에포크 {epochs}: 적절하게 공부하고 있습니다! (정상 학습)")
    
    st.markdown("""
    ---
    **실제 실습 가이드:**
    1. **Teachable Machine**에 접속합니다.
    2. 지도학습을 이용해 나의 얼굴과 손동작을 학습시켜 봅니다.
    3. 학습이 완료된 후 AI가 나를 잘 알아보는지 확인해 봅시다.
    """)

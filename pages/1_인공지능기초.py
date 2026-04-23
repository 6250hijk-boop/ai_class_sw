import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_login, get_username
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.firebase import get_db
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import json
import time

st.set_page_config(page_title="인공지능기초", page_icon="🧠", layout="wide")
check_login()
username = get_username()


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

def save_quiz_result(username, quiz_name, score, total, wrong_list):
    try:
        db = get_db()
        doc_ref = db.collection("quiz_results").document(username)
        doc = doc_ref.get()
        results = doc.to_dict() if doc.exists else {}

        if quiz_name not in results:
            results[quiz_name] = []

        results[quiz_name].append({
            "score": score,
            "total": total,
            "wrong": wrong_list,
            "date": time.strftime('%Y-%m-%d %H:%M')
        })
        doc_ref.set(results)
        return True
    except Exception as e:
        st.error(f"결과 저장 실패: {e}")
        return False

# ── 퀴즈 데이터 ──
QUIZZES = [
    {
        "q": "머신러닝에서 정답이 붙은 데이터로 학습하는 방식은?",
        "options": ["비지도학습", "지도학습", "강화학습", "딥러닝"],
        "answer": "지도학습",
        "explain": "지도학습은 정답(라벨)이 있는 데이터로 컴퓨터를 학습시키는 방식으로, 스팸 메일 분류나 이미지 분류 등에 사용됩니다."
    },
    {
        "q": "정답 없이 비슷한 것끼리 묶는 머신러닝 방식은?",
        "options": ["지도학습", "강화학습", "비지도학습", "전이학습"],
        "answer": "비지도학습",
        "explain": "비지도학습은 정답 없이 데이터의 패턴을 스스로 찾아 분류하는 방식으로, 넷플릭스 추천 시스템 등에 사용됩니다."
    },
    {
        "q": "머신러닝 모델 학습 과정에서 가장 먼저 해야 할 것은?",
        "options": ["모델 배포", "데이터 수집", "모델 평가", "예측"],
        "answer": "데이터 수집",
        "explain": "모델 학습을 위해서는 먼저 충분한 데이터를 수집해야 합니다. 데이터가 없으면 학습 자체가 불가능합니다."
    },
    {
        "q": "에포크(Epoch)란 무엇인가요?",
        "options": [
            "모델의 크기",
            "전체 데이터를 한 번 학습하는 단위",
            "학습 속도",
            "데이터의 양"
        ],
        "answer": "전체 데이터를 한 번 학습하는 단위",
        "explain": "에포크는 AI가 전체 학습 데이터를 한 번 다 보는 것을 말해요. 100 에포크면 같은 데이터를 100번 반복 학습한 것입니다."
    },
    {
        "q": "모델이 학습 데이터에만 너무 맞춰져서 새로운 데이터에는 성능이 떨어지는 현상은?",
        "options": ["과소적합", "과적합(Overfitting)", "정규화", "전처리"],
        "answer": "과적합(Overfitting)",
        "explain": "과적합은 모델이 학습 데이터만 외워버려 새로운 데이터에 잘 대응하지 못하는 현상입니다. 에포크가 너무 많거나 데이터가 적을 때 발생합니다."
    },
]

# ── 세션 초기화 ──
if "ml_answers" not in st.session_state:
    st.session_state.ml_answers = {}
if "ml_submitted" not in st.session_state:
    st.session_state.ml_submitted = False
if "ml_saved" not in st.session_state:
    st.session_state.ml_saved = False

# ── UI ──
st.title("🧠 인공지능 기초")
st.markdown(f"👤 **{username}**")
st.divider()

tab1, tab2, tab3 = st.tabs(["📖 이론 학습", "📝 퀴즈", "💻 실습"])

# ════════ 탭1: 이론 ════════
with tab1:
    st.header("📖 머신러닝 이론")

    with st.expander("1️⃣ 머신러닝이란?", expanded=True):
        st.markdown("""
머신러닝은 **'기계(Machine)가 스스로 학습(Learning)하는 것'** 을 말해요.
사람이 규칙을 정해주는 대신, 컴퓨터에게 엄청나게 많은 데이터를 보여주면
컴퓨터가 그 안에서 스스로 규칙을 찾아내는 기술이죠.

요리법(레시피)을 하나하나 읽어주는 게 아니라, 수천 가지의 완성된 요리를 맛보게 해서
컴퓨터가 스스로 "아, 설탕이 들어가면 달콤해지는구나!"라고 깨닫게 만드는 것과 같아요.
        """)

    with st.expander("2️⃣ 지도학습 vs 비지도학습"):
        st.markdown("""
**지도학습 (Supervised Learning): "정답지가 있는 공부"**

선생님이 옆에서 문제와 정답을 같이 알려주며 공부시키는 방식이에요.
- **학습법:** "이 사진은 강아지야", "이 사진은 고양이야"라고 이름(정답)이 붙은 사진을 수만 장 보여줍니다.
- **결과:** 나중에 이름이 없는 새 사진을 보여주면, 컴퓨터가 "이건 99% 확률로 고양이네요!"라고 정답을 맞혀요.
- **예시:** 스팸 메일 분류, 시험 합격/불합격 예측.

---

**비지도학습 (Unsupervised Learning): "정답 없이 끼리끼리 모으기"**

정답을 알려주지 않고, 컴퓨터에게 **"비슷한 것끼리 한번 묶어봐"** 라고 시키는 방식이에요.
- **학습법:** 과일이 잔뜩 섞인 바구니를 주고 이름은 안 알려줍니다.
- **결과:** 사람이 알려주지 않은 새로운 특징이나 그룹을 찾아낼 때 유용해요.
- **예시:** 넷플릭스의 비슷한 영화 추천, 비슷한 취미를 가진 사람들의 모임 찾기.
        """)

    with st.expander("3️⃣ 모델 학습 과정"):
        st.markdown("""
컴퓨터가 똑똑한 '모델'이 되는 과정은 우리가 기말고사를 준비하는 과정과 아주 비슷해요.

1. **문제집 준비 (데이터 수집):** 공부할 문제들을 많이 모아요.
2. **공부하기 (모델 학습):** 문제집을 열심히 풀면서 규칙을 찾아요.
3. **모의고사 풀기 (예측/테스트):** 공부가 잘 됐는지 확인하기 위해 정답을 가리고 문제를 풀어봐요.
4. **채점 및 오답노트 (평가 및 수정):** 틀린 문제를 분석하고, 규칙을 다시 수정해서 더 똑똑해지도록 반복해요.
5. **실전 시험 (배포):** 충분히 똑똑해졌다면, 실제로 세상에 나가서 일을 시작해요.
        """)

# ════════ 탭2: 퀴즈 ════════
with tab2:
    st.header("📝 머신러닝 퀴즈")
    st.markdown(f"총 **{len(QUIZZES)}문제** — 모두 풀고 **정답 확인** 버튼을 누르세요!")
    st.divider()

    # 문제 표시
    for i, quiz in enumerate(QUIZZES):
        st.markdown(f"**Q{i+1}. {quiz['q']}**")

        # 제출 후엔 비활성화
        disabled = st.session_state.ml_submitted
        choice = st.radio(
            "답을 선택하세요",
            quiz['options'],
            key=f"ml_quiz_{i}",
            index=None,
            disabled=disabled
        )
        if choice:
            st.session_state.ml_answers[i] = choice

        # 제출 후 정답/오답 표시
        if st.session_state.ml_submitted:
            if st.session_state.ml_answers.get(i) == quiz['answer']:
                st.success(f"✅ 정답!")
            else:
                st.error(f"❌ 오답! 정답: **{quiz['answer']}**")
                st.info(f"💡 해설: {quiz['explain']}")
        st.divider()

    # 정답 확인 버튼
    if not st.session_state.ml_submitted:
        answered_count = len(st.session_state.ml_answers)
        st.write(f"답변 완료: **{answered_count} / {len(QUIZZES)}**")

        if answered_count < len(QUIZZES):
            st.warning("⚠️ 모든 문제에 답해야 제출할 수 있어요!")

        if st.button("✅ 정답 확인", type="primary",
                     use_container_width=True,
                     disabled=answered_count < len(QUIZZES)):
            st.session_state.ml_submitted = True
            st.session_state.ml_saved = False
            st.rerun()

    # 결과 표시
    if st.session_state.ml_submitted:
        score = sum(
            1 for i, q in enumerate(QUIZZES)
            if st.session_state.ml_answers.get(i) == q['answer']
        )
        wrong_list = [
            QUIZZES[i]['q'] for i in range(len(QUIZZES))
            if st.session_state.ml_answers.get(i) != QUIZZES[i]['answer']
        ]
        total = len(QUIZZES)
        wrong_count = total - score

        st.divider()
        st.markdown("## 📊 퀴즈 결과")

        col1, col2, col3 = st.columns(3)
        col1.metric("✅ 맞힌 문제", f"{score}개")
        col2.metric("❌ 틀린 문제", f"{wrong_count}개")
        col3.metric("📊 점수", f"{int(score/total*100)}점")

        if score == total:
            st.balloons()
            st.success("🎉 만점입니다! 완벽해요!")
        elif score >= total * 0.8:
            st.success(f"👍 잘했어요! {wrong_count}문제 틀렸어요.")
        elif score >= total * 0.6:
            st.warning(f"😅 조금 더 공부해봐요! {wrong_count}문제 틀렸어요.")
        else:
            st.error(f"😢 이론을 다시 공부해봐요! {wrong_count}문제 틀렸어요.")

        # 결과 저장
        if not st.session_state.ml_saved:
            with st.spinner("결과 저장 중..."):
                ok = save_quiz_result(username, "머신러닝기초", score, total, wrong_list)
            if ok:
                st.session_state.ml_saved = True

        # 다시 풀기 버튼
        if st.button("🔄 다시 풀기", use_container_width=True):
            st.session_state.ml_answers  = {}
            st.session_state.ml_submitted = False
            st.session_state.ml_saved    = False
            for i in range(len(QUIZZES)):
                if f"ml_quiz_{i}" in st.session_state:
                    del st.session_state[f"ml_quiz_{i}"]
            st.rerun()

# ════════ 탭3: 실습 ════════
with tab3:
    st.header("💻 머신러닝 실습")
    st.info("✏️ 실습 내용을 추가하세요.")
    st.markdown("""
**실습 예시 아이디어:**
- scikit-learn으로 간단한 분류기 만들기
- 붓꽃(iris) 데이터셋 분류 실습
- 모델 정확도 시각화
    """)

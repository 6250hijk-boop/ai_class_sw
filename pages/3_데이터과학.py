import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_login, get_username

st.set_page_config(page_title="빅데이터", page_icon="📊", layout="wide")
check_login()
username = get_username()

st.title("📊 빅데이터 분석")
st.markdown(f"👤 **{username}**")
st.divider()

tab1, tab2, tab3 = st.tabs(["📖 이론 학습", "📝 퀴즈", "💻 실습"])

with tab1:
    st.header("📖 빅데이터 이론")
    with st.expander("1️⃣ 빅데이터란?", expanded=True):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")
    with st.expander("2️⃣ 데이터 수집과 전처리"):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")
    with st.expander("3️⃣ 데이터 시각화"):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")

with tab2:
    st.header("📝 빅데이터 퀴즈")
    st.info("✏️ 퀴즈 내용을 추가하세요.")

    QUIZZES = [
        {
            "q": "✏️ 퀴즈 1 내용을 입력하세요",
            "options": ["보기1", "보기2", "보기3", "보기4"],
            "answer": "보기1",
            "explain": "해설을 입력하세요."
        },
    ]

    score = 0
    for i, quiz in enumerate(QUIZZES):
        st.markdown(f"**Q{i+1}. {quiz['q']}**")
        choice = st.radio("답을 선택하세요", quiz['options'], key=f"bd_quiz_{i}", index=None)
        if choice:
            if choice == quiz['answer']:
                st.success(f"✅ 정답! {quiz['explain']}")
                score += 1
            else:
                st.error(f"❌ 오답! 정답은 **{quiz['answer']}** 입니다.")
        st.divider()

with tab3:
    st.header("💻 빅데이터 실습")
    st.info("✏️ 실습 내용을 추가하세요.")
    st.markdown("""
    **실습 예시 아이디어:**
    - CSV 파일 업로드 후 데이터 분석
    - 차트 시각화 (Plotly, Matplotlib)
    - 기초 통계 계산
    """)

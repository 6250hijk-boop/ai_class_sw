import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_login, get_username

st.set_page_config(page_title="머신러닝", page_icon="🤖", layout="wide")
check_login()
username = get_username()

st.title("🤖 머신러닝 기초")
st.markdown(f"👤 **{username}**")
st.divider()

tab1, tab2, tab3 = st.tabs(["📖 이론 학습", "📝 퀴즈", "💻 실습"])

with tab1:
    st.header("📖 머신러닝 이론")
    with st.expander("1️⃣ 머신러닝이란?", expanded=True):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")
    with st.expander("2️⃣ 지도학습 vs 비지도학습"):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")
    with st.expander("3️⃣ 모델 학습 과정"):
        st.markdown("> ✏️ **여기에 이론 내용을 추가하세요**")

with tab2:
    st.header("📝 머신러닝 퀴즈")
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
        choice = st.radio("답을 선택하세요", quiz['options'], key=f"ml_quiz_{i}", index=None)
        if choice:
            if choice == quiz['answer']:
                st.success(f"✅ 정답! {quiz['explain']}")
                score += 1
            else:
                st.error(f"❌ 오답! 정답은 **{quiz['answer']}** 입니다.")
        st.divider()

with tab3:
    st.header("💻 머신러닝 실습")
    st.info("✏️ 실습 내용을 추가하세요.")
    st.markdown("""
    **실습 예시 아이디어:**
    - scikit-learn으로 간단한 분류기 만들기
    - 붓꽃(iris) 데이터셋 분류 실습
    - 모델 정확도 시각화
    """)

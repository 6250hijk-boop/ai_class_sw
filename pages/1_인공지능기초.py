import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_login, get_username

st.set_page_config(page_title="머신러닝", page_icon="🤖", layout="wide")
check_login()
username = get_username()

st.title("📊 빅데이터 분석")
st.markdown(f"👤 **{username}**")
st.divider()

tab1, tab2, tab3 = st.tabs(["📖 이론 학습", "📝 퀴즈", "💻 실습"])

with tab1:
    st.header("📖 머신러닝 이론")
    with st.expander("1️⃣ 머신러닝이란?", expanded=True):
        st.markdown("하지만 머신러닝은 달라요.
머신러닝은 '기계(Machine)가 스스로 학습(Learning)하는 것'을 말해요. 사람이 규칙을 정해주는 대신, 컴퓨터에게 엄청나게 많은 데이터를 보여주면 컴퓨터가 그 안에서 스스로 규칙을 찾아내는 기술이죠.
요리법(레시피)을 하나하나 읽어주는 게 아니라, 수천 가지의 완성된 요리를 맛보게 해서 컴퓨터가 스스로 "아, 설탕이 들어가면 달콤해지는구나!"라고 깨닫게 만드는 것과 같아요.")
    with st.expander("2️⃣ 지도학습 vs 비지도학습"):
        st.markdown("지도학습 (Supervised Learning): "정답지가 있는 공부"
선생님이 옆에서 문제와 정답을 같이 알려주며 공부시키는 방식이에요.
학습법: "이 사진은 강아지야", "이 사진은 고양이야"라고 이름(정답)이 붙은 사진을 수만 장 보여줍니다.
결과: 나중에 이름이 없는 새 사진을 보여주면, 컴퓨터가 "이건 99% 확률로 고양이네요!"라고 정답을 맞혀요.
예시: 스팸 메일 분류, 시험 합격/불합격 예측.

비지도학습 (Unsupervised Learning): "정답 없이 끼리끼리 모으기"
정답을 알려주지 않고, 컴퓨터에게 **"비슷한 것끼리 한번 묶어봐"**라고 시키는 방식이에요.
학습법: 과일이 잔뜩 섞인 바구니를 주고 이름은 안 알려줍니다. 그러면 컴퓨터는 모양, 색깔, 질감을 보고 "동그랗고 빨간 것들", "길쭉하고 노란 것들"끼리 알아서 분류해요.
결과: 사람이 알려주지 않은 새로운 특징이나 그룹을 찾아낼 때 유용해요.
예시: 넷플릭스의 비슷한 영화 추천, 비슷한 취미를 가진 사람들의 모임 찾기.*")
    with st.expander("3️⃣ 모델 학습 과정"):
        st.markdown("컴퓨터가 똑똑한 '모델'이 되는 과정은 우리가 기말고사를 준비하는 과정과 아주 비슷해요.
문제집 준비 (데이터 수집): 공부할 문제들을 많이 모아요. (예: 개와 고양이 사진 수만 장)
공부하기 (모델 학습): 문제집을 열심히 풀면서 규칙을 찾아요. "귀가 뾰족하면 고양이일 확률이 높네?" 같은 규칙을 컴퓨터가 스스로 만들어요.
모의고사 풀기 (예측/테스트): 공부가 잘 됐는지 확인하기 위해, 정답을 가리고 문제를 풀어봐요.
채점 및 오답노트 (평가 및 수정): 틀린 문제가 있다면 왜 틀렸는지 분석하고, 규칙을 다시 수정해서 더 똑똑해지도록 반복해요.
실전 시험 (배포): 이제 충분히 똑똑해졌다면, 실제로 세상에 나가서 사람들의 질문에 답하거나 사진을 분류하는 일을 시작해요.")

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

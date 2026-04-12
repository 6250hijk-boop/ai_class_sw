import streamlit as st
import cv2  # 색상 변환을 위해 필요합니다
from ultralytics import YOLO
from PIL import Image
import os

# (앞부분 코드 생략...)

# --- 3. AI 모델 분석 탭 수정 부분 ---
elif menu == MENU_3:
    st.header("🔍 AI 사물 분석 및 정확도 확인")
    model_path = "best.pt"
    
    model = load_yolo_model(model_path)
    
    if model is None:
        st.warning("⚠️ GitHub에 best.pt 파일을 먼저 업로드해주세요.")
    else:
        test_file = st.file_uploader("분석할 사진을 업로드하세요", type=['jpg', 'jpeg', 'png'])
        
        if test_file:
            img_pil = Image.open(test_file).convert("RGB")
            
            if st.button("🚀 분석 실행"):
                with st.spinner("AI가 분석 중입니다..."):
                    results = model(img_pil)
                    res = results[0]
                    
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.subheader("🖼️ 분석 결과 이미지")
                        
                        # [핵심 수정] res.plot()은 BGR 배열을 반환합니다. 
                        # 이를 RGB로 바꿔줘야 색깔이 정상으로 나옵니다.
                        res_bgr = res.plot()
                        res_rgb = cv2.cvtColor(res_bgr, cv2.COLOR_BGR2RGB)
                        
                        st.image(res_rgb, use_column_width=True)
                    
                    with col2:
                        st.subheader("📊 검출 데이터")
                        if len(res.boxes) > 0:
                            st.write(f"총 **{len(res.boxes)}개**의 사물을 찾았습니다.")
                            for i, box in enumerate(res.boxes):
                                cls_id = int(box.cls[0])
                                label = model.names[cls_id]
                                conf = float(box.conf[0]) * 100
                                st.info(f"**[{i+1}] {label}**\n\n정확도: **{conf:.1f}%**")
                                st.progress(conf / 100)
                        else:
                            st.error("검출된 사물이 없습니다. 학습 데이터의 색상과 일치하는지 확인해보세요.")

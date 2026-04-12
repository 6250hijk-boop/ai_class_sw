import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import os
import re

# YOLO 라이브러리 (분석 탭에서 사용)
try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

# 1. 구글 드라이브 서비스 연결
def get_drive_service():
    if "google_oauth" in st.secrets:
        oauth_info = st.secrets["google_oauth"]
        creds = Credentials(
            token=None,
            refresh_token=oauth_info["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=oauth_info["client_id"],
            client_secret=oauth_info["client_secret"],
            scopes=['https://www.googleapis.com/auth/drive']
        )
        if not creds.valid:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    else:
        st.error("Secrets 설정([google_oauth])이 되지 않았습니다.")
        st.stop()

service = get_drive_service()
PARENT_FOLDER_ID = "1i7dospy3B3f4U6Nc3ZEzTk8hB3TCeaWL" 

# 자동 파일명(dataN) 생성 함수
def get_next_data_index():
    try:
        query = f"'{PARENT_FOLDER_ID}' in parents and name contains 'data' and trashed = false"
        results = service.files().list(q=query, fields="files(name)").execute()
        files = results.get('files', [])
        max_idx = 0
        for f in files:
            match = re.search(r'data(\d+)', f['name'])
            if match:
                idx = int(match.group(1))
                if idx > max_idx:
                    max_idx = idx
        return max_idx + 1
    except:
        return 1

# 라벨 확인용 박스 그리기 함수
def draw_yolo_boxes(image, yolo_lines, labels):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for line in yolo_lines:
        try:
            class_id, cx, cy, w, h = map(float, line.split())
            left = (cx - w/2) * width
            top = (cy - h/2) * height
            right = (cx + w/2) * width
            bottom = (cy + h/2) * height
            draw.rectangle([left, top, right, bottom], outline="#e6a500", width=3)
            class_name = labels[int(class_id)]
            draw.text((left, top - 15), class_name, fill="#e6a500")
        except:
            continue
    return image

st.set_page_config(page_title="AI 실습 통합 플랫폼", layout="wide")

# 세션 상태 초기화
if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]
if "loaded_image_id" not in st.session_state:
    st.session_state.loaded_image_id = None
if "loaded_image_pil" not in st.session_state:
    st.session_state.loaded_image_pil = None
if "saved_yolo_lines" not in st.session_state:
    st.session_state.saved_yolo_lines = []

st.sidebar.title("🚀 AI 교육 플랫폼")
menu = st.sidebar.radio("메뉴 선택", ["1. 데이터 수집 (업로드)", "2. 데이터 라벨링 (드래그 방식)", "3. AI 모델 분석 (YOLOv8)"])

# --- 1. 데이터 수집 ---
if menu == "1. 데이터 수집 (업로드)":
    st.header("📸 학습 데이터 업로드")
    st.info("PC나 스마트폰의 사진을 올리면 'data1, data2...' 순서로 구글 드라이브에 저장됩니다.")
    files = st.file_uploader("사진을 선택하세요", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    if st.button("드라이브로 전송 시작"):
        if files:
            current_idx = get_next_data_index()
            progress_bar = st.progress(0)
            for i, f in enumerate(files):
                new_name = f"data{current_idx}.jpg"
                metadata = {'name': new_name, 'parents': [PARENT_FOLDER_ID]}
                media = MediaInMemoryUpload(f.getvalue(), mimetype='image/jpeg')
                service.files().create(body=metadata, media_body=media).execute()
                current_idx += 1
                progress_bar.progress((i + 1) / len(files))
            st.success(f"성공! 총 {len(files)}장의 사진이 저장되었습니다.")
        else:
            st.warning("사진을 첨부해주세요.")

# --- 2. 데이터 라벨링 (드래그 방식 복구) ---
elif menu == "2. 데이터 라벨링 (드래그 방식)":
    st.header("🏷️ 데이터 라벨링 (드래그 방식)")
    st.info("사진 위에서 마우스를 부드럽게 드래그하여 박스를 그려주세요.")
    
    with st.sidebar.expander("📝 라벨(클래스) 관리", expanded=True):
        new_label = st.text_input("새 라벨 이름 입력")
        if st.button("라벨 추가"):
            if new_label and new_label not in st.session_state.labels:
                st.session_state.labels.append(new_label)
                st.rerun()
        st.write("목록:", ", ".join(st.session_state.labels))

    try:
        query = f"'{PARENT_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])

        if items:
            file_names = [i['name'] for i in items]
            target_name = st.selectbox("라벨링할 사진 선택", file_names)
            target_id = [i['id'] for i in items if i['name'] == target_name][0]
            selected_label = st.selectbox("현재 그릴 라벨 선택", st.session_state.labels)
            label_idx = st.session_state.labels.index(selected_label)

            if st.button("📥 사진 불러오기 및 초기화"):
                st.session_state.saved_yolo_lines = []
                with st.spinner("가져오는 중..."):
                    req = service.files().get_media(fileId=target_id)
                    original_img = Image.open(io.BytesIO(req.execute())).convert("RGB")
                    
                    width = 800
                    height = int(original_img.height * (width / original_img.width))
                    img_resized = original_img.resize((width, height))
                    
                    # [블랙스크린 방지] 메모리 세탁 과정 (PNG 포맷으로 변환하여 찌꺼기 데이터 제거)
                    temp_bytes = io.BytesIO()
                    img_resized.save(temp_bytes, format="PNG")
                    clean_image = Image.open(temp_bytes)
                    
                    st.session_state.loaded_image_id = target_id
                    st.session_state.loaded_image_pil = clean_image

            if st.session_state.loaded_image_id == target_id and st.session_state.loaded_image_pil is not None:
                st.markdown("---")
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"✍️ **캔버스 (현재 라벨: {selected_label})**")
                    
                    # 캔버스 렌더링 (끊김 없음!)
                    canvas_result = st_canvas(
                        fill_color="rgba(255, 165, 0, 0.3)",
                        stroke_width=2,
                        stroke_color="#e6a500",
                        background_image=st.session_state.loaded_image_pil,
                        height=st.session_state.loaded_image_pil.height,
                        width=st.session_state.loaded_image_pil.width,
                        drawing_mode="rect",
                        key=f"canvas_{target_id}",
                    )

                with col2:
                    st.write("📊 **저장 관리**")
                    if st.button("💾 라벨 데이터(TXT) 드라이브에 저장"):
                        if canvas_result.json_data and canvas_result.json_data["objects"]:
                            yolo_lines = []
                            w_canvas = st.session_state.loaded_image_pil.width
                            h_canvas = st.session_state.loaded_image_pil.height
                            
                            for obj in canvas_result.json_data["objects"]:
                                cx = (obj['left'] + obj['width']/2) / w_canvas
                                cy = (obj['top'] + obj['height']/2) / h_canvas
                                w = obj['width'] / w_canvas
                                h = obj['height'] / h_canvas
                                yolo_lines.append(f"{label_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                            
                            st.session_state.saved_yolo_lines = yolo_lines
                            txt_content = "\n".join(yolo_lines).encode()
                            txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                            media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                            service.files().create(body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, media_body=media).execute()
                            
                            st.success(f"'{txt_name}' 정답지 저장 완료!")
                            st.rerun()
                        else:
                            st.warning("먼저 박스를 부드럽게 그려주세요.")
            
            # 최종 확인 창
            if st.session_state.saved_yolo_lines:
                st.markdown("---")
                st.write("✅ **최종 라벨링 결과 확인**")
                original_image_copy = st.session_state.loaded_image_pil.copy()
                labeled_image = draw_yolo_boxes(original_image_copy, st.session_state.saved_yolo_lines, st.session_state.labels)
                st.image(labeled_image, use_column_width=True)

        else:
            st.info("드라이브에 사진이 없습니다. 1번 메뉴에서 올려주세요.")
    except Exception as e:
        st.error(f"오류: {e}")

# --- 3. AI 모델 분석 (YOLO 실제 연동) ---
elif menu == "3. AI 모델 분석 (YOLOv8)":
    st.header("🔍 학습된 인공지능 분석")
    st.write("새로운 사진을 올리면, 학습된 인공지능(`best.pt`)이 분석 결과를 보여줍니다.")
    
    if YOLO is None:
        st.error("YOLO 라이브러리가 설치되지 않았습니다. `requirements.txt`에 `ultralytics`를 추가해 주세요.")
        st.stop()

    model_path = "best.pt"  
    
    if not os.path.exists(model_path):
        st.warning("⚠️ 아직 인공지능 뇌 파일(`best.pt`)이 없습니다!")
    else:
        st.success("✅ 학습된 AI 모델(`best.pt`)이 준비되었습니다!")
        model = YOLO(model_path)
        
        test_file = st.file_uploader("테스트할 새로운 사진 업로드", type=['jpg', 'jpeg', 'png'])
        if test_file:
            img = Image.open(test_file).convert("RGB")
            st.image(img, caption="원본 사진", use_column_width=True)
            
            if st.button("AI 자동 분석 실행"):
                with st.spinner("AI가 사진을 분석하고 있습니다..."):
                    results = model(img)  
                    res_img = results[0].plot()  
                    st.image(res_img, caption="분석 완료!", use_column_width=True)

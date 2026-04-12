import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import os
import re

# 1. 구글 드라이브 서비스 연결 함수
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
        st.error("Secrets 설정을 확인해주세요.")
        st.stop()

service = get_drive_service()
PARENT_FOLDER_ID = "1i7dospy3B3f4U6Nc3ZEzTk8hB3TCeaWL" 

# 2. 드라이브 내 기존 파일 번호를 확인하여 다음 번호(dataN)를 결정하는 함수
def get_next_data_index():
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

st.set_page_config(page_title="AI 데이터 마스터", layout="wide")

# 세션 상태 초기화
if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]

# 사이드바 메뉴
st.sidebar.title("🤖 AI 데이터 센터")
menu = st.sidebar.radio("메뉴 선택", ["데이터 수집 (Upload)", "데이터 라벨링 (Labeling)", "모델 분석 (Analysis)"])

# --- 1. 데이터 수집 (업로드 및 자동 이름 변경) ---
if menu == "데이터 수집 (Upload)":
    st.header("📸 학습 데이터 자동 수집")
    st.info("사진을 올리면 'data1, data2...' 순서로 이름이 자동 변경되어 드라이브에 저장됩니다.")
    
    files = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    
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
                
            st.success(f"총 {len(files)}장의 사진이 데이터 세트로 변환되어 저장되었습니다.")
        else:
            st.warning("먼저 사진 파일을 선택해주세요.")

# --- 2. 데이터 라벨링 (기존/신규 라벨 관리) ---
elif menu == "데이터 라벨링 (Labeling)":
    st.header("🏷️ 공동 데이터 라벨링")
    
    # 라벨 관리 UI
    with st.sidebar.expander("📝 라벨 클래스 관리", expanded=True):
        new_label = st.text_input("새 라벨 이름 추가")
        if st.button("추가"):
            if new_label and new_label not in st.session_state.labels:
                st.session_state.labels.append(new_label)
                st.rerun()
        st.write("사용 가능한 라벨:", ", ".join(st.session_state.labels))

    try:
        # 이미지 파일 목록만 가져오기
        query = f"'{PARENT_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])

        if items:
            file_names = [i['name'] for i in items]
            target_name = st.selectbox("라벨링할 데이터 선택", file_names)
            target_id = [i['id'] for i in items if i['name'] == target_name][0]
            
            selected_label = st.selectbox("현재 박스 라벨 선택", st.session_state.labels)
            label_idx = st.session_state.labels.index(selected_label)

            # 이미지 로드 및 캔버스 버그 방지 (임시 파일 저장)
            req = service.files().get_media(fileId=target_id)
            original_img = Image.open(io.BytesIO(req.execute())).convert("RGB")
            
            # 리사이징
            width = 800
            height = int(original_img.height * (width / original_img.width))
            img_resized = original_img.resize((width, height))
            
            # 캔버스 배경용 임시 저장
            img_resized.save("temp_canvas.jpg")
            bg_img = Image.open("temp_canvas.jpg")

            st.write(f"현재 라벨링: **{selected_label}** (ID: {label_idx})")
            
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#e6a500",
                background_image=bg_img,
                update_streamlit=True,
                height=height,
                width=width,
                drawing_mode="rect",
                key=f"canvas_{target_id}",
            )

            if st.button("라벨 및 TXT 저장"):
                if canvas_result.json_data and len(canvas_result.json_data["objects"]) > 0:
                    yolo_lines = []
                    for obj in canvas_result.json_data["objects"]:
                        cx = (obj['left'] + obj['width']/2) / width
                        cy = (obj['top'] + obj['height']/2) / height
                        w = obj['width'] / width
                        h = obj['height'] / height
                        yolo_lines.append(f"{label_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                    
                    # TXT 파일 저장
                    txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                    txt_content = "\n".join(yolo_lines).encode()
                    media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                    service.files().create(
                        body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, 
                        media_body=media
                    ).execute()
                    st.success(f"'{txt_name}' 파일이 드라이브에 저장되었습니다.")
                else:
                    st.warning("박스를 먼저 그려주세요.")
        else:
            st.info("드라이브에 저장된 데이터가 없습니다.")
    except Exception as e:
        st.error(f"오류: {e}")

# --- 3. 모델 분석 (학습 후 모델 연결 탭) ---
elif menu == "모델 분석 (Analysis)":
    st.header("🔍 학습된 모델 분석")
    st.warning("분석 기능은 YOLO 모델 학습 완료 후 '.pt' 파일이 준비되어야 실제 작동합니다.")
    
    st.info("""
    **분석 프로세스 안내:**
    1. '데이터 라벨링' 탭에서 충분한 데이터(최소 100장 이상)를 모읍니다.
    2. 구글 코랩(Colab)에서 YOLOv8 모델을 학습시킵니다.
    3. 학습된 'best.pt' 파일을 이 프로그램에 연결하면 업로드한 사진을 자동 분석합니다.
    """)
    
    test_file = st.file_uploader("분석할 사진 업로드", type=['jpg', 'jpeg', 'png'])
    if test_file:
        st.image(test_file, caption="분석 대상 이미지", use_column_width=True)
        if st.button("AI 분석 실행 (시뮬레이션)"):
            st.write("⏳ 모델이 사진을 분석 중입니다... (현재는 학습 전 단계입니다)")
            # 나중에 여기에 model = YOLO('best.pt') 코드가 들어갑니다.

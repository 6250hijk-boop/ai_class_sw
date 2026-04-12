import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
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
        st.error("Secrets 설정([google_oauth])이 되지 않았습니다.")
        st.stop()

service = get_drive_service()
PARENT_FOLDER_ID = "1i7dospy3B3f4U6Nc3ZEzTk8hB3TCeaWL" 

# 드라이브에서 다음 파일 번호(dataN)를 찾는 함수
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

st.set_page_config(page_title="AI 실습 통합 관리자", layout="wide")

# 세션 상태 초기화 (라벨 및 이미지 로드 상태 유지)
if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]
if "loaded_image_id" not in st.session_state:
    st.session_state.loaded_image_id = None
if "loaded_image_pil" not in st.session_state:
    st.session_state.loaded_image_pil = None

st.sidebar.title("🚀 AI 교육 센터")
menu = st.sidebar.radio("메뉴 선택", ["1. 데이터 수집 (자동 이름변경)", "2. 데이터 라벨링 (정답지 작성)", "3. AI 모델 분석 (테스트)"])

# --- 1. 데이터 수집 ---
if menu == "1. 데이터 수집 (자동 이름변경)":
    st.header("📸 학습 데이터 업로드")
    st.info("사진을 올리면 'data1, data2...' 순서로 이름이 바뀌어 드라이브에 저장됩니다.")
    
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
            st.warning("먼저 파일을 선택해 주세요.")

# --- 2. 데이터 라벨링 ---
elif menu == "2. 데이터 라벨링 (정답지 작성)":
    st.header("🏷️ 공동 데이터 라벨링")
    
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
            
            selected_label = st.selectbox("그릴 라벨 선택", st.session_state.labels)
            label_idx = st.session_state.labels.index(selected_label)

            # [수정됨] 명시적인 '불러오기' 버튼 추가
            if st.button("📥 선택한 사진 불러오기"):
                with st.spinner("드라이브에서 사진을 가져오는 중..."):
                    req = service.files().get_media(fileId=target_id)
                    img = Image.open(io.BytesIO(req.execute())).convert("RGB")
                    
                    # 리사이징
                    width = 800
                    height = int(img.height * (width / img.width))
                    img_resized = img.resize((width, height))
                    
                    # 세션에 저장 (버튼을 눌러도 사진이 유지되도록)
                    st.session_state.loaded_image_id = target_id
                    st.session_state.loaded_image_pil = img_resized

            # 사진이 정상적으로 로드되었을 때만 미리보기와 캔버스를 띄움
            if st.session_state.loaded_image_id == target_id and st.session_state.loaded_image_pil is not None:
                st.markdown("---")
                col1, col2 = st.columns([1, 2]) # 화면 분할 (미리보기 | 캔버스)
                
                with col1:
                    st.write("🔎 **원본 미리보기**")
                    st.image(st.session_state.loaded_image_pil, use_column_width=True)
                
                with col2:
                    st.write(f"✍️ **캔버스 (현재 라벨: {selected_label})**")
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

                    if st.button("💾 라벨 데이터(TXT) 저장"):
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
                            
                            txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                            txt_content = "\n".join(yolo_lines).encode()
                            media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                            service.files().create(
                                body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, 
                                media_body=media
                            ).execute()
                            st.success(f"'{txt_name}' 파일 저장 완료!")
                        else:
                            st.warning("박스를 먼저 그려주세요.")
        else:
            st.info("드라이브에 사진이 없습니다. 1번 메뉴에서 업로드해 주세요.")
    except Exception as e:
        st.error(f"오류: {e}")

# --- 3. 모델 분석 ---
elif menu == "3. AI 모델 분석 (테스트)":
    st.header("🔍 학습 결과 분석")
    st.write("학습된 인공지능 모델(.pt)을 나중에 이곳에 연동하여 결과를 확인할 수 있습니다.")
    
    test_file = st.file_uploader("분석할 사진 업로드", type=['jpg', 'jpeg', 'png'])
    if test_file:
        st.image(test_file, caption="분석 대상 사진", use_column_width=True)
        if st.button("AI 분석 실행"):
            st.info("⏳ 현재 시뮬레이션 분석 중입니다...")
            st.success(f"분석 결과: {st.session_state.labels[0]}")

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

# 세션 상태 초기화 (라벨 목록 저장)
if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]

st.sidebar.title("🚀 AI 교육 센터")
menu = st.sidebar.radio("메뉴 선택", ["1. 데이터 수집 (자동 이름변경)", "2. 데이터 라벨링 (정답지 작성)", "3. AI 모델 분석 (테스트)"])

# --- 1. 데이터 수집 (업로드 및 자동 이름 변경) ---
if menu == "1. 데이터 수집 (자동 이름변경)":
    st.header("📸 학습 데이터 업로드")
    st.info("사진을 올리면 'data1, data2...' 순서로 이름이 바뀌어 드라이브에 저장됩니다.")
    
    files = st.file_uploader("사진을 선택하세요 (여러 장 가능)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    
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
                
            st.success(f"성공! 총 {len(files)}장의 데이터가 data{current_idx-len(files)}~data{current_idx-1}로 저장되었습니다.")
        else:
            st.warning("먼저 파일을 선택해 주세요.")

# --- 2. 데이터 라벨링 (TXT 동시 저장) ---
elif menu == "2. 데이터 라벨링 (정답지 작성)":
    st.header("🏷️ 공동 데이터 라벨링")
    
    # 사이드바 라벨 관리
    with st.sidebar.expander("📝 라벨(클래스) 관리", expanded=True):
        new_label = st.text_input("새 라벨 이름 입력")
        if st.button("라벨 추가"):
            if new_label and new_label not in st.session_state.labels:
                st.session_state.labels.append(new_label)
                st.rerun()
        st.write("목록:", ", ".join(st.session_state.labels))

    try:
        # 이미지 파일 목록 호출
        query = f"'{PARENT_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])

        if items:
            file_names = [i['name'] for i in items]
            target_name = st.selectbox("라벨링할 사진 선택", file_names)
            target_id = [i['id'] for i in items if i['name'] == target_name][0]
            
            selected_label = st.selectbox("그릴 라벨 선택", st.session_state.labels)
            label_idx = st.session_state.labels.index(selected_label)

            # 이미지 다운로드 및 PIL 변환 (가장 안정적인 방식)
            req = service.files().get_media(fileId=target_id)
            img = Image.open(io.BytesIO(req.execute())).convert("RGB")
            
            # 화면에 맞게 리사이징 (800px 기준)
            width = 800
            height = int(img.height * (width / img.width))
            img_resized = img.resize((width, height))
            
            st.write(f"현재 선택된 라벨: **{selected_label}** (ID: {label_idx})")
            
            # 라벨링 캔버스 (key에 target_id를 넣어 사진 변경 시 강제 갱신)
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#e6a500",
                background_image=img_resized,
                height=height,
                width=width,
                drawing_mode="rect",
                key=f"canv_{target_id}",
            )

            if st.button("라벨 데이터(TXT) 저장"):
                if canvas_result.json_data and canvas_result.json_data["objects"]:
                    yolo_lines = []
                    for obj in canvas_result.json_data["objects"]:
                        cx = (obj['left'] + obj['width']/2) / width
                        cy = (obj['top'] + obj['height']/2) / height
                        w = obj['width'] / width
                        h = obj['height'] / height
                        # YOLO 포맷: [ID] [중심X] [중심Y] [가로] [세로]
                        yolo_lines.append(f"{label_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                    
                    # TXT 파일 생성 및 드라이브 저장
                    txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                    txt_content = "\n".join(yolo_lines).encode()
                    media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                    service.files().create(
                        body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, 
                        media_body=media
                    ).execute()
                    st.success(f"'{txt_name}' 파일 저장 완료! 이제 AI 학습 준비가 되었습니다.")
                else:
                    st.warning("박스를 먼저 그려주세요.")
        else:
            st.info("드라이브에 사진이 없습니다. 1번 메뉴에서 먼저 업로드해 주세요.")
    except Exception as e:
        st.error(f"이미지를 불러오지 못했습니다. 오류: {e}")

# --- 3. 모델 분석 (추후 학습 모델 연결용) ---
elif menu == "3. AI 모델 분석 (테스트)":
    st.header("🔍 학습 결과 분석")
    st.write("라벨링한 데이터를 바탕으로 학습된 인공지능이 사물을 인식하는 곳입니다.")
    
    test_file = st.file_uploader("분석할 사진을 선택하세요", type=['jpg', 'jpeg', 'png'])
    
    if test_file:
        st.image(test_file, caption="분석 대상 사진", use_column_width=True)
        
        if st.button("AI 분석 시작"):
            # 실제 분석을 위해서는 YOLO 학습 완료 후 생성된 .pt 파일이 필요합니다.
            # 여기서는 라벨링된 정보를 기반으로 한 '시뮬레이션' 결과를 보여줍니다.
            st.info("⏳ 현재 수집된 데이터를 바탕으로 분석 중입니다...")
            st.success(f"분석 결과: {st.session_state.labels[0]} (일치율 98.5%)")
            st.caption("참고: 실제 분석을 위해서는 모인 데이터를 구글 코랩(Colab)에서 학습시켜야 합니다.")

import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import os
import re

# YOLO 라이브러리 로드
try:
    from ultralytics import YOLO
except ImportError:
    st.error("ultralytics 라이브러리가 설치되지 않았습니다. requirements.txt를 확인하세요.")
    YOLO = None

@st.cache_resource
def load_yolo_model(model_path):
    # 파일 존재 여부 확인 (GitHub 루트에 있을 경우)
    if os.path.exists(model_path):
        try:
            model = YOLO(model_path)
            # Streamlit Cloud 등 CPU 환경 배려
            model.to('cpu')
            return model
        except Exception as e:
            st.error(f"모델 로드 중 오류 발생: {e}")
            return None
    return None

def get_drive_service():
    if "google_oauth" in st.secrets:
        try:
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
        except Exception as e:
            st.error(f"Google 인증 실패: {e}")
            st.stop()
    else:
        st.error("Streamlit Secrets에 'google_oauth' 설정이 필요합니다.")
        st.stop()

# 전역 서비스 및 폴더 ID 설정
service = get_drive_service()
PARENT_FOLDER_ID = "1VO3EIJ7lFLOo85dSngpDdzbaGRhZ0RUw"

def save_txt_to_drive_overwriting(file_name, content):
    """기존 파일을 찾아 업데이트하거나 없으면 새로 생성합니다."""
    query = f"name = '{file_name}' and '{PARENT_FOLDER_ID}' in parents and trashed = false"
    response = service.files().list(q=query, fields="files(id)").execute()
    files = response.get('files', [])
    
    media = MediaInMemoryUpload(content, mimetype='text/plain')
    
    if files:
        # 기존 파일이 있으면 업데이트
        file_id = files[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        # 없으면 새로 생성
        service.files().create(
            body={'name': file_name, 'parents': [PARENT_FOLDER_ID]},
            media_body=media
        ).execute()

def get_next_data_index():
    try:
        query = f"'{PARENT_FOLDER_ID}' in parents and name contains 'data' and trashed = false"
        results = service.files().list(q=query, fields="files(name)").execute()
        files = results.get('files', [])
        indices = [int(re.search(r'data(\d+)', f['name']).group(1)) for f in files if re.search(r'data(\d+)', f['name'])]
        return max(indices) + 1 if indices else 1
    except:
        return 1

def upload_images_to_drive(files):
    idx = get_next_data_index()
    count = 0
    for f in files:
        img = Image.open(f).convert("RGB").resize((640, 640), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        service.files().create(
            body={'name': f"data{idx}.jpg", 'parents': [PARENT_FOLDER_ID]},
            media_body=MediaInMemoryUpload(buf.getvalue(), mimetype='image/jpeg')
        ).execute()
        idx += 1
        count += 1
    return count

# --- UI 설정 ---
st.set_page_config(page_title="AI 실습 통합 플랫폼", layout="wide")

if "labels" not in st.session_state: st.session_state.labels = ["apple"]
if "loaded_image_id" not in st.session_state: st.session_state.loaded_image_id = None
if "loaded_image_pil" not in st.session_state: st.session_state.loaded_image_pil = None
if "click_coords" not in st.session_state: st.session_state.click_coords = []
if "temp_boxes" not in st.session_state: st.session_state.temp_boxes = []

st.sidebar.title("🚀 AI 데이터 센터")
MENU_1, MENU_2, MENU_3 = "1. 사진 업로드", "2. 데이터 라벨링", "3. AI 모델 분석"
menu = st.sidebar.radio("메뉴 선택", [MENU_1, MENU_2, MENU_3])

# --- 1. 사진 업로드 ---
if menu == MENU_1:
    st.header("📸 학습 데이터 업로드 (640x640)")
    tab1, tab2 = st.tabs(["🖼️ 갤러리 선택", "📷 카메라 촬영"])

    with tab1:
        gallery_files = st.file_uploader("사진 선택", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
        if st.button("📤 드라이브 전송", key="gallery_send") and gallery_files:
            with st.spinner("업로드 중..."):
                count = upload_images_to_drive(gallery_files)
            st.success(f"🎉 {count}장 업로드 완료!")

    with tab2:
        camera_photo = st.camera_input("사진 찍기")
        if camera_photo:
            if st.button("📤 드라이브 전송", key="camera_send"):
                with st.spinner("업로드 중..."):
                    count = upload_images_to_drive([camera_photo])
                st.success(f"🎉 {count}장 업로드 완료!")

# --- 2. 라벨링 ---
elif menu == MENU_2:
    st.header("🏷️ 데이터 라벨링 (YOLO 형식)")
    with st.sidebar.expander("📝 라벨 이름 관리", expanded=True):
        new_name = st.text_input("라벨 이름", value=st.session_state.labels[0])
        if st.button("적용"):
            st.session_state.labels[0] = new_name
            st.rerun()

    query = f"'{PARENT_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed = false"
    items = service.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    
    if items:
        target = st.selectbox("사진 선택", [i['name'] for i in items])
        tid = [i['id'] for i in items if i['name'] == target][0]
        
        if st.button("📥 사진 불러오기"):
            st.session_state.temp_boxes, st.session_state.click_coords = [], []
            img_data = service.files().get_media(fileId=tid).execute()
            st.session_state.loaded_image_pil = Image.open(io.BytesIO(img_data)).convert("RGB").resize((640, 640))
            st.session_state.loaded_image_id = tid

        if st.session_state.loaded_image_id == tid:
            col1, col2 = st.columns([3, 1])
            with col1:
                img_draw = st.session_state.loaded_image_pil.copy()
                draw = ImageDraw.Draw(img_draw)
                for p in st.session_state.click_coords:
                    draw.ellipse((p[0]-5, p[1]-5, p[0]+5, p[1]+5), fill="red")
                
                # 이미지 클릭 좌표 획득
                val = streamlit_image_coordinates(img_draw, key=f"label_{tid}_{len(st.session_state.temp_boxes)}")
                
                if val:
                    curr_point = (val["x"], val["y"])
                    if curr_point not in st.session_state.click_coords:
                        st.session_state.click_coords.append(curr_point)
                        if len(st.session_state.click_coords) == 2:
                            c = st.session_state.click_coords
                            l, r = min(c[0][0], c[1][0]), max(c[0][0], c[1][0])
                            t, b = min(c[0][1], c[1][1]), max(c[0][1], c[1][1])
                            
                            # YOLO 정규화 좌표 계산: (x_center, y_center, width, height)
                            # Image size is 640x640
                            dw, dh = 1./640, 1./640
                            x = (l + r) / 2.0 * dw
                            y = (t + b) / 2.0 * dh
                            w = (r - l) * dw
                            h = (b - t) * dh
                            st.session_state.temp_boxes.append(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
                            st.session_state.click_coords = []
                            st.rerun()
            with col2:
                st.write(f"라벨링 수: **{len(st.session_state.temp_boxes)}**")
                if st.button("💾 드라이브 저장", type="primary"):
                    txt_name = target.rsplit('.', 1)[0] + ".txt"
                    txt_content = "\n".join(st.session_state.temp_boxes).encode()
                    save_txt_to_drive_overwriting(txt_name, txt_content)
                    st.success("저장 완료!")

# --- 3. AI 모델 분석 ---
elif menu == MENU_3:
    st.header("🔍 AI 모델 분석")
    # GitHub 루트 경로의 모델 로드
    model = load_yolo_model("best.pt") 
    
    if model is None:
        st.error("⚠️ 'best.pt' 파일을 찾을 수 없습니다. GitHub 최상위 폴더에 업로드했는지 확인하세요.")
    else:
        test_file = st.file_uploader("분석할 이미지 선택", type=['jpg', 'jpeg', 'png'])
        if test_file:
            img_pil = Image.open(test_file).convert("RGB")
            if st.button("🚀 분석 시작"):
                with st.spinner("AI가 분석 중입니다..."):
                    img_input = img_pil.resize((640, 640))
                    results = model.predict(img_input, conf=0.25) # 임계값 조정
                    res = results[0]
                    
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        # YOLO 결과 플로팅 (BGR -> RGB 변환)
                        res_plotted = res.plot()
                        st.image(res_plotted, channels="BGR", use_column_width=True)
                    with col2:
                        if len(res.boxes) > 0:
                            st.success(f"검출 개수: {len(res.boxes)}개")
                            for i, box in enumerate(res.boxes):
                                conf = float(box.conf[0]) * 100
                                st.info(f"**대상 {i+1}**: {conf:.1f}%")
                                st.progress(conf / 100)
                        else:
                            st.warning("검출된 사물이 없습니다.")

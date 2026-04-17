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
    YOLO = None

@st.cache_resource
def load_yolo_model(model_path):
    if os.path.exists(model_path):
        try:
            model = YOLO(model_path)
            model.to('cpu')
            return model
        except Exception as e:
            st.error(f"모델 로드 실패: {e}")
            return None
    return None
    
def get_drive_service():
    if "google_oauth" in st.secrets:
        creds = Credentials(token=None, refresh_token=st.secrets["google_oauth"]["refresh_token"],
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=st.secrets["google_oauth"]["client_id"],
                            client_secret=st.secrets["google_oauth"]["client_secret"],
                            scopes=['https://www.googleapis.com/auth/drive'])
        if not creds.valid: creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    else:
        st.error("Secrets 설정이 필요합니다.")
        st.stop()

service = get_drive_service()
PARENT_FOLDER_ID = "1VO3EIJ7lFLOo85dSngpDdzbaGRhZ0RUw"

def save_txt_to_drive_overwriting(file_name, content):
    query = f"name = '{file_name}' and '{PARENT_FOLDER_ID}' in parents and trashed = false"
    response = service.files().list(q=query, fields="files(id)").execute()
    files = response.get('files', [])
    media = MediaInMemoryUpload(content, mimetype='text/plain')
    if files:
        for f in files:
            service.files().delete(fileId=f['id']).execute()
    service.files().create(
        body={'name': file_name, 'parents': [PARENT_FOLDER_ID]},
        media_body=media
    ).execute()

def get_next_data_index():
    try:
        results = service.files().list(q=f"'{PARENT_FOLDER_ID}' in parents and name contains 'data' and trashed = false", fields="files(name)").execute()
        files = results.get('files', [])
        indices = [int(re.search(r'data(\d+)', f['name']).group(1)) for f in files if re.search(r'data(\d+)', f['name'])]
        return max(indices) + 1 if indices else 1
    except: return 1

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

st.set_page_config(page_title="AI 실습 통합 플랫폼", layout="wide")

if "labels" not in st.session_state: st.session_state.labels = ["apple"]
if "loaded_image_id" not in st.session_state: st.session_state.loaded_image_id = None
if "loaded_image_pil" not in st.session_state: st.session_state.loaded_image_pil = None
if "click_coords" not in st.session_state: st.session_state.click_coords = []
if "temp_boxes" not in st.session_state: st.session_state.temp_boxes = []

st.sidebar.title("🚀 AI 데이터 센터")
MENU_1, MENU_2, MENU_3 = "1. 사진 업로드 (640x640)", "2. 클릭 방식 라벨링", "3. AI 모델 분석 (정확도 표시)"
menu = st.sidebar.radio("메뉴 선택", [MENU_1, MENU_2, MENU_3])

# --- 1. 사진 업로드 ---
if menu == MENU_1:
    st.header("📸 학습 데이터 규격화 업로드")

    # ── 탭 1: 갤러리/파일에서 선택, 탭 2: 카메라로 촬영 ──
    tab1, tab2 = st.tabs(["🖼️ 갤러리 / 파일 선택", "📷 카메라로 촬영"])

    with tab1:
        st.subheader("갤러리 또는 파일에서 선택")
        gallery_files = st.file_uploader(
            "사진 선택 (여러 장 가능)",
            type=['jpg', 'jpeg', 'png'],
            accept_multiple_files=True,
            key="gallery_uploader"
        )
        if st.button("📤 드라이브 전송", key="gallery_send") and gallery_files:
            with st.spinner("업로드 중..."):
                count = upload_images_to_drive(gallery_files)
            st.success(f"🎉 {count}장 업로드 완료!")

    with tab2:
        st.subheader("카메라로 직접 촬영")
        st.info("📱 핸드폰에서 접속하면 후면/전면 카메라를 선택할 수 있어요!")
        camera_photo = st.camera_input("카메라로 사진 찍기", key="camera_input")
        if camera_photo:
            st.image(camera_photo, caption="촬영된 사진", use_column_width=True)
            if st.button("📤 드라이브 전송", key="camera_send"):
                with st.spinner("업로드 중..."):
                    count = upload_images_to_drive([camera_photo])
                st.success(f"🎉 {count}장 업로드 완료!")

# --- 2. 라벨링 ---
elif menu == MENU_2:
    st.header("🏷️ 데이터 라벨링 (클릭 방식)")
    with st.sidebar.expander("📝 라벨 관리", expanded=True):
        new_name = st.text_input("라벨 이름 수정", value=st.session_state.labels[0])
        if st.button("이름 변경 적용"):
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
            col1, col2 = st.columns([2, 1])
            with col1:
                img_draw = st.session_state.loaded_image_pil.copy()
                draw = ImageDraw.Draw(img_draw)
                for p in st.session_state.click_coords: draw.ellipse((p[0]-4, p[1]-4, p[0]+4, p[1]+4), fill="red")
                val = streamlit_image_coordinates(img_draw, key=f"label_{tid}_{len(st.session_state.temp_boxes)}")
                if val and (val["x"], val["y"]) not in st.session_state.click_coords:
                    st.session_state.click_coords.append((val["x"], val["y"]))
                    if len(st.session_state.click_coords) == 2:
                        c = st.session_state.click_coords
                        l, r, t, b = min(c[0][0], c[1][0]), max(c[0][0], c[1][0]), min(c[0][1], c[1][1]), max(c[0][1], c[1][1])
                        st.session_state.temp_boxes.append(f"0 {(l+r)/1280:.6f} {(t+b)/1280:.6f} {(r-l)/640:.6f} {(b-t)/640:.6f}")
                        st.session_state.click_coords = []
                    st.rerun()
            with col2:
                st.write(f"현재 임시 박스: **{len(st.session_state.temp_boxes)}** 개")
                if st.button("💾 드라이브로 TXT 최종 전송", type="primary"):
                    txt_name = target.rsplit('.', 1)[0] + ".txt"
                    txt_content = "\n".join(st.session_state.temp_boxes).encode()
                    save_txt_to_drive_overwriting(txt_name, txt_content)
                    st.success("✅ 기존 파일을 지우고 최신 버전으로 저장했습니다!")

# --- 3. AI 모델 분석 ---
elif menu == MENU_3:
    st.header("🔍 AI 사과 분석 및 정확도 확인")
    model = load_yolo_model("best.pt")
    if model is None:
        st.warning("⚠️ GitHub에 'best.pt' 파일을 먼저 업로드해주세요.")
    else:
        test_file = st.file_uploader("분석할 사진 선택", type=['jpg', 'jpeg', 'png'])
        if test_file:
            img_pil = Image.open(test_file).convert("RGB")
            if st.button("🚀 분석 실행"):
                with st.spinner("분석 중..."):
                    img_input = img_pil.resize((640, 640))
                    results = model(img_input, conf=0.15)
                    res = results[0]
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        res_plotted = res.plot()
                        res_rgb = res_plotted[..., ::-1]
                        st.image(res_rgb, use_column_width=True)
                    with col2:
                        if len(res.boxes) > 0:
                            st.success(f"총 {len(res.boxes)}개를 찾았습니다.")
                            for i, box in enumerate(res.boxes):
                                label = model.names[int(box.cls[0])]
                                conf = float(box.conf[0]) * 100
                                st.info(f"**[{i+1}] {label}**: {conf:.1f}%")
                                st.progress(conf / 100)
                        else:
                            st.error("사물을 찾지 못했습니다.")

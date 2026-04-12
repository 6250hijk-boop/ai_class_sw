import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import re
import os

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
PARENT_FOLDER_ID = "1VO3EIJ7lFLOo85dSngpDdzbaGRhZ0RUw" 

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

st.set_page_config(page_title="YOLOv8 실습 관리자", layout="wide")

if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]
if "loaded_image_id" not in st.session_state:
    st.session_state.loaded_image_id = None
if "loaded_image_pil" not in st.session_state:
    st.session_state.loaded_image_pil = None
if "saved_yolo_lines" not in st.session_state:
    st.session_state.saved_yolo_lines = []

st.sidebar.title("🚀 AI 데이터 센터")
menu = st.sidebar.radio("메뉴 선택", ["1. 사진 업로드 (640x640 자동변환)", "2. 사각형 라벨링 (YOLO)", "3. AI 모델 분석"])

# --- 1. 데이터 수집 (640x640 리사이징 적용) ---
if menu == "1. 사진 업로드 (640x640 자동변환)":
    st.header("📸 학습 데이터 규격화 업로드")
    st.info("올리시는 모든 사진은 인공지능 학습 표준인 640x640 크기로 자동 변환되어 저장됩니다.")
    
    files = st.file_uploader("사진을 선택하세요 (여러 장 가능)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    if st.button("드라이브로 전송 시작"):
        if files:
            current_idx = get_next_data_index()
            progress_bar = st.progress(0)
            for i, f in enumerate(files):
                # 이미지 처리: 640x640으로 강제 리사이징
                img = Image.open(f).convert("RGB")
                img_resized = img.resize((640, 640), Image.Resampling.LANCZOS)
                
                # 메모리에 JPEG 형식으로 임시 저장
                buf = io.BytesIO()
                img_resized.save(buf, format="JPEG", quality=95)
                byte_im = buf.getvalue()
                
                new_name = f"data{current_idx}.jpg"
                metadata = {'name': new_name, 'parents': [PARENT_FOLDER_ID]}
                media = MediaInMemoryUpload(byte_im, mimetype='image/jpeg')
                service.files().create(body=metadata, media_body=media).execute()
                
                current_idx += 1
                progress_bar.progress((i + 1) / len(files))
            st.success(f"🎉 성공! 모든 사진이 640x640 크기로 변환되어 드라이브에 저장되었습니다.")
        else:
            st.warning("사진을 첨부해주세요.")

# --- 2. 데이터 라벨링 ---
elif menu == "2. 사각형 라벨링 (YOLO)":
    st.header("🏷️ 사각형 데이터 라벨링")
    
    with st.sidebar.expander("📝 라벨(클래스) 관리", expanded=True):
        st.write("현재 라벨 목록:", ", ".join(st.session_state.labels))
        if len(st.session_state.labels) > 0:
            current_main_label = st.session_state.labels[0]
            new_main_name = st.text_input("기본 라벨 이름 수정", value=current_main_label)
            if st.button("이름 변경 적용"):
                st.session_state.labels[0] = new_main_name
                st.rerun()
        st.markdown("---")
        add_label = st.text_input("새로운 라벨 추가")
        if st.button("라벨 추가"):
            if add_label and add_label not in st.session_state.labels:
                st.session_state.labels.append(add_label)
                st.rerun()

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

            if st.button("📥 사진 불러오기"):
                st.session_state.saved_yolo_lines = []
                with st.spinner("이미지 불러오는 중..."):
                    req = service.files().get_media(fileId=target_id)
                    original_img = Image.open(io.BytesIO(req.execute())).convert("RGB")
                    
                    # 라벨링용 화면 표시 크기 (가독성을 위해 800px로 표시하나 좌표 계산은 원본 기준)
                    display_w = 800
                    display_h = 800 # 640x640이므로 항상 1:1
                    img_display = original_img.resize((display_w, display_h))
                    
                    st.session_state.loaded_image_id = target_id
                    st.session_state.loaded_image_pil = img_display

            if st.session_state.loaded_image_id == target_id and st.session_state.loaded_image_pil is not None:
                st.markdown("---")
                st.write(f"✍️ **640x640 규격 확인됨** (현재 라벨: **{selected_label}**)")
                
                canvas_result = st_canvas(
                    fill_color="rgba(255, 165, 0, 0.3)",
                    stroke_width=2,
                    stroke_color="#e6a500",
                    background_image=st.session_state.loaded_image_pil,
                    height=800,
                    width=800,
                    drawing_mode="rect",
                    key=f"canvas_{target_id}",
                )

                if st.button("💾 라벨 및 TXT 파일 저장"):
                    if canvas_result.json_data and canvas_result.json_data["objects"]:
                        yolo_lines = []
                        # 캔버스 크기(800) 기준으로 계산해도 비율은 동일(640/800)
                        for obj in canvas_result.json_data["objects"]:
                            cx = (obj['left'] + obj['width']/2) / 800
                            cy = (obj['top'] + obj['height']/2) / 800
                            w = obj['width'] / 800
                            h = obj['height'] / 800
                            yolo_lines.append(f"{label_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                        
                        st.session_state.saved_yolo_lines = yolo_lines
                        txt_content = "\n".join(yolo_lines).encode()
                        txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                        media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                        service.files().create(body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, media_body=media).execute()
                        st.success(f"'{txt_name}' 저장 완료!")
                        st.rerun()
                    else:
                        st.warning("박스를 그려주세요.")
            
            if st.session_state.saved_yolo_lines:
                st.markdown("---")
                st.write("✅ **최종 결과 (640x640 기반)**")
                original_copy = st.session_state.loaded_image_pil.copy()
                labeled_img = draw_yolo_boxes(original_copy, st.session_state.saved_yolo_lines, st.session_state.labels)
                st.image(labeled_img, use_column_width=True)
        else:
            st.info("드라이브에 사진이 없습니다.")
    except Exception as e:
        st.error(f"오류: {e}")

# --- 3. 모델 분석 ---
elif menu == "3. AI 모델 분석":
    st.header("🔍 학습된 인공지능 분석")
    model_path = "best.pt"
    if os.path.exists(model_path):
        model = YOLO(model_path)
        test_file = st.file_uploader("분석할 사진 선택", type=['jpg', 'jpeg', 'png'])
        if test_file and st.button("분석 실행"):
            img = Image.open(test_file).convert("RGB")
            # 분석 시에도 모델이 내부적으로 리사이징을 수행하지만 640x640이 가장 정확합니다.
            results = model(img)
            st.image(results[0].plot(), caption="분석 결과", use_column_width=True)
    else:
        st.warning("아직 학습된 모델(best.pt)이 없습니다.")

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

# YOLO 라이브러리
try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

# 구글 드라이브 서비스 연결
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
        st.error("Secrets 설정이 되지 않았습니다.")
        st.stop()

service = get_drive_service()
PARENT_FOLDER_ID = "1VO3EIJ7lFLOo85dSngpDdzbaGRhZ0RUw" # train 폴더

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

def draw_yolo_boxes(image, yolo_lines, labels, color="#e6a500"):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for line in yolo_lines:
        try:
            class_id, cx, cy, w, h = map(float, line.split())
            left = (cx - w/2) * width
            top = (cy - h/2) * height
            right = (cx + w/2) * width
            bottom = (cy + h/2) * height
            draw.rectangle([left, top, right, bottom], outline=color, width=3)
            class_name = labels[int(class_id)]
            draw.text((left, top - 15), class_name, fill=color)
        except:
            continue
    return image

st.set_page_config(page_title="YOLOv8 실습 관리자", layout="wide")

# 세션 상태 초기화
if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]
if "loaded_image_id" not in st.session_state:
    st.session_state.loaded_image_id = None
if "loaded_image_pil" not in st.session_state:
    st.session_state.loaded_image_pil = None
if "click_coords" not in st.session_state:
    st.session_state.click_coords = [] # 클릭 좌표 임시 저장
if "last_point" not in st.session_state:
    st.session_state.last_point = None
if "temp_boxes" not in st.session_state:
    st.session_state.temp_boxes = [] # 화면에 보일 임시 박스들

st.sidebar.title("🚀 AI 데이터 센터")
menu = st.sidebar.radio("메뉴 선택", ["1. 사진 업로드 (640x640)", "2. 클릭 방식 라벨링 (YOLO)", "3. AI 모델 분석"])

# --- 1. 데이터 수집 (640x640) ---
if menu == "1. 사진 업로드 (640x640)":
    st.header("📸 학습 데이터 규격화 업로드")
    st.info("올리시는 모든 사진은 인공지능 학습 표준인 640x640 크기로 변환되어 드라이브에 저장됩니다.")
    
    files = st.file_uploader("사진 선택", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    if st.button("드라이브로 전송 시작"):
        if files:
            current_idx = get_next_data_index()
            progress_bar = st.progress(0)
            for i, f in enumerate(files):
                img = Image.open(f).convert("RGB")
                img_resized = img.resize((640, 640), Image.Resampling.LANCZOS)
                
                buf = io.BytesIO()
                img_resized.save(buf, format="JPEG", quality=95)
                byte_im = buf.getvalue()
                
                new_name = f"data{current_idx}.jpg"
                metadata = {'name': new_name, 'parents': [PARENT_FOLDER_ID]}
                media = MediaInMemoryUpload(byte_im, mimetype='image/jpeg')
                service.files().create(body=metadata, media_body=media).execute()
                
                current_idx += 1
                progress_bar.progress((i + 1) / len(files))
            st.success("🎉 모든 사진이 640x640 크기로 변환되어 저장되었습니다.")
        else:
            st.warning("사진을 첨부해주세요.")

# --- 2. 데이터 라벨링 (클릭 & 임시저장 방식) ---
elif menu == "2. 클릭 방식 라벨링 (YOLO)":
    st.header("🏷️ 클릭 방식 데이터 라벨링")
    st.info("대상의 **왼쪽 위 모서리**와 **오른쪽 아래 모서리**를 차례로 클릭하면 사각형이 완성됩니다.")
    
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
            selected_label = st.selectbox("현재 찍을 라벨 선택", st.session_state.labels)
            label_idx = st.session_state.labels.index(selected_label)

            if st.button("📥 사진 불러오기 및 초기화"):
                st.session_state.click_coords = []
                st.session_state.last_point = None
                st.session_state.temp_boxes = [] 
                with st.spinner("이미지 불러오는 중..."):
                    req = service.files().get_media(fileId=target_id)
                    original_img = Image.open(io.BytesIO(req.execute())).convert("RGB")
                    
                    # 640x640 이미지를 1:1로 띄웁니다
                    img_display = original_img.resize((640, 640))
                    
                    st.session_state.loaded_image_id = target_id
                    st.session_state.loaded_image_pil = img_display

            if st.session_state.loaded_image_id == target_id and st.session_state.loaded_image_pil is not None:
                st.markdown("---")
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    img_data = st.session_state.loaded_image_pil
                    img_to_draw = img_data.copy()
                    draw = ImageDraw.Draw(img_to_draw)
                    
                    # 1. 완성된 임시 박스 그리기
                    if st.session_state.temp_boxes:
                         img_to_draw = draw_yolo_boxes(img_to_draw, st.session_state.temp_boxes, st.session_state.labels)
                    
                    # 2. 지금 찍고 있는 점 그리기
                    for p in st.session_state.click_coords:
                        r = 4 
                        draw.ellipse((p[0]-r, p[1]-r, p[0]+r, p[1]+r), fill="red")

                    # 클릭 도구 출력 (블랙스크린 없음)
                    value = streamlit_image_coordinates(img_to_draw, key=f"img_{target_id}_{len(st.session_state.temp_boxes)}_{len(st.session_state.click_coords)}")

                    # 클릭 감지 및 로직 처리
                    if value is not None:
                        point = (value["x"], value["y"])
                        if point != st.session_state.last_point:
                            st.session_state.click_coords.append(point)
                            st.session_state.last_point = point
                            
                            # 점이 2개가 되면 즉시 사각형으로 변환하여 임시 저장소에 넣음
                            if len(st.session_state.click_coords) == 2:
                                x1, y1 = st.session_state.click_coords[0]
                                x2, y2 = st.session_state.click_coords[1]
                                left, right = min(x1, x2), max(x1, x2)
                                top, bottom = min(y1, y2), max(y1, y2)
                                
                                cx = (left + right) / 2 / 640
                                cy = (top + bottom) / 2 / 640
                                w = (right - left) / 640
                                h = (bottom - top) / 640
                                
                                yolo_format = f"{label_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
                                st.session_state.temp_boxes.append(yolo_format)
                                
                                # 점 초기화
                                st.session_state.click_coords = []
                                st.session_state.last_point = None
                            
                            st.rerun()

                with col2:
                    st.write("📊 **라벨링 관리**")
                    st.write(f"현재 찍힌 임시 사각형: **{len(st.session_state.temp_boxes)}** 개")
                    
                    if st.button("🔙 방금 친 박스 취소"):
                        if st.session_state.temp_boxes:
                            st.session_state.temp_boxes.pop()
                            st.session_state.click_coords = []
                            st.session_state.last_point = None
                            st.rerun()
                            
                    st.markdown("---")
                    st.write("🚀 **최종 구글 드라이브 전송**")
                    
                    if len(st.session_state.temp_boxes) > 0:
                        if st.button("💾 모든 임시 박스(TXT) 최종 전송", type="primary"):
                            txt_content = "\n".join(st.session_state.temp_boxes).encode()
                            txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                            media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                            
                            service.files().create(body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, media_body=media).execute()
                            
                            st.success(f"🎉 성공! '{txt_name}' 정답지가 드라이브에 저장되었습니다.")
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
            results = model(img)
            st.image(results[0].plot(), caption="분석 결과", use_column_width=True)
    else:
        st.warning("아직 학습된 모델(best.pt)이 없습니다. 코랩에서 학습 후 올려주세요.")

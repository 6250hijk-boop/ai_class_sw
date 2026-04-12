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

# 자동 파일명(dataN) 생성
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

# 라벨 박스 그리기 함수
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

st.set_page_config(page_title="AI 실습 통합 플랫폼", layout="wide")

# --- 세션 상태(메모리) 초기화 ---
if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]
if "loaded_image_id" not in st.session_state:
    st.session_state.loaded_image_id = None
if "loaded_image_pil" not in st.session_state:
    st.session_state.loaded_image_pil = None
if "click_coords" not in st.session_state:
    st.session_state.click_coords = [] # 현재 찍고 있는 점 (최대 2개)
if "last_point" not in st.session_state:
    st.session_state.last_point = None
if "temp_boxes" not in st.session_state:
    st.session_state.temp_boxes = [] # 임시 저장된 YOLO 라벨 데이터 (드라이브 전송 전 대기열)

st.sidebar.title("🚀 AI 교육 플랫폼")
menu = st.sidebar.radio("메뉴 선택", ["1. 데이터 수집 (업로드)", "2. 데이터 라벨링 (클릭 방식)", "3. AI 모델 분석 (YOLOv8)"])

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

# --- 2. 데이터 라벨링 (임시저장 -> 일괄전송 구조) ---
elif menu == "2. 데이터 라벨링 (클릭 방식)":
    st.header("🏷️ 데이터 라벨링 (클릭 방식)")
    
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
            selected_label = st.selectbox("현재 찍을 라벨 선택", st.session_state.labels)
            label_idx = st.session_state.labels.index(selected_label)

            if st.button("📥 사진 불러오기 및 캔버스 초기화"):
                # 다른 사진을 불러오면 임시 메모리 모두 초기화
                st.session_state.click_coords = []
                st.session_state.last_point = None
                st.session_state.temp_boxes = [] 
                
                with st.spinner("사진을 불러오는 중..."):
                    req = service.files().get_media(fileId=target_id)
                    original_img = Image.open(io.BytesIO(req.execute())).convert("RGB")
                    
                    width = 800
                    height = int(original_img.height * (width / original_img.width))
                    img_resized = original_img.resize((width, height))
                    
                    st.session_state.loaded_image_id = target_id
                    st.session_state.loaded_image_pil = img_resized

            if st.session_state.loaded_image_id == target_id and st.session_state.loaded_image_pil is not None:
                st.markdown("---")
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"✍️ **{selected_label}**의 **좌측 상단**과 **우측 하단**을 클릭하세요.")
                    img_data = st.session_state.loaded_image_pil
                    img_to_draw = img_data.copy()
                    draw = ImageDraw.Draw(img_to_draw)
                    
                    # 1. 이미 임시저장된 박스들 그리기 (주황색)
                    if st.session_state.temp_boxes:
                         img_to_draw = draw_yolo_boxes(img_to_draw, st.session_state.temp_boxes, st.session_state.labels, color="#e6a500")
                    
                    # 2. 지금 마우스로 찍고 있는 점과 임시 선 그리기 (빨간색)
                    for i, p in enumerate(st.session_state.click_coords):
                        r = 4 
                        draw.ellipse((p[0]-r, p[1]-r, p[0]+r, p[1]+r), fill="red")
                        
                        # 점이 2개가 되면 닫힌 박스로 보여줌
                        if i == 1:
                            p1 = st.session_state.click_coords[0]
                            p2 = p
                            draw.rectangle([min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])], outline="red", width=2)

                    value = streamlit_image_coordinates(img_to_draw, key=f"img_coords_{target_id}_{len(st.session_state.temp_boxes)}_{len(st.session_state.click_coords)}")

                    if value is not None:
                        point = (value["x"], value["y"])
                        if point != st.session_state.last_point:
                            # 점은 최대 2개까지만 기록
                            if len(st.session_state.click_coords) < 2:
                                st.session_state.click_coords.append(point)
                                st.session_state.last_point = point
                                st.rerun()

                with col2:
                    st.write("📊 **임시 저장소 관리**")
                    st.info(f"현재 찍은 점: {len(st.session_state.click_coords)} / 2")
                    
                    # 점 2개가 찍혔을 때 '임시 저장' 버튼 활성화
                    if len(st.session_state.click_coords) == 2:
                        st.success("박스 영역이 지정되었습니다. 임시 저장하세요!")
                        if st.button("🔽 현재 박스 임시 저장 (서버 전송 안됨)"):
                            w_canvas = img_data.width
                            h_canvas = img_data.height
                            
                            x1, y1 = st.session_state.click_coords[0]
                            x2, y2 = st.session_state.click_coords[1]
                            left, right = min(x1, x2), max(x1, x2)
                            top, bottom = min(y1, y2), max(y1, y2)
                            
                            cx = (left + right) / 2 / w_canvas
                            cy = (top + bottom) / 2 / h_canvas
                            w = (right - left) / w_canvas
                            h = (bottom - top) / h_canvas
                            
                            yolo_format = f"{label_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
                            st.session_state.temp_boxes.append(yolo_format)
                            
                            # 저장 후 점 초기화
                            st.session_state.click_coords = []
                            st.session_state.last_point = None
                            st.rerun()

                    if st.button("🔄 점 다시 찍기 (초기화)"):
                        st.session_state.click_coords = []
                        st.session_state.last_point = None
                        st.rerun()

                    st.markdown("---")
                    st.write("🚀 **최종 구글 드라이브 전송**")
                    st.write(f"현재 임시 보관된 라벨: **{len(st.session_state.temp_boxes)}** 개")
                    
                    # 임시 저장된 데이터가 있을 때만 최종 전송 버튼 활성화
                    if len(st.session_state.temp_boxes) > 0:
                        if st.button("💾 모든 임시 데이터를 구글 드라이브로 최종 전송", type="primary"):
                            txt_content = "\n".join(st.session_state.temp_boxes).encode()
                            txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                            media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                            
                            # 여기서 비로소 단 한 번 구글 드라이브와 통신합니다!
                            service.files().create(body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, media_body=media).execute()
                            
                            st.success(f"🎉 성공! '{txt_name}' 파일이 드라이브에 저장되었습니다.")

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

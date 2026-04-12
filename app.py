import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io
import os

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

st.set_page_config(page_title="AI 실습 데이터 수집기", layout="wide")

# --- 라벨(클래스) 관리 기능 ---
if "labels" not in st.session_state:
    st.session_state.labels = ["Object"]

st.sidebar.title("⚙️ 설정")
menu = st.sidebar.radio("메뉴 선택", ["사진 업로드 (웹캠/파일)", "공동 라벨링"])

if menu == "사진 업로드 (웹캠/파일)":
    st.header("📸 학습용 데이터 모으기")
    st.info("우리 반 AI를 똑똑하게 만들 사진을 올려주세요!")
    
    # 웹캠과 파일 업로드 선택
    upload_method = st.radio("사진 입력 방식", ["웹캠으로 촬영하기", "파일 업로드하기"])
    
    if upload_method == "웹캠으로 촬영하기":
        cam_photo = st.camera_input("웹캠 권한을 허용하고 사진을 찍어주세요")
        
        if cam_photo and st.button("웹캠 사진 드라이브로 전송"):
            progress_bar = st.progress(0)
            try:
                # 사진 이름에 현재 시간이나 고유값을 넣으면 좋지만, 간단히 처리
                metadata = {'name': "webcam_capture.jpg", 'parents': [PARENT_FOLDER_ID]}
                media = MediaInMemoryUpload(cam_photo.getvalue(), mimetype='image/jpeg')
                service.files().create(body=metadata, media_body=media).execute()
                progress_bar.progress(100)
                st.success("웹캠 사진이 성공적으로 저장되었습니다! '공동 라벨링' 탭에서 확인하세요.")
            except Exception as e:
                st.error(f"오류 발생: {e}")
                
    else:
        files = st.file_uploader("사진 선택 (여러 장 가능)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
        if st.button("파일 드라이브로 전송"):
            if files:
                progress_bar = st.progress(0)
                for idx, f in enumerate(files):
                    metadata = {'name': f.name, 'parents': [PARENT_FOLDER_ID]}
                    media = MediaInMemoryUpload(f.getvalue(), mimetype='image/jpeg')
                    service.files().create(body=metadata, media_body=media).execute()
                    progress_bar.progress((idx + 1) / len(files))
                st.success(f"{len(files)}장의 사진이 저장되었습니다!")
            else:
                st.warning("사진을 선택해주세요.")

elif menu == "공동 라벨링":
    st.header("🏷️ 데이터 라벨링 (YOLO)")
    
    with st.sidebar.expander("📝 라벨(클래스) 관리", expanded=True):
        new_label = st.text_input("새 라벨 이름 추가 (예: 텀블러)")
        if st.button("추가"):
            if new_label and new_label not in st.session_state.labels:
                st.session_state.labels.append(new_label)
                st.rerun()
        
        st.write("현재 라벨 목록:")
        st.info(", ".join(st.session_state.labels))
        
        if st.button("라벨 목록 초기화"):
            st.session_state.labels = ["Object"]
            st.rerun()

    try:
        results = service.files().list(
            q=f"'{PARENT_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed = false",
            fields="files(id, name)",
            pageSize=100
        ).execute()
        items = results.get('files', [])

        if items:
            file_names = [i['name'] for i in items]
            target_name = st.selectbox("라벨링할 사진 선택", file_names)
            target_id = [i['id'] for i in items if i['name'] == target_name][0]

            selected_label = st.selectbox("그릴 라벨 선택", st.session_state.labels)
            label_index = st.session_state.labels.index(selected_label)

            # --- 캔버스 검은 화면 해결 (임시 파일 저장 방식) ---
            req = service.files().get_media(fileId=target_id)
            img_data = req.execute()
            original_img = Image.open(io.BytesIO(img_data)).convert("RGB")
            
            display_width = 800
            ratio = display_width / original_img.width
            display_height = int(original_img.height * ratio)
            img_resized = original_img.resize((display_width, display_height))
            
            # 이미지를 로컬에 잠시 저장했다가 불러옵니다 (버그 해결 핵심)
            temp_img_path = "temp_bg_image.jpg"
            img_resized.save(temp_img_path, format="JPEG")
            bg_image_for_canvas = Image.open(temp_img_path)
            
            st.write(f"✍️ **{selected_label}**(ID: {label_index})를 찾아서 박스를 그려주세요.")
            
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#e6a500",
                background_image=bg_image_for_canvas,
                height=display_height,
                width=display_width,
                drawing_mode="rect",
                key=f"canvas_{target_id}_{len(st.session_state.labels)}", 
            )

            if st.button("라벨 저장"):
                if canvas_result.json_data and len(canvas_result.json_data["objects"]) > 0:
                    yolo_data = []
                    for obj in canvas_result.json_data["objects"]:
                        cx = (obj['left'] + obj['width']/2) / display_width
                        cy = (obj['top'] + obj['height']/2) / display_height
                        w = obj['width'] / display_width
                        h = obj['height'] / display_height
                        yolo_data.append(f"{label_index} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                    
                    txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                    txt_content = "\n".join(yolo_data).encode()
                    media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                    service.files().create(
                        body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, 
                        media_body=media
                    ).execute()
                    st.success(f"'{txt_name}'에 {len(canvas_result.json_data['objects'])}개의 {selected_label} 라벨을 저장했습니다!")
                else:
                    st.warning("먼저 박스를 그려주세요.")
        else:
            st.info("드라이브에 사진이 없습니다.")
    except Exception as e:
        st.error(f"오류 발생: {e}")

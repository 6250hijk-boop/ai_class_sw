import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import io

# 구글 드라이브 서비스 연결 함수
def get_drive_service():
    if "gcp_service_account" in st.secrets:
        key_dict = st.secrets["gcp_service_account"]
        
        # 1. 권한 범위(SCOPES) 명시적 지정 (이 부분이 추가되었습니다)
        SCOPES = ['https://www.googleapis.com/auth/drive']
        
        # 2. .with_scopes(SCOPES)를 사용하여 권한 부여
        creds = service_account.Credentials.from_service_account_info(
            key_dict
        ).with_scopes(SCOPES)
    else:
        st.error("구글 API 키가 설정되지 않았습니다. Secrets를 확인해주세요.")
        st.stop()
    return build('drive', 'v3', credentials=creds)

# 서비스 객체 초기화
service = get_drive_service()

# 선생님의 구글 드라이브 폴더 ID (기존 ID 유지)
PARENT_FOLDER_ID = "1i7dospy3B3f4U6Nc3ZEzTk8hB3TCeaWL" 

st.set_page_config(page_title="AI 실습 데이터 수집기", layout="wide")

# 사이드바 메뉴
menu = st.sidebar.radio("메뉴 선택", ["사진 업로드", "공동 라벨링"])

if menu == "사진 업로드":
    st.header("📸 학습용 사진 업로드")
    st.info("우리 반 인공지능 학습을 위해 실습 도구 사진을 찍어 올려주세요.")
    
    files = st.file_uploader("사진 선택", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    
    if st.button("드라이브로 전송"):
        if files:
            progress_bar = st.progress(0)
            for idx, f in enumerate(files):
                try:
                    metadata = {'name': f.name, 'parents': [PARENT_FOLDER_ID]}
                    media = MediaInMemoryUpload(f.getvalue(), mimetype='image/jpeg')
                    service.files().create(body=metadata, media_body=media).execute()
                    progress_bar.progress((idx + 1) / len(files))
                except Exception as e:
                    st.error(f"{f.name} 업로드 실패: {e}")
            st.success(f"{len(files)}장의 사진이 교사용 드라이브에 저장되었습니다!")
        else:
            st.warning("먼저 사진을 선택해주세요.")

elif menu == "공동 라벨링":
    st.header("🏷️ 데이터 라벨링 (YOLO)")
    
    try:
        # 폴더 내 이미지 파일 목록 가져오기
        results = service.files().list(
            q=f"'{PARENT_FOLDER_ID}' in parents and mimeType contains 'image/'",
            fields="files(id, name)").execute()
        items = results.get('files', [])

        if items:
            target_name = st.selectbox("라벨링할 사진 선택", [i['name'] for i in items])
            target_id = [i['id'] for i in items if i['name'] == target_name][0]

            # 이미지 다운로드 및 열기
            req = service.files().get_media(fileId=target_id)
            img = Image.open(io.BytesIO(req.execute()))
            
            st.write(f"현재 사진: {target_name}")
            st.write("박스를 그려 사물의 위치를 알려주세요.")
            
            # 라벨링 캔버스
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                background_image=img,
                height=img.height,
                width=img.width,
                drawing_mode="rect",
                key="canvas",
            )

            if st.button("라벨 저장"):
                if canvas_result.json_data:
                    yolo_data = []
                    for obj in canvas_result.json_data["objects"]:
                        # YOLO 좌표 정규화 계산
                        cx = (obj['left'] + obj['width']/2) / img.width
                        cy = (obj['top'] + obj['height']/2) / img.height
                        w = obj['width'] / img.width
                        h = obj['height'] / img.height
                        yolo_data.append(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                    
                    # .txt 파일로 드라이브에 저장
                    txt_name = target_name.rsplit('.', 1)[0] + ".txt"
                    txt_content = "\n".join(yolo_data).encode()
                    media = MediaInMemoryUpload(txt_content, mimetype='text/plain')
                    service.files().create(
                        body={'name': txt_name, 'parents': [PARENT_FOLDER_ID]}, 
                        media_body=media
                    ).execute()
                    st.success(f"{txt_name} 라벨 데이터가 저장되었습니다!")
        else:
            st.write("업로드된 사진이 없습니다.")
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")

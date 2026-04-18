import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_admin
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from PIL import Image
from collections import defaultdict
import io
import json
import random

# ── 폴더 ID ──
SYSTEM_FOLDER_ID = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"
TRAIN_IMG_ID     = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"
TRAIN_LBL_ID     = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"
VAL_IMG_ID       = "1Q6yhtuoJiJ5b35tIdQyk0KSbskXGheXI"
VAL_LBL_ID       = "1Iym0dtRQ3aTIcdtfzCQa_vtgJRKmfU39"
USERS_FILE       = "users.json"

st.set_page_config(page_title="관리자", page_icon="👑", layout="wide")
check_admin()

@st.cache_resource
def get_drive_service():
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

def load_users():
    svc = get_drive_service()
    query = f"name='{USERS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if not files:
        return {}
    data = svc.files().get_media(fileId=files[0]['id']).execute()
    return json.loads(data.decode('utf-8'))

def save_users(users_dict):
    svc = get_drive_service()
    content = json.dumps(users_dict, ensure_ascii=False, indent=2).encode('utf-8')
    media = MediaInMemoryUpload(content, mimetype='application/json')
    query = f"name='{USERS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if files:
        svc.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        svc.files().create(
            body={'name': USERS_FILE, 'parents': [SYSTEM_FOLDER_ID]},
            media_body=media
        ).execute()

def get_all_train_images():
    svc = get_drive_service()
    query = f"'{TRAIN_IMG_ID}' in parents and mimeType contains 'image/' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

def extract_val_data(ratio=0.2):
    svc = get_drive_service()
    all_imgs = get_all_train_images()
    if not all_imgs:
        return 0, 0
    query = f"'{TRAIN_LBL_ID}' in parents and trashed=false"
    all_lbls = svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    lbl_map = {f['name']: f['id'] for f in all_lbls}
    labeled_imgs = [img for img in all_imgs if img['name'].replace('.jpg', '.txt') in lbl_map]
    if not labeled_imgs:
        return 0, 0
    n_val = max(1, int(len(labeled_imgs) * ratio))
    selected = random.sample(labeled_imgs, n_val)
    copied_imgs = 0
    copied_lbls = 0
    for img in selected:
        img_data = svc.files().get_media(fileId=img['id']).execute()
        q = f"name='{img['name']}' and '{VAL_IMG_ID}' in parents and trashed=false"
        exist = svc.files().list(q=q, fields="files(id)").execute().get('files', [])
        media = MediaInMemoryUpload(img_data, mimetype='image/jpeg')
        if exist:
            svc.files().update(fileId=exist[0]['id'], media_body=media).execute()
        else:
            svc.files().create(
                body={'name': img['name'], 'parents': [VAL_IMG_ID]},
                media_body=media
            ).execute()
        copied_imgs += 1
        lbl_name = img['name'].replace('.jpg', '.txt')
        if lbl_name in lbl_map:
            lbl_data = svc.files().get_media(fileId=lbl_map[lbl_name]).execute()
            q2 = f"name='{lbl_name}' and '{VAL_LBL_ID}' in parents and trashed=false"
            exist2 = svc.files().list(q2, fields="files(id)").execute().get('files', [])
            media2 = MediaInMemoryUpload(lbl_data, mimetype='text/plain')
            if exist2:
                svc.files().update(fileId=exist2[0]['id'], media_body=media2).execute()
            else:
                svc.files().create(
                    body={'name': lbl_name, 'parents': [VAL_LBL_ID]},
                    media_body=media2
                ).execute()
            copied_lbls += 1
    return copied_imgs, copied_lbls

# ── UI ──
st.title("👑 관리자 페이지")
st.divider()

tab_users, tab_files, tab_val = st.tabs(["👥 회원 관리", "🖼️ 전체 데이터", "🔬 검증 데이터 추출"])

# ── 회원 관리 ──
with tab_users:
    st.subheader("등록된 회원 목록")
    users = load_users()
    if not users:
        st.info("등록된 회원이 없습니다.")
    else:
        st.write(f"총 **{len(users)}명**")
        for uid, info in users.items():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"👤 **{uid}** — 가입일: {info.get('created_at','알 수 없음')}")
            with col2:
                if st.button("🗑️ 삭제", key=f"del_{uid}"):
                    del users[uid]
                    save_users(users)
                    st.success(f"'{uid}' 삭제!")
                    st.rerun()

# ── 전체 데이터 ──
with tab_files:
    st.subheader("train/images 전체 파일")
    all_imgs = get_all_train_images()
    if not all_imgs:
        st.info("업로드된 파일이 없습니다.")
    else:
        grouped = defaultdict(list)
        for img in all_imgs:
            uname = img['name'].split('_data')[0] if '_data' in img['name'] else '기타'
            grouped[uname].append(img)
        st.write(f"총 **{len(all_imgs)}장** / **{len(grouped)}명**")
        for uname, imgs in grouped.items():
            with st.expander(f"👤 {uname} ({len(imgs)}장)"):
                svc = get_drive_service()
                cols = st.columns(4)
                for i, img in enumerate(imgs):
                    with cols[i % 4]:
                        img_data = svc.files().get_media(fileId=img['id']).execute()
                        st.image(Image.open(io.BytesIO(img_data)), caption=img['name'], use_column_width=True)

# ── 검증 데이터 추출 ──
with tab_val:
    st.subheader("🔬 검증용 데이터 추출")
    st.info("train 폴더에서 랜덤 추출하여 val 폴더로 복사합니다.")
    all_imgs = get_all_train_images()
    st.write(f"현재 train/images: **{len(all_imgs)}장**")
    ratio = st.slider("검증 데이터 비율 (%)", 5, 40, 20, 5)
    n_expected = max(1, int(len(all_imgs) * ratio / 100))
    st.write(f"추출 예정: 약 **{n_expected}장**")
    if st.button("🚀 검증 데이터 추출 시작", type="primary"):
        with st.spinner("추출 중..."):
            ci, cl = extract_val_data(ratio / 100)
        st.success(f"✅ 이미지 {ci}장, 라벨 {cl}개 → val 폴더 복사 완료!")

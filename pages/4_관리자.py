import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_admin
from utils.firebase import get_db
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from PIL import Image, ImageDraw
from collections import defaultdict
import io, json, random, base64, requests

# ── 구글 드라이브 폴더 ID (사진 저장용) ──
TRAIN_IMG_ID = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"
TRAIN_LBL_ID = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"
VAL_IMG_ID   = "1Q6yhtuoJiJ5b35tIdQyk0KSbskXGheXI"
VAL_LBL_ID   = "1Iym0dtRQ3aTIcdtfzCQa_vtgJRKmfU39"

st.set_page_config(page_title="관리자", page_icon="👑", layout="wide")
check_admin()

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

# ── Firebase 함수 ──
def load_all_users():
    db = get_db()
    docs = db.collection("users").get()
    return {doc.id: doc.to_dict() for doc in docs}

def delete_user(username):
    db = get_db()
    db.collection("users").document(username).delete()

def load_labels():
    db = get_db()
    doc = db.collection("settings").document("labels").get()
    if doc.exists:
        return doc.to_dict().get("list", ["vicpie"])
    return ["vicpie"]

def save_labels(labels_list):
    db = get_db()
    db.collection("settings").document("labels").set({"list": labels_list})

def load_quiz_results():
    db = get_db()
    docs = db.collection("quiz_results").get()
    return {doc.id: doc.to_dict() for doc in docs}

# ── GitHub data.yaml 업데이트 ──
def update_github_yaml(labels_list):
    try:
        token = st.secrets.get("github", {}).get("token", "")
        repo  = st.secrets.get("github", {}).get("repo", "")
        if not token or not repo:
            return False, "GitHub 토큰/레포 설정 없음"
        nc = len(labels_list)
        names_str = "[" + ", ".join(f"'{l}'" for l in labels_list) + "]"
        yaml_content = f"""path: /content/drive/MyDrive/학교/AIClassWebapp
train: train/images
val: val/images

nc: {nc}
names: {names_str}
"""
        encoded = base64.b64encode(yaml_content.encode()).decode()
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        url = f"https://api.github.com/repos/{repo}/contents/data.yaml"
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            sha = r.json()['sha']
            payload = {"message": f"Update data.yaml: {labels_list}", "content": encoded, "sha": sha}
        else:
            payload = {"message": f"Create data.yaml: {labels_list}", "content": encoded}
        r2 = requests.put(url, headers=headers, json=payload)
        if r2.status_code in [200, 201]:
            return True, "GitHub data.yaml 업데이트 완료!"
        else:
            return False, f"GitHub 오류: {r2.status_code}"
    except Exception as e:
        return False, f"실패: {e}"

def get_all_images(folder_id):
    svc = get_drive_service()
    query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

def get_all_labels(folder_id):
    svc = get_drive_service()
    query = f"'{folder_id}' in parents and mimeType='text/plain' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

def delete_drive_file(file_id):
    svc = get_drive_service()
    svc.files().delete(fileId=file_id).execute()

def draw_boxes(img_pil, label_content):
    draw = ImageDraw.Draw(img_pil)
    W, H = img_pil.size
    for line in label_content.strip().split('\n'):
        parts = line.strip().split()
        if len(parts) == 5:
            _, cx, cy, w, h = map(float, parts)
            x1 = int((cx - w/2) * W); y1 = int((cy - h/2) * H)
            x2 = int((cx + w/2) * W); y2 = int((cy + h/2) * H)
            draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
    return img_pil

def extract_val_data(ratio=0.2):
    svc = get_drive_service()
    all_imgs = get_all_images(TRAIN_IMG_ID)
    if not all_imgs:
        return 0, 0
    all_lbls = get_all_labels(TRAIN_LBL_ID)
    lbl_map = {f['name']: f['id'] for f in all_lbls}
    labeled_imgs = [img for img in all_imgs if img['name'].replace('.jpg', '.txt') in lbl_map]
    if not labeled_imgs:
        return 0, 0
    n_val = max(1, int(len(labeled_imgs) * ratio))
    selected = random.sample(labeled_imgs, n_val)
    ci = cl = 0
    for img in selected:
        img_data = svc.files().get_media(fileId=img['id']).execute()
        q = f"name='{img['name']}' and '{VAL_IMG_ID}' in parents and trashed=false"
        exist = svc.files().list(q=q, fields="files(id)").execute().get('files', [])
        media = MediaInMemoryUpload(img_data, mimetype='image/jpeg')
        if exist:
            svc.files().update(fileId=exist[0]['id'], media_body=media).execute()
        else:
            svc.files().create(body={'name': img['name'], 'parents': [VAL_IMG_ID]}, media_body=media).execute()
        ci += 1
        lbl_name = img['name'].replace('.jpg', '.txt')
        if lbl_name in lbl_map:
            lbl_data = svc.files().get_media(fileId=lbl_map[lbl_name]).execute()
            q2 = f"name='{lbl_name}' and '{VAL_LBL_ID}' in parents and trashed=false"
            exist2 = svc.files().list(q=q2, fields="files(id)").execute().get('files', [])
            media2 = MediaInMemoryUpload(lbl_data, mimetype='text/plain')
            if exist2:
                svc.files().update(fileId=exist2[0]['id'], media_body=media2).execute()
            else:
                svc.files().create(body={'name': lbl_name, 'parents': [VAL_LBL_ID]}, media_body=media2).execute()
            cl += 1
    return ci, cl

# ════════════════════════════════════════════
#  UI
# ════════════════════════════════════════════
st.title("👑 관리자 페이지")
st.divider()

tab_users, tab_data, tab_val, tab_labels, tab_quiz = st.tabs([
    "👥 회원 관리", "🖼️ 데이터 관리", "🔬 검증 데이터 추출", "🏷️ 라벨 관리", "📝 퀴즈 현황"
])

# ════════ 탭1: 회원 관리 ════════
with tab_users:
    st.subheader("등록된 회원 목록")
    users = load_all_users()
    all_train_imgs = get_all_images(TRAIN_IMG_ID)
    all_train_lbls = get_all_labels(TRAIN_LBL_ID)

    if not users:
        st.info("등록된 회원이 없습니다.")
    else:
        st.write(f"총 **{len(users)}명**")
        st.divider()
        for uid, info in users.items():
            stunum = info.get('student_num', '-')
            name   = info.get('name', '-')
            email  = info.get('email', '-')
            prefix = f"{stunum}_{name}"
            img_count = sum(1 for f in all_train_imgs if f['name'].startswith(prefix + '_data'))
            lbl_count = sum(1 for f in all_train_lbls if f['name'].startswith(prefix + '_data'))

            with st.expander(f"🎓 {stunum} | {name} | 사진 {img_count}장 | 라벨 {lbl_count}개"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("학번", stunum)
                col2.metric("이름", name)
                col3.metric("업로드", f"{img_count}장")
                col4.metric("라벨링", f"{lbl_count}개")
                st.caption(f"📧 {email} | 가입일: {info.get('created_at','-')}")

                student_imgs = [f for f in all_train_imgs if f['name'].startswith(prefix + '_data')]
                student_lbls = {f['name']: f['id'] for f in all_train_lbls if f['name'].startswith(prefix + '_data')}

                if student_imgs:
                    svc = get_drive_service()
                    cols = st.columns(4)
                    for i, img in enumerate(student_imgs):
                        with cols[i % 4]:
                            try:
                                img_data = svc.files().get_media(fileId=img['id']).execute()
                                img_pil  = Image.open(io.BytesIO(img_data)).convert("RGB")
                                lbl_name = img['name'].replace('.jpg', '.txt')
                                has_label = lbl_name in student_lbls
                                if has_label:
                                    lbl_data = svc.files().get_media(fileId=student_lbls[lbl_name]).execute()
                                    img_pil  = draw_boxes(img_pil, lbl_data.decode('utf-8'))
                                icon = "🟢" if has_label else "🔴"
                                st.image(img_pil, caption=f"{icon} {img['name']}", width=150)
                                if st.button("🗑️ 삭제", key=f"del_img_{img['id']}"):
                                    delete_drive_file(img['id'])
                                    if has_label:
                                        delete_drive_file(student_lbls[lbl_name])
                                    st.success("삭제 완료!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"로드 실패: {e}")

                st.divider()
                if st.button(f"🗑️ 회원 삭제", key=f"del_user_{uid}", type="secondary"):
                    delete_user(uid)
                    st.success(f"'{uid}' 삭제!")
                    st.rerun()

# ════════ 탭2: 데이터 관리 ════════
with tab_data:
    st.subheader("🖼️ 전체 데이터 현황")
    with st.expander("📂 Train 데이터", expanded=True):
        all_train_imgs = get_all_images(TRAIN_IMG_ID)
        all_train_lbls = get_all_labels(TRAIN_LBL_ID)
        lbl_map = {f['name']: f['id'] for f in all_train_lbls}
        labeled   = sum(1 for f in all_train_imgs if f['name'].replace('.jpg','.txt') in lbl_map)
        unlabeled = len(all_train_imgs) - labeled
        col1, col2, col3 = st.columns(3)
        col1.metric("전체 이미지", f"{len(all_train_imgs)}장")
        col2.metric("라벨링 완료", f"{labeled}개")
        col3.metric("라벨링 미완료", f"{unlabeled}개")
    with st.expander("📂 Val 데이터"):
        all_val_imgs = get_all_images(VAL_IMG_ID)
        all_val_lbls = get_all_labels(VAL_LBL_ID)
        col1, col2 = st.columns(2)
        col1.metric("검증 이미지", f"{len(all_val_imgs)}장")
        col2.metric("검증 라벨", f"{len(all_val_lbls)}개")

# ════════ 탭3: 검증 데이터 추출 ════════
with tab_val:
    st.subheader("🔬 검증용 데이터 추출")
    st.info("train 폴더에서 랜덤 추출하여 val 폴더로 복사합니다.")
    all_imgs = get_all_images(TRAIN_IMG_ID)
    st.write(f"현재 train/images: **{len(all_imgs)}장**")
    ratio = st.slider("검증 데이터 비율 (%)", 5, 40, 20, 5)
    n_expected = max(1, int(len(all_imgs) * ratio / 100))
    st.write(f"추출 예정: 약 **{n_expected}장**")
    if st.button("🚀 검증 데이터 추출 시작", type="primary"):
        with st.spinner("추출 중..."):
            ci, cl = extract_val_data(ratio / 100)
        st.success(f"✅ 이미지 {ci}장, 라벨 {cl}개 → val 폴더 복사 완료!")

# ════════ 탭4: 라벨 관리 ════════
with tab_labels:
    st.subheader("🏷️ 라벨 목록 관리")
    st.info("여기서 설정한 라벨이 학생 라벨링 화면에 표시됩니다.")
    current_labels = load_labels()

    st.markdown("**현재 라벨 목록:**")
    for i, label in enumerate(current_labels):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**{i+1}.** {label}")
        with col2:
            if st.button("🗑️ 삭제", key=f"del_label_{i}"):
                current_labels.pop(i)
                save_labels(current_labels)
                ok, msg = update_github_yaml(current_labels)
                st.success(f"'{label}' 삭제! {msg}")
                st.rerun()

    st.divider()
    st.markdown("**새 라벨 추가:**")
    col1, col2 = st.columns([4, 1])
    with col1:
        new_label = st.text_input("라벨 이름 입력", placeholder="예: apple, vicpie ...", key="new_label_input")
    with col2:
        st.write(""); st.write("")
        if st.button("➕ 추가", type="primary"):
            if new_label:
                if new_label in current_labels:
                    st.error("이미 존재하는 라벨입니다!")
                else:
                    current_labels.append(new_label)
                    save_labels(current_labels)
                    ok, msg = update_github_yaml(current_labels)
                    st.success(f"✅ '{new_label}' 추가! {msg}")
                    st.rerun()
            else:
                st.error("라벨 이름을 입력하세요.")

    st.divider()
    if st.button("🗑️ 전체 초기화", type="secondary"):
        save_labels([])
        update_github_yaml([])
        st.success("전체 라벨 초기화 완료!")
        st.rerun()

    st.divider()
    st.markdown("**🔄 GitHub data.yaml 수동 동기화:**")
    if st.button("🔄 GitHub 동기화", type="primary"):
        with st.spinner("GitHub 업데이트 중..."):
            ok, msg = update_github_yaml(current_labels)
        if ok:
            st.success(f"✅ {msg}")
        else:
            st.error(f"❌ {msg}")

# ════════ 탭5: 퀴즈 현황 ════════
with tab_quiz:
    st.subheader("📝 학생별 퀴즈 현황")
    quiz_results = load_quiz_results()
    users = load_all_users()

    if not quiz_results:
        st.info("아직 퀴즈를 푼 학생이 없습니다.")
    else:
        total_attempts = sum(
            len(v) for data in quiz_results.values()
            for v in (data.values() if isinstance(data, dict) else [data])
        )
        st.metric("전체 퀴즈 응시 횟수", f"{total_attempts}회")
        st.divider()

        for uid, quiz_data in quiz_results.items():
            user_info = users.get(uid, {})
            stunum = user_info.get('student_num', '-')
            name   = user_info.get('name', uid)

            with st.expander(f"🎓 {stunum} | {name} | {uid}"):
                if isinstance(quiz_data, dict):
                    for quiz_name, attempts in quiz_data.items():
                        if not isinstance(attempts, list):
                            continue
                        st.markdown(f"**📋 {quiz_name}**")
                        scores     = [a['score'] for a in attempts]
                        totals     = [a['total'] for a in attempts]
                        best_score = max(scores)
                        best_total = totals[scores.index(best_score)]
                        avg_score  = sum(scores) / len(scores)
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("응시 횟수", f"{len(attempts)}회")
                        col2.metric("최고 점수", f"{best_score}/{best_total}")
                        col3.metric("평균 점수", f"{avg_score:.1f}점")
                        col4.metric("최고 점수(%)", f"{int(best_score/best_total*100)}%")
                        for attempt in reversed(attempts):
                            pct = int(attempt['score'] / attempt['total'] * 100)
                            color = "🟢" if pct >= 80 else "🟡" if pct >= 60 else "🔴"
                            st.caption(f"{color} {attempt['date']} | {attempt['score']}/{attempt['total']}점 ({pct}%)")
                            if attempt.get('wrong'):
                                with st.expander(f"❌ 틀린 문제 ({attempt['date']})", expanded=False):
                                    for q in attempt['wrong']:
                                        st.write(f"• {q}")
                        st.divider()

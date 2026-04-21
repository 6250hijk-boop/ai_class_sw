import streamlit as st
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import check_admin
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from PIL import Image, ImageDraw
from collections import defaultdict
import io, json, random

SYSTEM_FOLDER_ID = "1_zMtw7RDvOAZ3P7o2rNCKeO4DhKdZ3nv"
TRAIN_IMG_ID     = "1vAmEqTkOfI7GELAOYBSknv0zhMX00RPv"
TRAIN_LBL_ID     = "1WarT3vOu4alUk-g_262yhTI_unSew7cR"
VAL_IMG_ID       = "1Q6yhtuoJiJ5b35tIdQyk0KSbskXGheXI"
VAL_LBL_ID       = "1Iym0dtRQ3aTIcdtfzCQa_vtgJRKmfU39"
USERS_FILE       = "users.json"

st.set_page_config(page_title="관리자", page_icon="👑", layout="wide")
check_admin()

def get_drive_service():
    """매번 새로운 서비스 객체 생성 (SSL 오류 방지)"""
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

LABELS_FILE = "labels.json"

def load_labels():
    svc = get_drive_service()
    query = f"name='{LABELS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if not files:
        return ["vicpie"]
    data = svc.files().get_media(fileId=files[0]['id']).execute()
    return json.loads(data.decode('utf-8'))

def save_labels(labels_list):
    svc = get_drive_service()
    content = json.dumps(labels_list, ensure_ascii=False, indent=2).encode('utf-8')
    media = MediaInMemoryUpload(content, mimetype='application/json')
    query = f"name='{LABELS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if files:
        svc.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        svc.files().create(
            body={'name': LABELS_FILE, 'parents': [SYSTEM_FOLDER_ID]},
            media_body=media
        ).execute()

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

def get_all_images(folder_id):
    svc = get_drive_service()
    query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

def get_all_labels(folder_id):
    svc = get_drive_service()
    query = f"'{folder_id}' in parents and mimeType='text/plain' and trashed=false"
    return svc.files().list(q=query, fields="files(id, name)").execute().get('files', [])

def delete_file(file_id):
    svc = get_drive_service()
    svc.files().delete(fileId=file_id).execute()

def draw_boxes_on_image(img_pil, label_content):
    """라벨 txt 내용을 파싱해서 이미지에 박스 그리기"""
    draw = ImageDraw.Draw(img_pil)
    W, H = img_pil.size
    lines = label_content.strip().split('\n')
    for line in lines:
        parts = line.strip().split()
        if len(parts) == 5:
            _, cx, cy, w, h = map(float, parts)
            x1 = int((cx - w/2) * W)
            y1 = int((cy - h/2) * H)
            x2 = int((cx + w/2) * W)
            y2 = int((cy + h/2) * H)
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
            svc.files().create(body={'name': img['name'], 'parents': [VAL_IMG_ID]}, media_body=media).execute()
        copied_imgs += 1
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
            copied_lbls += 1
    return copied_imgs, copied_lbls

QUIZ_RESULTS_FILE = "quiz_results.json"

def load_quiz_results():
    try:
        svc = get_drive_service()
        query = f"name='{QUIZ_RESULTS_FILE}' and '{SYSTEM_FOLDER_ID}' in parents and trashed=false"
        files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
        if not files:
            return {}
        data = svc.files().get_media(fileId=files[0]['id']).execute()
        return json.loads(data.decode('utf-8'))
    except:
        return {}

# ════════════════════════════════════════════
#  UI
# ════════════════════════════════════════════
st.title("👑 관리자 페이지")
st.divider()

tab_users, tab_data, tab_val, tab_labels, tab_quiz = st.tabs([
    "👥 회원 관리", "🖼️ 데이터 관리", "🔬 검증 데이터 추출", "🏷️ 라벨 관리", "📝 퀴즈 현황"
])

# ════════ 탭5: 퀴즈 현황 ════════
with tab_quiz:
    st.subheader("📝 학생별 퀴즈 현황")

    quiz_results = load_quiz_results()
    users = load_users()

    if not quiz_results:
        st.info("아직 퀴즈를 푼 학생이 없습니다.")
    else:
        # 전체 통계
        total_attempts = sum(
            len(attempts)
            for user_data in quiz_results.values()
            for attempts in user_data.values()
        )
        st.metric("전체 퀴즈 응시 횟수", f"{total_attempts}회")
        st.divider()

        # 학생별 결과
        for uid, quiz_data in quiz_results.items():
            # 학번/이름 가져오기
            user_info = users.get(uid, {})
            stunum = user_info.get('student_num', '-')
            name   = user_info.get('name', uid)

            with st.expander(f"🎓 {stunum} | {name} | {uid}"):
                for quiz_name, attempts in quiz_data.items():
                    st.markdown(f"**📋 {quiz_name}**")

                    # 시도 횟수, 최고점, 평균점
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

                    # 응시 기록
                    st.markdown("**응시 기록:**")
                    for j, attempt in enumerate(reversed(attempts)):
                        pct = int(attempt['score'] / attempt['total'] * 100)
                        color = "🟢" if pct >= 80 else "🟡" if pct >= 60 else "🔴"
                        st.caption(
                            f"{color} {attempt['date']} | "
                            f"{attempt['score']}/{attempt['total']}점 ({pct}%) | "
                            f"틀린 문제: {len(attempt.get('wrong', []))}개"
                        )
                        # 틀린 문제 보기
                        if attempt.get('wrong'):
                            with st.expander(f"❌ 틀린 문제 보기 ({attempt['date']})", expanded=False):
                                for wrong_q in attempt['wrong']:
                                    st.write(f"• {wrong_q}")
                    st.divider()


# ════════ 탭4: 라벨 관리 ════════
with tab_labels:
    st.subheader("🏷️ 라벨 목록 관리")
    st.info("여기서 설정한 라벨이 학생 라벨링 화면에 표시됩니다.")

    current_labels = load_labels()

    # 현재 라벨 목록
    st.markdown("**현재 라벨 목록:**")
    for i, label in enumerate(current_labels):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**{i+1}.** {label}")
        with col2:
            if st.button("🗑️ 삭제", key=f"del_label_{i}"):
                current_labels.pop(i)
                save_labels(current_labels)
                st.success(f"'{label}' 삭제!")
                st.rerun()

    st.divider()

    # 새 라벨 추가
    st.markdown("**새 라벨 추가:**")
    col1, col2 = st.columns([4, 1])
    with col1:
        new_label = st.text_input("라벨 이름 입력", placeholder="예: apple, vicpie, 사과 ...", key="new_label_input")
    with col2:
        st.write("")
        st.write("")
        if st.button("➕ 추가", type="primary"):
            if new_label:
                if new_label in current_labels:
                    st.error("이미 존재하는 라벨입니다!")
                else:
                    current_labels.append(new_label)
                    save_labels(current_labels)
                    st.success(f"✅ '{new_label}' 추가 완료!")
                    st.rerun()
            else:
                st.error("라벨 이름을 입력하세요.")

    st.divider()
    # 전체 초기화
    if st.button("🗑️ 전체 초기화", type="secondary"):
        save_labels([])
        st.success("전체 라벨 초기화 완료!")
        st.rerun()


# ════════ 탭1: 회원 관리 ════════
with tab_users:
    st.subheader("등록된 회원 목록")
    users = load_users()

    # 전체 이미지/라벨 목록 미리 가져오기
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

            # 해당 학생 파일 수 계산
            img_count = sum(1 for f in all_train_imgs if f['name'].startswith(prefix + '_data'))
            lbl_count = sum(1 for f in all_train_lbls if f['name'].startswith(prefix + '_data'))

            with st.expander(f"🎓 {stunum} | {name} | 사진 {img_count}장 | 라벨 {lbl_count}개"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("학번", stunum)
                col2.metric("이름", name)
                col3.metric("업로드", f"{img_count}장")
                col4.metric("라벨링", f"{lbl_count}개")
                st.caption(f"📧 {email} | 가입일: {info.get('created_at','-')}")

                # 해당 학생 이미지 목록
                student_imgs = [f for f in all_train_imgs if f['name'].startswith(prefix + '_data')]
                student_lbls = {f['name']: f['id'] for f in all_train_lbls if f['name'].startswith(prefix + '_data')}

                if student_imgs:
                    st.markdown("**📸 업로드된 사진 (클릭하면 삭제)**")
                    svc = get_drive_service()
                    cols = st.columns(4)
                    for i, img in enumerate(student_imgs):
                        with cols[i % 4]:
                            try:
                                img_data = svc.files().get_media(fileId=img['id']).execute()
                                img_pil  = Image.open(io.BytesIO(img_data)).convert("RGB")

                                # 라벨 있으면 박스 그리기
                                lbl_name = img['name'].replace('.jpg', '.txt')
                                has_label = lbl_name in student_lbls
                                if has_label:
                                    lbl_data = svc.files().get_media(fileId=student_lbls[lbl_name]).execute()
                                    lbl_text = lbl_data.decode('utf-8')
                                    img_pil  = draw_boxes_on_image(img_pil, lbl_text)

                                label_icon = "🟢" if has_label else "🔴"
                                st.image(img_pil, caption=f"{label_icon} {img['name']}", use_column_width=True)

                                # 삭제 버튼
                                if st.button(f"🗑️ 삭제", key=f"del_img_{img['id']}"):
                                    delete_file(img['id'])
                                    if has_label:
                                        delete_file(student_lbls[lbl_name])
                                    st.success(f"삭제 완료!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"로드 실패: {e}")

                st.divider()
                if st.button(f"🗑️ 회원 삭제", key=f"del_user_{uid}", type="secondary"):
                    del users[uid]
                    save_users(users)
                    st.success(f"'{uid}' 삭제!")
                    st.rerun()

# ════════ 탭2: 데이터 관리 ════════
with tab_data:
    st.subheader("🖼️ 전체 데이터 현황")

    # train 데이터
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

    # val 데이터
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

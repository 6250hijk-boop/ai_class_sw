# (상단 import 및 get_drive_service 등 기존 코드는 유지)
# [수정 부분] 박스 저장 시 인덱스 자동 계산 로직 적용

# ... (기존 유틸 함수들) ...

def save_label(file_name, content):
    svc = get_drive_service()
    media = MediaInMemoryUpload(content, mimetype='text/plain')
    query = f"name='{file_name}' and '{TRAIN_LBL_ID}' in parents and trashed=false"
    files = svc.files().list(q=query, fields="files(id)").execute().get('files', [])
    if files:
        svc.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        svc.files().create(body={'name': file_name, 'parents': [TRAIN_LBL_ID]}, media_body=media).execute()

# ... (UI 구성 부분) ...

# [핵심] 라벨 번호(인덱스) 찾기
all_labels = load_labels()
current_label_name = st.session_state.vision_labels[0]
# 관리자가 설정한 목록에서 현재 선택된 라벨의 순서(0, 1, 2...)를 찾음
label_index = all_labels.index(current_label_name) if current_label_name in all_labels else 0

# ... (이미지 클릭 처리 부분) ...
if len(st.session_state.click_coords) == 2:
    c = st.session_state.click_coords
    l, r = min(c[0][0],c[1][0]), max(c[0][0],c[1][0])
    t, b = min(c[0][1],c[1][1]), max(c[0][1],c[1][1])
    x, y = (l+r)/2/640, (t+b)/2/640
    w, h = (r-l)/640, (b-t)/640
    # '0' 대신 동기화된 label_index를 사용해 저장
    st.session_state.temp_boxes.append(f"{label_index} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
    st.session_state.click_coords = []
    st.rerun()

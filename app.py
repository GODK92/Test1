"""쇼핑 리스트 Streamlit 앱.

데이터는 storage 모듈로만 다룬다. 상태를 바꾸는 동작은 모두 위젯 콜백에서
처리하므로, 콜백이 끝난 뒤 다시 그려지는 화면에 변경 내용이 바로 반영된다.
"""

import functools
import html

import streamlit as st

import storage

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")

FILTER_ALL, FILTER_TODO, FILTER_DONE = "전체", "미완료", "완료"

# session_state 키
EDITING_ID = "editing_id"        # 편집 중인 아이템 id (한 번에 하나)
CONFIRM_CLEAR = "confirm_clear"  # 체크된 항목 일괄 삭제 확인 중 여부
MESSAGES = "messages"            # 콜백에서 남긴 알림 [(종류, 문구)]
NEW_NAME, NEW_QTY = "new_name", "new_qty"
FILTER = "filter"


# ---------- 공통 도우미 ----------

def init_state() -> None:
    """session_state 기본값을 설정한다."""
    st.session_state.setdefault(EDITING_ID, None)
    st.session_state.setdefault(CONFIRM_CLEAR, False)
    st.session_state.setdefault(MESSAGES, [])
    st.session_state.setdefault(NEW_QTY, 1)
    st.session_state.setdefault(FILTER, FILTER_ALL)


def notify(kind: str, text: str) -> None:
    """다음 화면에 보여줄 알림을 남긴다. kind는 'success' 또는 'warning'."""
    st.session_state[MESSAGES].append((kind, text))


def show_messages() -> None:
    """남겨 둔 알림을 보여주고 비운다. 성공은 토스트, 경고는 경고 박스로 표시한다."""
    for kind, text in st.session_state[MESSAGES]:
        if kind == "success":
            st.toast(text, icon="✅")
        else:
            st.warning(text, icon="⚠️")
    st.session_state[MESSAGES] = []


def normalize(name: str) -> str:
    """중복 비교용으로 공백과 대소문자를 무시한 이름을 만든다."""
    return "".join(name.split()).casefold()


def has_duplicate(name: str, exclude_id: str | None = None) -> bool:
    """같은 이름(공백·대소문자 무시)의 아이템이 이미 있는지 확인한다."""
    key = normalize(name)
    return any(
        normalize(item["name"]) == key and item["id"] != exclude_id
        for item in storage.load_items()
    )


# 마크다운 서식, LaTeX($), HTML(<, >, &), Streamlit 지시어(:)에 쓰이는 기호
_MD_SPECIAL = set("\\`*_{}[]()#+-.!|~<>$:&@=^\"'")
# 자동 링크(https://, www., 이메일)를 만드는 기호. 앞뒤에 보이지 않는 단어 결합자(U+2060)를 넣어 끊는다.
_AUTOLINK_BREAK = set(":.@")
_WORD_JOINER = "&#8288;"


def escape_md(text: str) -> str:
    """마크다운으로만 표시되는 곳(토스트, 경고)에서 입력한 글자를 그대로 보이게 바꾼다.

    특수 기호는 숫자 문자 참조(&#NN;)로 바꿔 서식·수식·HTML로 해석되지 않게 한다.
    Streamlit은 문자 참조를 해석한 뒤 URL을 자동 링크로 만들기 때문에, : . @ 앞뒤에
    보이지 않는 단어 결합자를 넣어 'www.', 'https:', 'a@b' 같은 링크 패턴을 끊는다.
    """
    out = []
    for c in text:
        if c in _AUTOLINK_BREAK:
            out.append(f"{_WORD_JOINER}&#{ord(c)};{_WORD_JOINER}")
        elif c in _MD_SPECIAL:
            out.append(f"&#{ord(c)};")
        else:
            out.append(c)
    return "".join(out)


def guarded(callback):
    """콜백에서 저장 오류가 나면 에러 화면 대신 경고를 보여주도록 감싼다."""
    @functools.wraps(callback)
    def wrapper(*args, **kwargs):
        try:
            return callback(*args, **kwargs)
        except storage.StorageError as e:
            notify("warning", str(e))
    return wrapper


def sort_items(items: list[dict]) -> list[dict]:
    """미완료를 위, 완료를 아래로 두고, 각 그룹 안에서는 추가한 순서를 유지한다."""
    return sorted(items, key=lambda item: (bool(item.get("checked")), item.get("created_at", "")))


# ---------- 콜백 ----------

@guarded
def on_add() -> None:
    """추가 폼 제출: 검증 후 아이템을 추가하고 입력창을 비운다."""
    name = (st.session_state.get(NEW_NAME) or "").strip()
    if not name:
        notify("warning", "아이템 이름을 입력해 주세요.")
        return
    duplicate = has_duplicate(name)
    try:
        storage.add_item(name, st.session_state.get(NEW_QTY, 1))
    except ValueError as e:
        notify("warning", str(e))
        return
    if duplicate:
        notify("warning", f"'{escape_md(name)}'은(는) 이미 리스트에 있어요. 그래도 추가했어요.")
    notify("success", f"'{escape_md(name)}' 추가했어요.")
    st.session_state[NEW_NAME] = ""
    st.session_state[NEW_QTY] = 1


@guarded
def on_toggle(item_id: str) -> None:
    """체크박스 변경을 저장한다."""
    try:
        storage.update_item(item_id, checked=st.session_state[f"chk_{item_id}"])
    except KeyError:
        notify("warning", "이미 삭제된 아이템이에요.")


def on_start_edit(item: dict) -> None:
    """편집 모드로 들어가며 입력창에 현재 값을 채운다. 다른 아이템 편집 중이면 그 편집은 취소된다."""
    st.session_state[EDITING_ID] = item["id"]
    st.session_state[f"edit_name_{item['id']}"] = item["name"]
    st.session_state[f"edit_qty_{item['id']}"] = item.get("quantity", 1)


@guarded
def on_save_edit(item_id: str) -> None:
    """편집 내용을 검증 후 저장한다. 실패하면 편집 모드를 유지한다."""
    name = (st.session_state.get(f"edit_name_{item_id}") or "").strip()
    if not name:
        notify("warning", "아이템 이름을 입력해 주세요.")
        return
    duplicate = has_duplicate(name, exclude_id=item_id)
    try:
        storage.update_item(item_id, name=name, quantity=st.session_state.get(f"edit_qty_{item_id}", 1))
    except ValueError as e:
        notify("warning", str(e))
        return
    except KeyError:
        notify("warning", "이미 삭제된 아이템이에요.")
    else:
        if duplicate:
            notify("warning", f"'{escape_md(name)}'은(는) 이미 리스트에 있어요. 그래도 저장했어요.")
        notify("success", "수정했어요.")
    st.session_state[EDITING_ID] = None


def on_cancel_edit() -> None:
    """편집을 취소한다."""
    st.session_state[EDITING_ID] = None


@guarded
def on_delete(item_id: str, name: str) -> None:
    """아이템 하나를 바로 삭제한다."""
    storage.delete_item(item_id)
    if st.session_state[EDITING_ID] == item_id:
        st.session_state[EDITING_ID] = None
    notify("success", f"'{escape_md(name)}' 삭제했어요.")


def on_ask_clear() -> None:
    """체크된 항목 일괄 삭제 확인 단계를 연다."""
    st.session_state[CONFIRM_CLEAR] = True


@guarded
def on_confirm_clear() -> None:
    """체크된 항목을 모두 삭제한다."""
    removed = storage.delete_checked()
    st.session_state[CONFIRM_CLEAR] = False
    editing = st.session_state[EDITING_ID]
    if editing and editing not in {item["id"] for item in storage.load_items()}:
        st.session_state[EDITING_ID] = None
    notify("success", f"체크된 항목 {removed}개를 삭제했어요.")


def on_filter_change() -> None:
    """필터의 선택된 옵션을 다시 눌러 선택이 해제되면 '전체'로 되돌린다."""
    if st.session_state.get(FILTER) is None:
        st.session_state[FILTER] = FILTER_ALL


def on_cancel_clear() -> None:
    """일괄 삭제를 취소한다."""
    st.session_state[CONFIRM_CLEAR] = False


# ---------- 화면 ----------

# 앱 전체에 쓰는 CSS는 여기 한 곳에서만 관리한다.
CSS = """
<style>
/* 모바일(640px 이하)에서도 st.columns가 세로로 쌓이지 않고 한 줄을 유지하게 한다. */
[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
[data-testid="stColumn"] { min-width: 0 !important; }

/* 버튼 터치 영역 최소 40px */
.stButton button, .stFormSubmitButton button, .st-key-filter button { min-height: 40px; }

/* 아이템 카드 */
[class*="st-key-item_"] { padding: 0.3rem 0.6rem 0.3rem 0.9rem !important; gap: 0.5rem !important; }
[class*="st-key-item_"] p { margin: 0; overflow-wrap: anywhere; line-height: 1.4; }
[class*="st-key-item_"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.item-name { margin: 0; line-height: 1.4; overflow-wrap: anywhere; }
.item-name.done { opacity: 0.7; }
.qty { opacity: 0.72; font-size: 0.9em; margin-left: 0.35rem; white-space: nowrap; }

/* 아이콘 버튼: 평소엔 은은하게, 삭제는 마우스를 올리면 빨갛게 */
[class*="st-key-edit_"] button, [class*="st-key-del_"] button { font-size: 1.1rem; padding: 0; min-width: 40px; }
[class*="st-key-del_"] button:hover { background: rgba(220, 53, 69, 0.12); }
/* 아이콘 버튼의 글자("수정"/"삭제")는 화면 낭독기용으로만 남기고 눈에는 숨긴다. */
[class*="st-key-edit_"] button [data-testid="stMarkdownContainer"],
[class*="st-key-del_"] button [data-testid="stMarkdownContainer"] {
  position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap;
}

/* 일괄 삭제 버튼은 오른쪽 정렬 */
.st-key-clear_ask { align-self: flex-end; }

/* 빈 상태 */
.empty-state { text-align: center; padding: 2.5rem 1rem 2rem; }
.empty-state .icon { font-size: 3rem; line-height: 1; margin-bottom: 0.75rem; }
.empty-state .title { font-weight: 700; font-size: 1.1rem; margin: 0 0 0.25rem; }
.empty-state .desc { opacity: 0.6; margin: 0; }

/* 진행 현황 */
.progress-text { margin: -0.5rem 0 0.25rem; opacity: 0.75; }
.progress-text b { opacity: 1; }

@media (max-width: 640px) {
  [data-testid="stHorizontalBlock"] { gap: 0.5rem !important; }
  /* 좁은 화면에서는 수량 +/- 버튼을 숨겨 숫자 칸을 넓힌다 (숫자 키패드로 입력). */
  .st-key-new_qty [data-testid="stNumberInputStepDown"],
  .st-key-new_qty [data-testid="stNumberInputStepUp"] { display: none; }
  h1 { font-size: 2rem !important; }
  /* 하단은 좁은 화면에서 필터 한 줄, 그 아래 일괄 삭제 버튼으로 쌓는다. */
  .st-key-footer [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
  .st-key-footer [data-testid="stColumn"] { min-width: 100% !important; }
}
</style>
"""


def render_header(items: list[dict]) -> None:
    """제목과 진행 현황 (F-09). 다 샀으면 축하 메시지를 보여준다."""
    st.title("🛒 쇼핑 리스트")
    total = len(items)
    if not total:
        return
    done = sum(1 for item in items if item.get("checked"))
    st.markdown(
        f'<p class="progress-text"><b>{done}</b> / {total} 완료</p>', unsafe_allow_html=True
    )
    st.progress(done / total)
    if done == total:
        st.success("모두 담았어요! 장보기 완료 🎉")


def render_add_form() -> None:
    """아이템 추가 폼 (F-01, F-07). 이름이 가장 넓고 수량·추가 버튼은 오른쪽에 둔다. Enter로도 제출된다."""
    with st.form("add_form", border=True):
        col_name, col_qty, col_btn = st.columns([5, 2.2, 1.8], vertical_alignment="bottom")
        # 글자 수와 수량 범위는 브라우저에서 막지 않고 storage에서 검증한다.
        # (max_chars는 긴 텍스트 붙여넣기를 통째로 무시하고, min/max는 범위 밖 값을
        #  서버로 보내지 않아 폼이 잠기기 때문)
        col_name.text_input("아이템 이름", key=NEW_NAME, placeholder="예: 우유")
        col_qty.number_input("수량", key=NEW_QTY, step=1)
        col_btn.form_submit_button("추가", on_click=on_add, type="primary", use_container_width=True)


def render_edit_row(item_id: str) -> None:
    """편집 모드: 이름은 한 줄 전체, 그 아래 수량과 저장·취소 버튼."""
    st.text_input("이름 수정", key=f"edit_name_{item_id}")
    col_qty, col_save, col_cancel = st.columns([2, 1.5, 1.5], vertical_alignment="bottom")
    col_qty.number_input("수량", key=f"edit_qty_{item_id}", step=1)
    col_save.button("저장", key=f"save_{item_id}", on_click=on_save_edit, args=(item_id,),
                    type="primary", use_container_width=True)
    col_cancel.button("취소", key=f"cancel_{item_id}", on_click=on_cancel_edit,
                      use_container_width=True)


def render_item(item: dict) -> None:
    """아이템 카드 한 장 (F-02~F-05). 삭제 버튼은 실수로 누르지 않게 오른쪽 끝에 둔다."""
    item_id = item["id"]
    with st.container(border=True, key=f"item_{item_id}"):
        if st.session_state[EDITING_ID] == item_id:
            render_edit_row(item_id)
            return

        checked = bool(item.get("checked"))
        # st.columns(4개) 대신 가로 컨테이너 하나를 쓴다. 아이템마다 그려야 할 요소가 줄어
        # 아이템 100개에서 클릭 반영 시간이 약 1.3초 → 0.9초로 줄었다.
        row = st.container(horizontal=True, vertical_alignment="center", gap="small")
        # 라벨은 화면에 보이지 않고(collapsed) 화면 낭독기의 aria-label로만 쓰이므로 원래 이름을 그대로 넘긴다.
        row.checkbox(
            item["name"], key=f"chk_{item_id}", value=checked, label_visibility="collapsed",
            on_change=on_toggle, args=(item_id,),
        )
        # 이름은 <p>로 시작하는 HTML 블록으로 넘긴다. HTML 블록 안은 마크다운으로 해석되지 않으므로
        # 서식·수식·자동 링크(URL, 이메일)가 생기지 않고, html.escape로 태그와 &도 글자 그대로 보인다.
        name = html.escape(item["name"])
        if checked:
            name = f"<del>{name}</del>"
        row.markdown(
            f'<p class="item-name{" done" if checked else ""}">{name}'
            f'<span class="qty">× {item["quantity"]}</span></p>',
            unsafe_allow_html=True, width="stretch",
        )
        row.button("수정", icon="✏️", key=f"edit_{item_id}", help="수정", type="tertiary",
                   on_click=on_start_edit, args=(item,))
        row.button("삭제", icon="🗑️", key=f"del_{item_id}", help="삭제", type="tertiary",
                   on_click=on_delete, args=(item_id, item["name"]))


def render_empty_state() -> None:
    """아이템이 하나도 없을 때의 안내."""
    st.markdown(
        '<div class="empty-state"><div class="icon">🧺</div>'
        '<p class="title">리스트가 비어 있어요</p>'
        '<p class="desc">살 물건을 추가해 보세요.</p></div>',
        unsafe_allow_html=True,
    )


def render_item_list(items: list[dict]) -> None:
    """필터(하단에서 선택)를 적용한 목록 (F-02, F-10).

    필터에 맞지 않는 카드도 항상 그리고 CSS로만 숨긴다. 필터를 바꿀 때마다 카드를 새로
    만들면 아이템 100개에서 1초가 넘게 걸리지만, 숨기기만 하면 일반 클릭과 같은 시간에 끝난다.
    """
    choice = st.session_state.get(FILTER) or FILTER_ALL
    if choice == FILTER_TODO:
        hidden = [item["id"] for item in items if item["checked"]]
    elif choice == FILTER_DONE:
        hidden = [item["id"] for item in items if not item["checked"]]
    else:
        hidden = []

    if len(hidden) == len(items):
        st.caption(f"'{choice}' 항목이 없어요.")
    if hidden:
        # id는 storage에서 [A-Za-z0-9_-]만 허용하므로 CSS 선택자에 그대로 넣어도 안전하다.
        selectors = ",".join(
            f'[data-testid="stLayoutWrapper"]:has(> .st-key-item_{item_id})' for item_id in hidden
        )
        st.html(f"<style>{selectors} {{ display: none !important; }}</style>")
    for item in sort_items(items):
        render_item(item)


def render_footer(items: list[dict]) -> None:
    """하단: 보기 필터(F-10)와 체크된 항목 일괄 삭제(F-08, 한 번 확인)."""
    checked_count = sum(1 for item in items if item.get("checked"))
    if checked_count == 0:
        st.session_state[CONFIRM_CLEAR] = False

    if st.session_state[CONFIRM_CLEAR]:
        st.warning(f"체크된 항목 {checked_count}개를 삭제할까요?")
        col_yes, col_no = st.columns(2)
        col_yes.button("삭제", key="clear_yes", on_click=on_confirm_clear, type="primary",
                       use_container_width=True)
        col_no.button("취소", key="clear_no", on_click=on_cancel_clear, use_container_width=True)
        return

    with st.container(key="footer"):
        col_filter, col_clear = st.columns([1, 1], vertical_alignment="center")
        with col_filter:
            st.segmented_control(
                "보기", [FILTER_ALL, FILTER_TODO, FILTER_DONE], key=FILTER,
                label_visibility="collapsed", on_change=on_filter_change,
            )
        col_clear.button(
            f"🧹 체크 항목 삭제 ({checked_count})", key="clear_ask", on_click=on_ask_clear,
            disabled=checked_count == 0,
        )


def main() -> None:
    """화면 전체를 순서대로 그린다."""
    init_state()
    st.html(CSS)
    try:
        items = storage.load_items()
    except storage.StorageError as e:
        st.title("🛒 쇼핑 리스트")
        st.error(str(e), icon="🚫")
        st.button("다시 시도")
        return
    render_header(items)
    render_add_form()
    show_messages()
    if not items:
        render_empty_state()
        return
    render_item_list(items)
    st.divider()
    render_footer(items)


main()

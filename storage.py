"""쇼핑 리스트 데이터 저장 모듈.

data/items.json 파일에 아이템 목록을 저장한다. app.py는 이 모듈의 함수로만
데이터를 다루므로, 나중에 외부 저장소로 바꿀 때 이 파일만 고치면 된다.

Streamlit은 접속한 세션마다 별도 스레드에서 실행되므로, 읽기와
읽고-고치고-쓰기는 모두 프로세스 단위 잠금(_lock) 안에서 처리한다.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "items.json"
MAX_NAME_LENGTH = 50
MIN_QUANTITY = 1
MAX_QUANTITY = 99

_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
_lock = threading.RLock()
_RETRIES = 10           # 다른 프로그램(백신, 편집기 등)이 파일을 잠깐 잡고 있을 때 재시도 횟수
_RETRY_DELAY = 0.05     # 초


class StorageError(Exception):
    """파일을 읽거나 쓸 수 없을 때 발생한다."""


def _retry(action):
    """Windows에서 파일이 잠깐 잠겨 있을 때 생기는 PermissionError를 몇 번 재시도한다."""
    for attempt in range(_RETRIES):
        try:
            return action()
        except PermissionError:
            if attempt == _RETRIES - 1:
                raise
            time.sleep(_RETRY_DELAY)


def _normalize(raw) -> dict | None:
    """저장된 항목 하나를 검증하고 보정한다. 쓸 수 없는 항목이면 None을 반환한다."""
    if not isinstance(raw, dict):
        return None
    item_id, name = raw.get("id"), raw.get("name")
    # id는 화면에서 위젯 key와 CSS 선택자에 쓰이므로 영문·숫자·_·-만 허용한다 (uuid4는 항상 통과).
    if not isinstance(item_id, str) or not _ID_PATTERN.fullmatch(item_id):
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        quantity = int(float(raw.get("quantity", MIN_QUANTITY)))
    except (TypeError, ValueError, OverflowError):
        quantity = MIN_QUANTITY
    quantity = min(MAX_QUANTITY, max(MIN_QUANTITY, quantity))
    created_at = raw.get("created_at")
    return {
        "id": item_id,
        "name": name.strip()[:MAX_NAME_LENGTH],
        "quantity": quantity,
        "checked": bool(raw.get("checked", False)),
        "created_at": created_at if isinstance(created_at, str) else "",
    }


def _read() -> list[dict]:
    """파일에서 아이템 목록을 읽는다.

    파일이 없거나 내용이 깨져 있으면 빈 리스트로 본다. 그 밖의 읽기 오류(권한 등)를
    빈 리스트로 취급하면 다음 저장 때 기존 데이터를 덮어쓰게 되므로 StorageError로 알린다.
    """
    def load():
        with DATA_FILE.open(encoding="utf-8-sig") as f:
            return json.load(f)

    try:
        data = _retry(load)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    except OSError as e:
        raise StorageError("저장된 목록을 읽지 못했어요. 잠시 후 다시 시도해 주세요.") from e
    if not isinstance(data, list):
        return []
    return [item for item in map(_normalize, data) if item is not None]


def _write(items: list[dict]) -> None:
    """임시 파일에 쓴 뒤 교체해서, 쓰는 도중 중단돼도 기존 파일이 깨지지 않게 저장한다."""
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=DATA_FILE.parent, suffix=".tmp")
    except OSError as e:
        raise StorageError("목록을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.") from e
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        _retry(lambda: os.replace(tmp_path, DATA_FILE))
    except OSError as e:
        Path(tmp_path).unlink(missing_ok=True)
        raise StorageError("목록을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.") from e
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _clean_name(name: str) -> str:
    """이름의 앞뒤 공백을 없애고 검증한다. 비어 있거나 너무 길면 ValueError를 낸다."""
    name = (name or "").strip()
    if not name:
        raise ValueError("아이템 이름을 입력해 주세요.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"아이템 이름은 {MAX_NAME_LENGTH}자 이하로 입력해 주세요. (지금 {len(name)}자)")
    return name


def _clean_quantity(quantity) -> int:
    """수량을 정수로 바꾸고 1~99 범위인지 확인한다. 범위 밖이거나 정수가 아니면 ValueError를 낸다."""
    try:
        number = float(quantity)
    except (TypeError, ValueError):
        raise ValueError("수량은 숫자로 입력해 주세요.") from None
    if not number.is_integer() or not MIN_QUANTITY <= number <= MAX_QUANTITY:
        raise ValueError(f"수량은 {MIN_QUANTITY}~{MAX_QUANTITY} 사이의 정수로 입력해 주세요.")
    return int(number)


def load_items() -> list[dict]:
    """저장된 아이템 전체를 추가한 순서대로 반환한다. 파일이 없으면 빈 파일을 만든다."""
    with _lock:
        if not DATA_FILE.exists():
            _write([])
        return sorted(_read(), key=lambda item: item["created_at"])


def add_item(name: str, quantity: int = 1) -> dict:
    """새 아이템을 추가하고, 추가한 아이템을 반환한다."""
    item = {
        "id": str(uuid.uuid4()),
        "name": _clean_name(name),
        "quantity": _clean_quantity(quantity),
        "checked": False,
        "created_at": datetime.now().isoformat(timespec="microseconds"),
    }
    with _lock:
        items = _read()
        items.append(item)
        _write(items)
    return item


def update_item(item_id: str, **fields) -> None:
    """id에 해당하는 아이템의 name, quantity, checked 값을 바꾼다. 없는 id면 KeyError를 낸다."""
    allowed = {"name", "quantity", "checked"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"수정할 수 없는 항목입니다: {', '.join(sorted(unknown))}")
    if "name" in fields:
        fields["name"] = _clean_name(fields["name"])
    if "quantity" in fields:
        fields["quantity"] = _clean_quantity(fields["quantity"])
    if "checked" in fields:
        fields["checked"] = bool(fields["checked"])

    with _lock:
        items = _read()
        for item in items:
            if item["id"] == item_id:
                item.update(fields)
                _write(items)
                return
    raise KeyError(item_id)


def delete_item(item_id: str) -> None:
    """id에 해당하는 아이템을 삭제한다. 이미 없는 id면 아무 일도 하지 않는다."""
    with _lock:
        items = _read()
        remaining = [item for item in items if item["id"] != item_id]
        if len(remaining) != len(items):
            _write(remaining)


def delete_checked() -> int:
    """체크된 아이템을 모두 삭제하고, 삭제한 개수를 반환한다."""
    with _lock:
        items = _read()
        remaining = [item for item in items if not item["checked"]]
        removed = len(items) - len(remaining)
        if removed:
            _write(remaining)
    return removed

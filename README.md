# 🛒 쇼핑 리스트

아이템을 추가, 수정, 삭제, 체크할 수 있는 간단한 Streamlit 웹앱입니다. 요구사항은 [PRD.md](PRD.md)를 참고하세요.

## 설치

Python 3.10 이상이 필요합니다.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 실행

```bash
streamlit run app.py
```

브라우저에서 http://localhost:8501 이 열립니다.

## 데이터

아이템은 `data/items.json`에 저장됩니다. 파일이 없으면 앱을 처음 실행할 때 자동으로 만들어집니다.
이 폴더는 Git에 올리지 않습니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 화면 |
| `storage.py` | 데이터 읽기/쓰기 (JSON 파일) |
| `requirements.txt` | 의존성 |

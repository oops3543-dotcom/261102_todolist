# 261102_todolist

Python Flask + SQLite로 만든 할일 관리 앱입니다.

## 기능

- 할 일 추가 (우선순위, 마감일)
- 완료 표시 / 해제, 수정, 삭제
- 전체 / 진행중 / 완료 필터, 검색
- 진행률 표시, 마감일 지난 항목 강조
- 완료 항목 일괄 삭제

## 실행 방법

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

브라우저에서 http://localhost:5000 접속

"""
체결강도 히스토리 저장/로드
JSON 파일 기반, 종목별 시계열 데이터
"""

import json
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).parent.parent.parent.parent / ".intensity_history.json"
MAX_RECORDS = 120  # 종목당 최대 120건 (2시간, 1분 간격 기준)


def load_history() -> dict[str, list[dict]]:
    """전체 히스토리 로드"""
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_history(history: dict[str, list[dict]]) -> None:
    """전체 히스토리 저장"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
    except Exception:
        pass


def append_intensity(stock_code: str, intensity: float) -> None:
    """체결강도 1건 추가"""
    if not intensity:
        return

    history = load_history()
    if stock_code not in history:
        history[stock_code] = []

    history[stock_code].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "value": round(intensity, 1),
    })

    # 최대 건수 유지
    if len(history[stock_code]) > MAX_RECORDS:
        history[stock_code] = history[stock_code][-MAX_RECORDS:]

    save_history(history)


def get_intensity_history(stock_code: str) -> list[dict]:
    """종목별 히스토리 조회"""
    history = load_history()
    return history.get(stock_code, [])


def clear_history() -> None:
    """히스토리 초기화 (장 시작 시 호출)"""
    save_history({})

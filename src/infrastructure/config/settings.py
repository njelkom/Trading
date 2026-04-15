import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.domain.exceptions import ConfigurationError

load_dotenv()


def _get_env(key: str, default: str = "") -> str:
    """환경변수 조회 (.env 우선, Streamlit Secrets 폴백)"""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
WATCHLIST_FILE = PROJECT_ROOT / "watchlist.txt"


@dataclass(frozen=True)
class KISSettings:
    app_key: str
    app_secret: str
    account_no: str
    base_url: str
    ws_url: str


@dataclass(frozen=True)
class ClaudeSettings:
    api_key: str
    model: str


@dataclass(frozen=True)
class AnalysisSettings:
    interval_seconds: int
    imbalance_threshold_pct: float
    wall_volume_ratio: float


@dataclass(frozen=True)
class AppSettings:
    kis: KISSettings
    claude: ClaudeSettings
    analysis: AnalysisSettings
    watch_stocks: list[str]


def _load_watchlist() -> list[str]:
    """watchlist.txt → .env WATCH_STOCKS → 대화형 입력 순으로 종목 로드"""

    # 1. watchlist.txt 파일
    if WATCHLIST_FILE.exists():
        stocks = []
        for line in WATCHLIST_FILE.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                stocks.append(line)
        if stocks:
            return stocks

    # 2. .env / Secrets WATCH_STOCKS
    env_stocks = _get_env("WATCH_STOCKS", "")
    if env_stocks:
        return [s.strip() for s in env_stocks.split(",") if s.strip()]

    # 3. 대화형 입력
    print("감시할 종목코드를 입력하세요 (쉼표 구분, 예: 005930,000660)")
    user_input = input("> ").strip()
    if not user_input:
        raise ConfigurationError("감시 종목이 설정되지 않았습니다.")
    return [s.strip() for s in user_input.split(",") if s.strip()]


def load_settings() -> AppSettings:
    kis = KISSettings(
        app_key=_get_env("KIS_APP_KEY"),
        app_secret=_get_env("KIS_APP_SECRET"),
        account_no=_get_env("KIS_ACCOUNT_NO"),
        base_url=_get_env(
            "KIS_BASE_URL", "https://openapi.koreainvestment.com:9443"
        ),
        ws_url=_get_env(
            "KIS_WS_URL", "ws://ops.koreainvestment.com:31000"
        ),
    )

    claude = ClaudeSettings(
        api_key=_get_env("ANTHROPIC_API_KEY"),
        model=_get_env("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
    )

    analysis = AnalysisSettings(
        interval_seconds=int(_get_env("ANALYSIS_INTERVAL_SECONDS", "30")),
        imbalance_threshold_pct=float(_get_env("IMBALANCE_THRESHOLD_PCT", "60.0")),
        wall_volume_ratio=float(_get_env("WALL_VOLUME_RATIO", "3.0")),
    )

    watch_stocks = _load_watchlist()

    _validate(kis)

    return AppSettings(
        kis=kis,
        claude=claude,
        analysis=analysis,
        watch_stocks=watch_stocks,
    )


def _validate(kis: KISSettings) -> None:
    missing = []
    if not kis.app_key:
        missing.append("KIS_APP_KEY")
    if not kis.app_secret:
        missing.append("KIS_APP_SECRET")
    if missing:
        raise ConfigurationError(
            f"환경변수 누락: {', '.join(missing)}\n.env 파일을 확인하세요."
        )

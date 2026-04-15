"""
주식 호가창 분석 봇 - Composition Root
모든 의존성을 조립하고 애플리케이션을 부트스트랩한다.
"""

import asyncio

from src.infrastructure.config.settings import load_settings
from src.infrastructure.kis.kis_market_data_adapter import KISMarketDataAdapter
from src.infrastructure.ai.rule_based_analyzer_adapter import RuleBasedAnalyzerAdapter
from src.presentation.terminal.terminal_display import TerminalDisplay
from src.application.use_cases.analyze_orderbook import AnalyzeOrderbookUseCase
from src.application.use_cases.stream_orderbook import StreamOrderbookUseCase


async def main() -> None:
    # 설정 로드
    settings = load_settings()

    # 어댑터 생성 (Infrastructure)
    market_data = KISMarketDataAdapter(settings.kis)
    analyzer = RuleBasedAnalyzerAdapter(
        imbalance_threshold_pct=settings.analysis.imbalance_threshold_pct,
        wall_volume_ratio=settings.analysis.wall_volume_ratio,
    )
    display = TerminalDisplay()

    # 유스케이스 조립 (Application)
    analyze_uc = AnalyzeOrderbookUseCase(analyzer=analyzer, display=display)
    stream_uc = StreamOrderbookUseCase(
        market_data=market_data,
        display=display,
        analyze_use_case=analyze_uc,
        analysis_interval_seconds=settings.analysis.interval_seconds,
    )

    # 부트스트랩
    display.show_banner()

    display.show_step("KIS API 인증 중...")
    await market_data.authenticate()
    display.show_ok("인증 완료")

    stocks = settings.watch_stocks
    display.show_step(f"종목 정보 조회 중... ({len(stocks)}종목)")
    await market_data.fetch_stock_names(stocks)
    names = [
        f"{market_data.get_stock_name(c)}({c})" for c in stocks
    ]
    display.show_ok(f"감시 종목: {', '.join(names)}")

    if len(stocks) > 3:
        display.show_step(
            f"KIS WebSocket 최대 3종목 제한 -> "
            f"{len(stocks)}종목을 배치 교대 수집합니다"
        )

    display.show_step("실시간 호가 수신 시작...")
    display.show_ok("봇 가동 완료! Ctrl+C로 종료")

    try:
        await stream_uc.execute(stocks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    asyncio.run(main())

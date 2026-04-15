import asyncio
import sys
from dataclasses import replace
from datetime import datetime

from src.infrastructure.storage.intensity_history import append_intensity

from src.application.ports.display_port import DisplayPort
from src.application.use_cases.analyze_orderbook import AnalyzeOrderbookUseCase
from src.domain.entities.orderbook import Orderbook
from src.infrastructure.kis.kis_market_data_adapter import KISMarketDataAdapter


class StreamOrderbookUseCase:
    def __init__(
        self,
        market_data: KISMarketDataAdapter,
        display: DisplayPort,
        analyze_use_case: AnalyzeOrderbookUseCase,
        analysis_interval_seconds: int = 30,
    ):
        self._market_data = market_data
        self._display = display
        self._analyze = analyze_use_case
        self._interval = analysis_interval_seconds
        self._running = True

    async def execute(self, stock_codes: list[str]) -> None:
        loop = asyncio.get_event_loop()

        # 종목명 조회
        missing = [c for c in stock_codes if not self._market_data.has_stock_name(c)]
        if missing:
            await self._market_data.fetch_stock_names(missing)

        # 3종목씩 배치 분할
        max_sub = 3
        chunks = [
            stock_codes[i:i + max_sub]
            for i in range(0, len(stock_codes), max_sub)
        ]
        total_chunks = len(chunks)

        try:
            while self._running:
                all_orderbooks: dict[str, Orderbook] = {}

                # WebSocket 연결 (매 갱신마다 새로 연결)
                try:
                    await self._market_data.connect_ws()
                except Exception as e:
                    self._display.show_error(f"WebSocket 연결 실패: {e}")
                    await asyncio.sleep(3)
                    continue

                # 배치별로 구독 → 수집 → 해제
                for idx, chunk in enumerate(chunks):
                    if total_chunks > 1:
                        self._display.show_step(
                            f"호가 수집 중... ({idx + 1}/{total_chunks} 배치: "
                            f"{', '.join(self._market_data.get_stock_name(c) for c in chunk)})"
                        )

                    try:
                        await self._market_data.subscribe_stocks(chunk)
                        collected = await self._market_data.collect_orderbooks(
                            timeout_sec=3.0,
                        )
                        all_orderbooks.update(collected)
                    except Exception as e:
                        self._display.show_error(f"호가 수집 오류: {e}")

                # WebSocket 해제
                await self._market_data.disconnect_ws()

                # 현재가/등락률/체결강도/이동평균 조회 (REST)
                for code in list(all_orderbooks.keys()):
                    try:
                        price_info = await self._market_data.get_current_price(code)
                        await asyncio.sleep(0.5)
                        ma_info = await self._market_data.get_moving_averages(code)
                        all_orderbooks[code] = replace(
                            all_orderbooks[code],
                            current_price=price_info["price"],
                            change_pct=price_info["change_pct"],
                            trading_intensity=price_info["trading_intensity"],
                            volume=price_info["volume"],
                            volume_rate=price_info["volume_rate"],
                            open_price=price_info["open_price"],
                            high_price=price_info["high_price"],
                            low_price=price_info["low_price"],
                            prev_close=price_info["prev_close"],
                            w52_high=price_info["w52_high"],
                            w52_low=price_info["w52_low"],
                            vi_price=price_info["vi_price"],
                            ma5=ma_info["ma5"],
                            ma20=ma_info["ma20"],
                            ma60=ma_info["ma60"],
                        )
                        # 체결강도 히스토리 기록
                        append_intensity(code, price_info["trading_intensity"])
                    except Exception as e:
                        self._display.show_error(
                            f"{self._market_data.get_stock_name(code)} 시세 조회 실패: {e}"
                        )
                    await asyncio.sleep(1.0)

                # 화면 지우고 전체 결과 표시
                self._display.clear_and_banner()

                if not all_orderbooks:
                    self._display.show_error("호가 데이터를 수신하지 못했습니다.")
                else:
                    # 호가창 표시
                    for code in stock_codes:
                        if code in all_orderbooks:
                            self._display.show_orderbook(all_orderbooks[code])

                    # 분석 실행
                    for code in stock_codes:
                        if code in all_orderbooks:
                            try:
                                await self._analyze.execute(all_orderbooks[code])
                            except Exception as e:
                                self._display.show_error(f"분석 오류: {e}")

                # 사용자 입력 대기
                print(
                    f"\n\033[96m엔터를 누르면 갱신합니다 (Ctrl+C 종료)...\033[0m",
                    end="", flush=True,
                )
                await loop.run_in_executor(None, sys.stdin.readline)

        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            try:
                await self._market_data.disconnect_ws()
            except Exception:
                pass

    def stop(self) -> None:
        self._running = False

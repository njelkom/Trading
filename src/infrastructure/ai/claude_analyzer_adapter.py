"""
Claude AI 호가 분석 어댑터
호가창 데이터를 받아 매매 시그널 및 해설 생성
"""

from anthropic import AsyncAnthropic

from src.application.ports.analyzer_port import AnalyzerPort
from src.domain.entities.orderbook import Orderbook
from src.domain.entities.analysis_result import AnalysisResult
from src.domain.value_objects.signal import Signal
from src.domain.exceptions import AnalysisError
from src.infrastructure.config.settings import ClaudeSettings


SYSTEM_PROMPT = """당신은 국내 주식 호가창 전문 분석가입니다.
실시간 호가 데이터를 분석하여 다음 항목을 간결하게 한국어로 답변하세요:

1. **호가 불균형 분석** - 매수/매도 잔량 비율 해석
2. **벽(Wall) 감지** - 특정 가격대에 대량 잔량이 있는지
3. **단기 방향성** - 매수세 우위인지 매도세 우위인지
4. **주목 포인트** - 이상 패턴, 주의사항
5. **시그널** - 🟢 매수 우위 / 🔴 매도 우위 / 🟡 중립 중 하나

각 항목은 2-3문장 이내로 간결하게 작성하세요.
투자 권유는 하지 마세요. 분석 정보만 제공하세요."""


class ClaudeAnalyzerAdapter(AnalyzerPort):
    def __init__(self, settings: ClaudeSettings):
        self._settings = settings
        self._client = AsyncAnthropic(api_key=settings.api_key)

    async def analyze(self, orderbook: Orderbook) -> AnalysisResult:
        prompt = self._build_prompt(orderbook)

        try:
            message = await self._client.messages.create(
                model=self._settings.model,
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            raise AnalysisError(f"Claude API 호출 실패: {e}") from e

        text = message.content[0].text
        signal = self._extract_signal(text)

        return AnalysisResult(
            stock_code=orderbook.stock_code,
            text=text,
            signal=signal,
        )

    def _build_prompt(self, ob: Orderbook) -> str:
        ask_lines = []
        for i, entry in enumerate(ob.ask_entries):
            ask_lines.append(
                f"  매도{i+1}호가: {entry.price:>9,}원  "
                f"잔량: {entry.volume:>6,}주"
            )

        bid_lines = []
        for i, entry in enumerate(ob.bid_entries):
            bid_lines.append(
                f"  매수{i+1}호가: {entry.price:>9,}원  "
                f"잔량: {entry.volume:>6,}주"
            )

        return (
            f"종목코드: {ob.stock_code}\n"
            f"시각: {ob.timestamp.isoformat()}\n"
            f"\n"
            f"【매도 호가】(낮은 순)\n"
            f"{chr(10).join(ask_lines)}\n"
            f"\n"
            f"【매수 호가】(높은 순)\n"
            f"{chr(10).join(bid_lines)}\n"
            f"\n"
            f"【요약】\n"
            f"- 총 매도 잔량: {ob.total_ask_volume:,}주\n"
            f"- 총 매수 잔량: {ob.total_bid_volume:,}주\n"
            f"- 매수 비중: {ob.bid_ratio_pct}%\n"
            f"- 스프레드: {ob.spread:,}원 ({ob.spread_pct:.2f}%)\n"
            f"\n"
            f"위 호가창을 분석해주세요."
        )

    def _extract_signal(self, text: str) -> Signal:
        if "\U0001f7e2" in text or "매수 우위" in text:
            return Signal.BUY
        if "\U0001f534" in text or "매도 우위" in text:
            return Signal.SELL
        return Signal.NEUTRAL

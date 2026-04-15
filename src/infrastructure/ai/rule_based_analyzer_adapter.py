"""
규칙 기반 호가창 분석 어댑터
매수/매도 비율, 벽(Wall) 감지, 스프레드, 체결강도, 집중도를 종합 분석
"""

from src.application.ports.analyzer_port import AnalyzerPort
from src.domain.entities.orderbook import Orderbook, OrderbookEntry
from src.domain.entities.analysis_result import AnalysisResult
from src.domain.value_objects.signal import Signal


class RuleBasedAnalyzerAdapter(AnalyzerPort):
    def __init__(
        self,
        imbalance_threshold_pct: float = 60.0,
        wall_volume_ratio: float = 3.0,
    ):
        self._imbalance_threshold = imbalance_threshold_pct
        self._wall_ratio = wall_volume_ratio

    async def analyze(self, orderbook: Orderbook) -> AnalysisResult:
        lines: list[str] = []
        score = 0

        # 1. 호가 불균형 분석
        imbalance_text, imbalance_score = self._analyze_imbalance(orderbook)
        lines.append(imbalance_text)
        score += imbalance_score

        # 2. 체결강도 분석
        intensity_text, intensity_score = self._analyze_intensity(orderbook)
        lines.append(intensity_text)
        score += intensity_score

        # 3. 벽(Wall) 감지
        wall_text, wall_score = self._detect_walls(orderbook)
        lines.append(wall_text)
        score += wall_score

        # 4. 스프레드 분석
        spread_text = self._analyze_spread(orderbook)
        lines.append(spread_text)

        # 5. 잔량 집중도 분석
        conc_text, conc_score = self._analyze_concentration(orderbook)
        lines.append(conc_text)
        score += conc_score

        # 6. 거래량 분석
        vol_text, vol_score = self._analyze_volume(orderbook)
        if vol_text:
            lines.append(vol_text)
            score += vol_score

        # 7. 이동평균 분석
        ma_text, ma_score = self._analyze_moving_averages(orderbook)
        if ma_text:
            lines.append(ma_text)
            score += ma_score

        # 8. VI 분석
        vi_text = self._analyze_vi(orderbook)
        if vi_text:
            lines.append(vi_text)

        # 종합 판정
        signal = self._score_to_signal(score)
        summary = self._build_summary(orderbook, signal, score)
        lines.append("")
        lines.append(summary)

        text = "\n".join(lines)

        return AnalysisResult(
            stock_code=orderbook.stock_code,
            stock_name=orderbook.stock_name,
            text=text,
            signal=signal,
            current_price=orderbook.current_price,
            change_pct=orderbook.change_pct,
            trading_intensity=orderbook.trading_intensity,
            volume=orderbook.volume,
            volume_rate=orderbook.volume_rate,
            open_price=orderbook.open_price,
            high_price=orderbook.high_price,
            low_price=orderbook.low_price,
            prev_close=orderbook.prev_close,
            w52_high=orderbook.w52_high,
            w52_low=orderbook.w52_low,
            vi_price=orderbook.vi_price,
            ma5=orderbook.ma5,
            ma20=orderbook.ma20,
            ma60=orderbook.ma60,
        )

    # ── 1. 호가 불균형 ───────────────────────────────

    def _analyze_imbalance(self, ob: Orderbook) -> tuple[str, int]:
        ratio = ob.bid_ratio_pct
        total_ask = ob.total_ask_volume
        total_bid = ob.total_bid_volume
        diff = abs(total_bid - total_ask)
        score = 0

        if ratio >= 70:
            desc = "매수 잔량이 매도 대비 압도적으로 많습니다. 강한 매수세가 형성되어 있습니다."
            score = 2
        elif ratio >= 60:
            desc = "매수 잔량이 매도보다 우세합니다. 매수 심리가 살아있는 상황입니다."
            score = 1
        elif ratio <= 30:
            desc = "매도 잔량이 매수 대비 압도적으로 많습니다. 강한 매도 압력이 존재합니다."
            score = -2
        elif ratio <= 40:
            desc = "매도 잔량이 매수보다 우세합니다. 매도 심리가 우세한 상황입니다."
            score = -1
        else:
            desc = "매수와 매도 잔량이 비슷합니다. 관망 분위기로 방향성을 지켜볼 필요가 있습니다."

        text = (
            f"[수급 분석] {desc}\n"
            f"  - 매수 잔량: {total_bid:,}주 ({ratio}%) / "
            f"매도 잔량: {total_ask:,}주 ({round(100 - ratio, 1)}%) / "
            f"차이: {diff:,}주"
        )
        return text, score

    # ── 2. 체결강도 ──────────────────────────────────

    def _analyze_intensity(self, ob: Orderbook) -> tuple[str, int]:
        ti = ob.trading_intensity
        score = 0

        if ti == 0:
            return "[체결강도] 데이터 없음", 0

        if ti >= 150:
            desc = "체결강도가 매우 높습니다. 매수 체결이 매도 대비 크게 앞서고 있어 강한 상승 동력이 있습니다."
            score = 2
        elif ti >= 120:
            desc = "체결강도가 높은 편입니다. 실제 매수 체결이 활발하게 이루어지고 있습니다."
            score = 1
        elif ti >= 100:
            desc = "체결강도가 균형 수준입니다. 매수/매도 체결이 비슷하게 이루어지고 있습니다."
        elif ti >= 80:
            desc = "체결강도가 다소 약합니다. 매도 체결이 매수보다 앞서고 있습니다."
            score = -1
        else:
            desc = "체결강도가 매우 낮습니다. 매도 체결이 크게 앞서고 있어 하락 압력이 존재합니다."
            score = -2

        text = f"[체결강도] {ti:.1f}% - {desc}"
        return text, score

    # ── 3. 벽(Wall) 감지 ─────────────────────────────

    def _detect_walls(self, ob: Orderbook) -> tuple[str, int]:
        ask_walls = self._find_walls(ob.ask_entries, ob.total_ask_volume)
        bid_walls = self._find_walls(ob.bid_entries, ob.total_bid_volume)
        score = 0

        if not ask_walls and not bid_walls:
            return "[매물벽] 특이 대량 잔량이 감지되지 않았습니다. 가격이 자유롭게 움직일 수 있는 구간입니다.", 0

        parts = ["[매물벽]"]

        if ask_walls:
            score -= len(ask_walls)
            for price, volume, ratio in ask_walls:
                parts.append(
                    f"\n  - 매도벽: {price:,}원에 {volume:,}주 대기 중 "
                    f"(평균의 {ratio:.1f}배) → 이 가격대에서 상승 저항이 예상됩니다"
                )

        if bid_walls:
            score += len(bid_walls)
            for price, volume, ratio in bid_walls:
                parts.append(
                    f"\n  - 매수벽: {price:,}원에 {volume:,}주 대기 중 "
                    f"(평균의 {ratio:.1f}배) → 이 가격대에서 하방 지지가 예상됩니다"
                )

        text = "".join(parts)
        return text, score

    def _find_walls(
        self,
        entries: list[OrderbookEntry],
        total_volume: int,
    ) -> list[tuple[int, int, float]]:
        if not entries or total_volume == 0:
            return []

        avg_volume = total_volume / len(entries)
        walls = []

        for entry in entries:
            if avg_volume > 0 and entry.volume >= avg_volume * self._wall_ratio:
                ratio = entry.volume / avg_volume
                walls.append((entry.price, entry.volume, ratio))

        return walls

    # ── 4. 스프레드 ──────────────────────────────────

    def _analyze_spread(self, ob: Orderbook) -> str:
        if not ob.ask_entries or not ob.bid_entries:
            return "[스프레드] 데이터 부족"

        spread = ob.spread
        spread_pct = ob.spread_pct
        best_ask = ob.ask_entries[0].price
        best_bid = ob.bid_entries[0].price

        if spread_pct <= 0.05:
            desc = "스프레드가 매우 타이트합니다. 유동성이 풍부하여 원하는 가격에 체결이 용이합니다."
        elif spread_pct <= 0.15:
            desc = "스프레드가 정상 범위입니다. 일반적인 거래 환경입니다."
        elif spread_pct <= 0.3:
            desc = "스프레드가 다소 넓습니다. 급하게 매매하면 불리한 가격에 체결될 수 있어 주의가 필요합니다."
        else:
            desc = "스프레드가 매우 넓습니다. 유동성이 부족하여 시장가 주문 시 슬리피지가 발생할 수 있습니다."

        return (
            f"[스프레드] {spread:,}원 ({spread_pct:.2f}%) - {desc}\n"
            f"  - 최우선 매도호가: {best_ask:,}원 / 최우선 매수호가: {best_bid:,}원"
        )

    # ── 5. 잔량 집중도 ───────────────────────────────

    def _analyze_concentration(self, ob: Orderbook) -> tuple[str, int]:
        score = 0
        parts = ["[잔량 집중도]"]

        ask_top_pct = 0.0
        bid_top_pct = 0.0

        if ob.ask_entries and ob.total_ask_volume > 0:
            ask_top_pct = ob.ask_entries[0].volume / ob.total_ask_volume * 100

        if ob.bid_entries and ob.total_bid_volume > 0:
            bid_top_pct = ob.bid_entries[0].volume / ob.total_bid_volume * 100

        if ask_top_pct == 0 and bid_top_pct == 0:
            return "[잔량 집중도] 데이터 부족", 0

        if bid_top_pct >= 50:
            parts.append(
                f"\n  - 매수 1호가에 전체의 {bid_top_pct:.1f}%가 집중 "
                f"→ 현재 가격 부근에서 강한 매수 의지가 보입니다"
            )
            score += 1
        elif bid_top_pct >= 30:
            parts.append(f"\n  - 매수 1호가 집중도 {bid_top_pct:.1f}% (보통)")
        else:
            parts.append(f"\n  - 매수 1호가 집중도 {bid_top_pct:.1f}% (분산)")

        if ask_top_pct >= 50:
            parts.append(
                f"\n  - 매도 1호가에 전체의 {ask_top_pct:.1f}%가 집중 "
                f"→ 직상방에 강한 매도 압력이 존재합니다"
            )
            score -= 1
        elif ask_top_pct >= 30:
            parts.append(f"\n  - 매도 1호가 집중도 {ask_top_pct:.1f}% (보통)")
        else:
            parts.append(f"\n  - 매도 1호가 집중도 {ask_top_pct:.1f}% (분산)")

        return "".join(parts), score

    # ── 6. 거래량 ────────────────────────────────────

    def _analyze_volume(self, ob: Orderbook) -> tuple[str, int]:
        if not ob.volume:
            return "", 0

        score = 0
        rate = ob.volume_rate

        if rate >= 200:
            desc = f"거래량이 전일 대비 {rate:.0f}%로 폭발적으로 증가했습니다. 시장의 강한 관심이 집중되고 있습니다."
            score = 1
        elif rate >= 120:
            desc = f"거래량이 전일 대비 {rate:.0f}%로 활발합니다. 적극적인 거래가 이루어지고 있습니다."
        elif rate >= 50:
            desc = f"거래량이 전일 대비 {rate:.0f}%로 보통 수준입니다."
        elif rate > 0:
            desc = f"거래량이 전일 대비 {rate:.0f}%로 저조합니다. 시장 관심이 낮은 상태입니다."
            score = -1
        else:
            desc = f"누적 거래량 {ob.volume:,}주"

        return f"[거래량] {ob.volume:,}주 - {desc}", score

    # ── 7. 이동평균 ──────────────────────────────────

    def _analyze_moving_averages(self, ob: Orderbook) -> tuple[str, int]:
        if not ob.ma5 or not ob.current_price:
            return "", 0

        score = 0
        parts = ["[이동평균]"]

        # 정배열/역배열
        if ob.ma20:
            if ob.current_price > ob.ma5 > ob.ma20:
                parts.append(
                    "\n  - 정배열 (현재가 > 5일선 > 20일선): 상승 추세가 유지되고 있습니다"
                )
                score = 1
            elif ob.current_price < ob.ma5 < ob.ma20:
                parts.append(
                    "\n  - 역배열 (현재가 < 5일선 < 20일선): 하락 추세가 진행 중입니다"
                )
                score = -1
            else:
                parts.append("\n  - 이평선 혼조: 추세 전환 구간으로 방향성을 지켜봐야 합니다")

        # 5일선 괴리율
        gap5 = round((ob.current_price - ob.ma5) / ob.ma5 * 100, 2)
        if abs(gap5) >= 5:
            parts.append(
                f"\n  - 5일선 괴리율 {gap5:+.2f}%: 단기 과열/과매도 구간으로 되돌림 가능성 있음"
            )

        return "".join(parts), score

    # ── 8. VI 발동가 ─────────────────────────────────

    def _analyze_vi(self, ob: Orderbook) -> str:
        if not ob.vi_price or not ob.current_price:
            return ""

        vi_dist = round((ob.vi_price - ob.current_price) / ob.current_price * 100, 2)

        if abs(vi_dist) <= 3:
            return (
                f"[VI 경고] 정적 VI 발동가({ob.vi_price:,}원)까지 {vi_dist:+.2f}% 남았습니다. "
                f"급격한 가격 변동 시 VI가 발동될 수 있으니 주의하세요."
            )
        return ""

    # ── 종합 판정 ────────────────────────────────────

    def _score_to_signal(self, score: int) -> Signal:
        if score >= 3:
            return Signal.BUY
        elif score <= -3:
            return Signal.SELL
        return Signal.NEUTRAL

    def _build_summary(self, ob: Orderbook, signal: Signal, score: int) -> str:
        name = ob.stock_name or ob.stock_code

        if signal == Signal.BUY:
            if score >= 5:
                outlook = (
                    f"{name}은(는) 매수세가 매우 강한 상황입니다. "
                    f"호가 잔량, 체결강도, 매물벽 등 복수 지표가 상승을 가리키고 있습니다. "
                    f"단기 상승 가능성이 높아 보이나, 급등 후 차익실현 물량에 유의하세요."
                )
            else:
                outlook = (
                    f"{name}은(는) 매수 우위 상황입니다. "
                    f"매수 잔량과 체결이 앞서고 있어 단기적으로 긍정적인 흐름이 예상됩니다. "
                    f"다만 매도벽이나 외부 변수에 의해 반전될 수 있으니 추이를 지켜보세요."
                )
        elif signal == Signal.SELL:
            if score <= -5:
                outlook = (
                    f"{name}은(는) 매도 압력이 매우 강한 상황입니다. "
                    f"호가 잔량, 체결강도, 매물벽 등 복수 지표가 하락을 가리키고 있습니다. "
                    f"단기 하락 가능성이 높아 보이며, 신규 매수는 신중하게 접근하세요."
                )
            else:
                outlook = (
                    f"{name}은(는) 매도 우위 상황입니다. "
                    f"매도 잔량과 체결이 앞서고 있어 단기적으로 약세 흐름이 예상됩니다. "
                    f"지지선 확인 후 대응하는 것이 안전합니다."
                )
        else:
            outlook = (
                f"{name}은(는) 매수/매도 세력이 팽팽한 상황입니다. "
                f"뚜렷한 방향성이 없으므로 추가 신호가 나올 때까지 관망하는 것이 좋겠습니다. "
                f"거래량 변화나 호가 잔량 변동을 주시하세요."
            )

        return f"[종합 의견] {outlook}"

"""
터미널 출력 어댑터 - ANSI 컬러 포맷팅 (Windows/Mac 호환)
"""

import os
import sys
from datetime import datetime

from src.application.ports.display_port import DisplayPort
from src.domain.entities.orderbook import Orderbook
from src.domain.entities.analysis_result import AnalysisResult
from src.infrastructure.storage.intensity_history import get_intensity_history


def _enable_ansi_windows() -> None:
    """Windows 터미널에서 ANSI 색상 활성화"""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(
                kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass


_enable_ansi_windows()


class _Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    WHITE = "\033[97m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    DIM = "\033[2m"


C = _Colors


class TerminalDisplay(DisplayPort):
    def show_banner(self) -> None:
        print(
            f"\n{C.CYAN}{C.BOLD}"
            f"{'=' * 46}\n"
            f"  주식 호가창 분석 봇 v2.0\n"
            f"  실시간 호가창 분석\n"
            f"{'=' * 46}"
            f"{C.RESET}\n"
        )

    def show_step(self, msg: str) -> None:
        print(f"{C.BLUE}> {msg}{C.RESET}")

    def show_ok(self, msg: str) -> None:
        print(f"{C.GREEN}[OK] {msg}{C.RESET}")

    def show_error(self, msg: str) -> None:
        print(f"{C.RED}[ERROR] {msg}{C.RESET}")

    def clear_and_banner(self) -> None:
        self._clear_screen()
        print(
            f"{C.CYAN}{C.BOLD}"
            f"  주식 호가창 분석 봇 v2.0 | Ctrl+C로 종료"
            f"{C.RESET}"
        )

    def show_orderbook(self, orderbook: Orderbook) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        bid_ratio = orderbook.bid_ratio_pct

        if bid_ratio >= 60:
            ratio_color = C.GREEN
        elif bid_ratio <= 40:
            ratio_color = C.RED
        else:
            ratio_color = C.YELLOW

        # 등락률 색상
        pct = orderbook.change_pct
        if pct > 0:
            pct_color = C.RED
            pct_str = f"+{pct:.2f}%"
        elif pct < 0:
            pct_color = C.BLUE
            pct_str = f"{pct:.2f}%"
        else:
            pct_color = C.DIM
            pct_str = "0.00%"

        price_str = ""
        if orderbook.current_price:
            price_str = f"  {orderbook.current_price:,}원 ({pct_color}{pct_str}{C.RESET})"

        # 체결강도 색상
        ti = orderbook.trading_intensity
        if ti >= 120:
            ti_color = C.RED
        elif ti <= 80:
            ti_color = C.BLUE
        else:
            ti_color = C.YELLOW
        ti_str = f"  체결강도: {ti_color}{ti:.1f}%{C.RESET}" if ti else ""

        ob = orderbook
        print(f"\n{C.DIM}{'=' * 65}{C.RESET}")
        print(
            f"{C.BOLD}[{ts}] {ob.stock_name} ({ob.stock_code})"
            f"{C.RESET}{price_str}{ti_str}  "
            f"매수비중: {ratio_color}{bid_ratio}%{C.RESET}"
        )

        # 시세 요약 (거래량, 고저가, 52주, VI)
        details = []
        if ob.volume:
            vol_str = f"거래량: {ob.volume:,}"
            if ob.volume_rate:
                vol_str += f" (전일비 {ob.volume_rate:.1f}%)"
            details.append(vol_str)
        if ob.high_price:
            details.append(
                f"시:{ob.open_price:,} 고:{ob.high_price:,} 저:{ob.low_price:,}"
            )
        if ob.w52_high and ob.w52_high > ob.w52_low:
            w52_pos = round((ob.current_price - ob.w52_low) / (ob.w52_high - ob.w52_low) * 100)
            details.append(f"52주: {ob.w52_low:,}~{ob.w52_high:,} (위치 {w52_pos}%)")
        if ob.vi_price and ob.current_price:
            vi_dist = round((ob.vi_price - ob.current_price) / ob.current_price * 100, 2)
            details.append(f"VI: {ob.vi_price:,}원 ({vi_dist:+.2f}%)")

        if details:
            print(f"  {C.DIM}{' | '.join(details)}{C.RESET}")
            details = []

        # 이동평균
        if ob.ma5:
            ma_parts = []
            for label, val in [("MA5", ob.ma5), ("MA20", ob.ma20), ("MA60", ob.ma60)]:
                if val and ob.current_price:
                    gap = round((ob.current_price - val) / val * 100, 2)
                    ma_parts.append(f"{label}: {val:,} ({gap:+.2f}%)")
            if ma_parts:
                details.append(" | ".join(ma_parts))

        if details:
            print(f"  {C.DIM}{' | '.join(details)}{C.RESET}")

        # 잔량 비율 바
        total = ob.total_ask_volume + ob.total_bid_volume
        if total > 0:
            bar_width = 40
            bid_len = int(ob.total_bid_volume / total * bar_width)
            ask_len = bar_width - bid_len
            print(
                f"  {C.RED}{'█' * ask_len}{C.RESET}"
                f"{C.GREEN}{'█' * bid_len}{C.RESET}"
                f"  매도 {ob.total_ask_volume:,} vs 매수 {ob.total_bid_volume:,}"
            )

        print(f"  {C.DIM}{'-' * 50}{C.RESET}")

        # 호가 10단계
        total_ask = ob.total_ask_volume
        for entry in reversed(ob.ask_entries):
            bar = self._bar(entry.volume, total_ask, 15)
            print(
                f"  {C.RED}{entry.price:>10,}원  "
                f"{entry.volume:>8,}주  {bar}{C.RESET}"
            )

        print(f"  {C.DIM}{'.' * 50}{C.RESET}")

        total_bid = ob.total_bid_volume
        for entry in ob.bid_entries:
            bar = self._bar(entry.volume, total_bid, 15)
            print(
                f"  {C.GREEN}{entry.price:>10,}원  "
                f"{entry.volume:>8,}주  {bar}{C.RESET}"
            )

        # 체결강도 추이 (최근 10건)
        history = get_intensity_history(ob.stock_code)
        if len(history) >= 2:
            recent = history[-10:]
            vals = [r["value"] for r in recent]
            avg = sum(vals) / len(vals)
            sparkline = ""
            for v in vals:
                if v >= 120:
                    sparkline += f"{C.RED}▲{C.RESET}"
                elif v >= 100:
                    sparkline += f"{C.YELLOW}■{C.RESET}"
                else:
                    sparkline += f"{C.BLUE}▼{C.RESET}"
            print(
                f"  {C.DIM}체결강도 추이:{C.RESET} {sparkline} "
                f"{C.DIM}(최근{len(recent)}건 평균 {avg:.1f}%){C.RESET}"
            )

    def show_analyzing(self, stock_code: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(
            f"\n{C.YELLOW}[{ts}] {stock_code} 분석 중...{C.RESET}"
        )

    def show_analysis(self, result: AnalysisResult) -> None:
        # 등락률
        pct = result.change_pct
        if pct > 0:
            pct_color = C.RED
            pct_str = f"+{pct:.2f}%"
        elif pct < 0:
            pct_color = C.BLUE
            pct_str = f"{pct:.2f}%"
        else:
            pct_color = C.DIM
            pct_str = "0.00%"

        # 체결강도
        ti = result.trading_intensity
        if ti >= 120:
            ti_color = C.RED
        elif ti <= 80:
            ti_color = C.BLUE
        else:
            ti_color = C.YELLOW

        # 시그널 색상
        signal_color = C.GREEN if result.signal.label == "매수 우위" else (
            C.RED if result.signal.label == "매도 우위" else C.YELLOW
        )

        # 헤더
        print(
            f"\n{C.WHITE}{C.BOLD}"
            f"+-- 분석: {result.stock_name} ({result.stock_code}) "
            f"[{signal_color}{result.signal.emoji} {result.signal.label}{C.RESET}{C.WHITE}{C.BOLD}]"
            f"{C.RESET}"
        )

        # 시세 요약
        price_str = f"{result.current_price:,}원" if result.current_price else "-"
        print(
            f"{C.WHITE}| 현재가: {price_str} "
            f"전일대비: {pct_color}{pct_str}{C.RESET}{C.WHITE} "
            f"체결강도: {ti_color}{ti:.1f}%{C.RESET}"
        )

        # 분석 내용
        for line in result.text.strip().splitlines():
            print(f"{C.WHITE}| {line}{C.RESET}")
        print(f"{C.WHITE}+{'-' * 50}{C.RESET}")

    def _clear_screen(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")

    def _bar(self, volume: int, total: int, width: int) -> str:
        if total == 0:
            return ""
        filled = int(volume / total * width)
        return "#" * filled + "." * (width - filled)

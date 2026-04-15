"""
주식 호가창 분석 봇 - Streamlit 웹 UI
"""

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd

from src.infrastructure.config.settings import load_settings, WATCHLIST_FILE
from src.infrastructure.storage.intensity_history import append_intensity, get_intensity_history
from src.infrastructure.storage.portfolio import load_portfolio, save_holding, StockHolding
from src.infrastructure.kis.kis_market_data_adapter import KISMarketDataAdapter
from src.infrastructure.ai.rule_based_analyzer_adapter import RuleBasedAnalyzerAdapter
from src.domain.entities.orderbook import Orderbook
from src.domain.entities.analysis_result import AnalysisResult


# ── 페이지 설정 ─────────────────────────────────

st.set_page_config(
    page_title="호가창 분석 봇",
    page_icon="📈",
    layout="wide",
)

# ── 스타일 ───────────────────────────────────────

st.markdown("""
<style>
    .block-container { max-width: 1100px; }

    /* 모바일 반응형 */
    @media (max-width: 768px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        .ask-cell, .bid-cell { font-size: 0.75em !important; }
        .bar-ask, .bar-bid { display: none; }
        [data-testid="stMetric"] { padding: 4px 0; }
        [data-testid="stMetricLabel"] { font-size: 0.7em; }
        [data-testid="stMetricValue"] { font-size: 0.9em; }
        .summary-box { font-size: 0.85em; padding: 10px 12px; }
        .analysis-title { font-size: 0.9em; }
        .analysis-detail { font-size: 0.8em; }
    }

    .signal-buy {
        background: linear-gradient(135deg, #0d4d1a, #1a6b2a);
        color: #ffffff; padding: 12px 20px; border-radius: 10px;
        font-size: 1.1em; font-weight: bold; margin: 8px 0;
    }
    .signal-sell {
        background: linear-gradient(135deg, #4d0d0d, #6b1a1a);
        color: #ffffff; padding: 12px 20px; border-radius: 10px;
        font-size: 1.1em; font-weight: bold; margin: 8px 0;
    }
    .signal-neutral {
        background: linear-gradient(135deg, #4d4d0d, #6b6b1a);
        color: #ffffff; padding: 12px 20px; border-radius: 10px;
        font-size: 1.1em; font-weight: bold; margin: 8px 0;
    }

    .summary-box {
        background: rgba(50, 120, 220, 0.1);
        border-left: 4px solid #3278dc;
        padding: 14px 18px; border-radius: 6px; margin: 12px 0;
        font-size: 1.0em; line-height: 1.7;
        color: inherit;
    }

    .analysis-section {
        padding: 6px 0;
        font-size: 0.95em; line-height: 1.6;
        color: inherit;
    }
    .analysis-title {
        font-weight: bold; font-size: 1.0em;
        margin-top: 10px;
        color: inherit;
    }
    .analysis-detail {
        margin-left: 12px; color: inherit; opacity: 0.85;
    }

    .ask-cell { color: #e54545; font-family: monospace; font-size: 0.9em; }
    .bid-cell { color: #22a855; font-family: monospace; font-size: 0.9em; }
    .bar-ask { color: #e54545; letter-spacing: -2px; }
    .bar-bid { color: #22a855; letter-spacing: -2px; }
</style>
""", unsafe_allow_html=True)


# ── 비동기 헬퍼 ─────────────────────────────────

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ── 데이터 로드 ─────────────────────────────────

@st.cache_resource
def init_market_data():
    """KIS API 어댑터 초기화 (인증, 캐시)"""
    settings = load_settings()
    adapter = KISMarketDataAdapter(settings.kis)
    run_async(adapter.authenticate())
    return adapter, settings


async def fetch_all_data(
    market_data: KISMarketDataAdapter,
    analyzer: RuleBasedAnalyzerAdapter,
    stock_codes: list[str],
) -> list[tuple[Orderbook, AnalysisResult]]:
    """전체 종목 호가 + 분석 데이터 수집"""

    # 종목명은 매번 확인
    missing = [c for c in stock_codes if not market_data.has_stock_name(c)]
    if missing:
        await market_data.fetch_stock_names(missing)

    # WebSocket 배치 수집
    await market_data.connect_ws()
    all_orderbooks: dict[str, Orderbook] = {}
    max_sub = 3
    chunks = [stock_codes[i:i + max_sub] for i in range(0, len(stock_codes), max_sub)]

    for chunk in chunks:
        try:
            await market_data.subscribe_stocks(chunk)
            collected = await market_data.collect_orderbooks(timeout_sec=3.0)
            all_orderbooks.update(collected)
        except Exception:
            pass

    await market_data.disconnect_ws()

    # 현재가/체결강도/이동평균 REST 조회
    for code in list(all_orderbooks.keys()):
        try:
            price_info = await market_data.get_current_price(code)
            await asyncio.sleep(0.5)
            ma_info = await market_data.get_moving_averages(code)
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
        except Exception:
            pass
        await asyncio.sleep(1.0)

    # 분석
    results = []
    for code in stock_codes:
        if code in all_orderbooks:
            ob = all_orderbooks[code]
            analysis = await analyzer.analyze(ob)
            results.append((ob, analysis))

    return results


async def fetch_single_stock(
    market_data: KISMarketDataAdapter,
    analyzer: RuleBasedAnalyzerAdapter,
    stock_code: str,
) -> tuple[Orderbook, AnalysisResult] | None:
    """단일 종목 호가 + 분석 데이터 수집"""

    if not market_data.has_stock_name(stock_code):
        await market_data.fetch_stock_names([stock_code])

    # WebSocket 수집
    await market_data.connect_ws()
    try:
        await market_data.subscribe_stocks([stock_code])
        collected = await market_data.collect_orderbooks(timeout_sec=3.0)
    except Exception:
        collected = {}
    await market_data.disconnect_ws()

    if stock_code not in collected:
        return None

    ob = collected[stock_code]

    # 현재가/체결강도/이동평균
    try:
        price_info = await market_data.get_current_price(stock_code)
        await asyncio.sleep(0.5)
        ma_info = await market_data.get_moving_averages(stock_code)
        ob = replace(
            ob,
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
        append_intensity(stock_code, price_info["trading_intensity"])
    except Exception:
        pass

    analysis = await analyzer.analyze(ob)
    return ob, analysis


# ── UI 컴포넌트 ─────────────────────────────────

def render_orderbook(ob: Orderbook, holding: StockHolding | None = None):
    """호가창 렌더링"""

    pct = ob.change_pct
    pct_str = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"
    ti = ob.trading_intensity

    # 시세 카드 (2열씩 배치 → 모바일 친화)
    c1, c2 = st.columns(2)
    c1.metric("현재가", f"{ob.current_price:,}원" if ob.current_price else "-")
    c2.metric("전일대비", pct_str, delta=f"{pct:.2f}%")

    c3, c4 = st.columns(2)
    c3.metric("체결강도", f"{ti:.1f}%" if ti else "-")
    c4.metric("매수비중", f"{ob.bid_ratio_pct}%")

    c5, c6 = st.columns(2)
    if ob.volume:
        vol_str = f"{ob.volume:,}"
        rate_str = f"전일비 {ob.volume_rate:.1f}%" if ob.volume_rate else ""
        c5.metric("거래량", vol_str, delta=rate_str if ob.volume_rate else None)
    else:
        c5.metric("거래량", "-")

    if ob.high_price:
        c6.metric("시/고/저", f"{ob.open_price:,} / {ob.high_price:,} / {ob.low_price:,}")
    else:
        c6.metric("시/고/저", "-")

    c7, c8 = st.columns(2)
    if ob.w52_high:
        w52_pos = 0
        if ob.w52_high > ob.w52_low:
            w52_pos = round((ob.current_price - ob.w52_low) / (ob.w52_high - ob.w52_low) * 100)
        c7.metric("52주 고/저", f"{ob.w52_high:,} / {ob.w52_low:,}", delta=f"현위치 {w52_pos}%")
    else:
        c7.metric("52주 고/저", "-")

    if ob.vi_price:
        vi_dist = round((ob.vi_price - ob.current_price) / ob.current_price * 100, 2) if ob.current_price else 0
        c8.metric("VI 발동가", f"{ob.vi_price:,}원", delta=f"{vi_dist:+.2f}%")
    else:
        c8.metric("VI 발동가", "-")

    # 이동평균
    if ob.ma5:
        def _ma_delta(ma_val):
            if ma_val and ob.current_price:
                gap = round((ob.current_price - ma_val) / ma_val * 100, 2)
                return f"괴리 {gap:+.2f}%"
            return None

        c9, c10 = st.columns(2)
        c9.metric("5일 이평", f"{ob.ma5:,}원", delta=_ma_delta(ob.ma5))
        c10.metric("20일 이평", f"{ob.ma20:,}원" if ob.ma20 else "-", delta=_ma_delta(ob.ma20))

        c11, c12 = st.columns(2)
        c11.metric("60일 이평", f"{ob.ma60:,}원" if ob.ma60 else "-", delta=_ma_delta(ob.ma60))
        if ob.ma5 and ob.ma20:
            if ob.current_price > ob.ma5 > ob.ma20:
                c12.metric("이평 배열", "정배열", delta="상승 추세")
            elif ob.current_price < ob.ma5 < ob.ma20:
                c12.metric("이평 배열", "역배열", delta="하락 추세")
            else:
                c12.metric("이평 배열", "혼조", delta="방향 탐색 중")

    # 체결강도 추이 차트
    history = get_intensity_history(ob.stock_code)
    if len(history) >= 2:
        import pandas as pd
        df = pd.DataFrame(history)
        df = df.rename(columns={"time": "시각", "value": "체결강도(%)"})
        df = df.set_index("시각")

        # 100% 기준선과 함께 표시
        st.markdown("##### 체결강도 추이")
        st.line_chart(df, height=150, use_container_width=True)
        st.caption(
            f"최근 {len(history)}건 | "
            f"최고 {max(r['value'] for r in history):.1f}% | "
            f"최저 {min(r['value'] for r in history):.1f}% | "
            f"평균 {sum(r['value'] for r in history) / len(history):.1f}%"
        )

    # 매도/매수 총잔량 비율 바
    total = ob.total_ask_volume + ob.total_bid_volume
    if total > 0:
        bid_pct = ob.total_bid_volume / total
        st.markdown(
            f'<div style="display:flex;height:24px;border-radius:4px;overflow:hidden;margin:8px 0;">'
            f'<div style="width:{(1-bid_pct)*100:.1f}%;background:#e54545;display:flex;align-items:center;justify-content:center;font-size:0.8em;color:white;font-weight:bold;">'
            f'매도 {ob.total_ask_volume:,}</div>'
            f'<div style="width:{bid_pct*100:.1f}%;background:#22a855;display:flex;align-items:center;justify-content:center;font-size:0.8em;color:white;font-weight:bold;">'
            f'매수 {ob.total_bid_volume:,}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # 호가창 테이블 (10단계)
    st.caption(f"스프레드: {ob.spread:,}원 ({ob.spread_pct:.2f}%)" if ob.spread else "")
    ask_col, bid_col = st.columns(2)

    # 목표가/손절가 가격
    target_p = holding.target_price if holding else 0
    stop_p = holding.stop_loss_price if holding else 0

    with ask_col:
        st.markdown("##### 매도 호가 🔴")
        rows = []
        for entry in reversed(ob.ask_entries):
            pct_vol = entry.volume / ob.total_ask_volume * 100 if ob.total_ask_volume else 0
            bar_len = max(1, int(pct_vol / 3))
            tag = ""
            style = ""
            if target_p and entry.price == target_p:
                tag = " 🎯"
                style = "background:rgba(0,200,100,0.2);border-radius:4px;padding:2px 4px;"
            elif stop_p and entry.price == stop_p:
                tag = " 🛑"
                style = "background:rgba(255,0,0,0.2);border-radius:4px;padding:2px 4px;"
            rows.append(
                f'<div class="ask-cell" style="{style}">'
                f'{entry.price:>12,}원 &nbsp; {entry.volume:>10,}주 &nbsp; '
                f'<span class="bar-ask">{"█" * bar_len}</span>{tag}'
                f'</div>'
            )
        st.markdown("\n".join(rows), unsafe_allow_html=True)

    with bid_col:
        st.markdown("##### 매수 호가 🟢")
        rows = []
        for entry in ob.bid_entries:
            pct_vol = entry.volume / ob.total_bid_volume * 100 if ob.total_bid_volume else 0
            bar_len = max(1, int(pct_vol / 3))
            tag = ""
            style = ""
            if target_p and entry.price == target_p:
                tag = " 🎯"
                style = "background:rgba(0,200,100,0.2);border-radius:4px;padding:2px 4px;"
            elif stop_p and entry.price == stop_p:
                tag = " 🛑"
                style = "background:rgba(255,0,0,0.2);border-radius:4px;padding:2px 4px;"
            rows.append(
                f'<div class="bid-cell" style="{style}">'
                f'{entry.price:>12,}원 &nbsp; {entry.volume:>10,}주 &nbsp; '
                f'<span class="bar-bid">{"█" * bar_len}</span>{tag}'
                f'</div>'
            )
        st.markdown("\n".join(rows), unsafe_allow_html=True)


def render_analysis(result: AnalysisResult):
    """분석 결과 렌더링"""
    signal = result.signal

    # 시그널 배지
    if signal.label == "매수 우위":
        css = "signal-buy"
    elif signal.label == "매도 우위":
        css = "signal-sell"
    else:
        css = "signal-neutral"

    st.markdown(
        f'<div class="{css}">{signal.emoji} {signal.label}</div>',
        unsafe_allow_html=True,
    )

    # 분석 본문
    lines = result.text.strip().splitlines()
    html_parts = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        elif stripped.startswith("[종합 의견]"):
            content = stripped.replace("[종합 의견] ", "")
            html_parts.append(
                f'<div class="summary-box"><b>💡 종합 의견</b><br>{content}</div>'
            )
        elif stripped.startswith("["):
            bracket_end = stripped.find("]")
            if bracket_end > 0:
                title = stripped[1:bracket_end]
                rest = stripped[bracket_end + 1:].strip()
                # 제목과 요약을 분리
                if " - " in rest:
                    summary, detail = rest.split(" - ", 1)
                    html_parts.append(
                        f'<div class="analysis-title">📌 {title} {summary}</div>'
                        f'<div class="analysis-detail">{detail}</div>'
                    )
                else:
                    html_parts.append(
                        f'<div class="analysis-title">📌 {title}</div>'
                        f'<div class="analysis-detail">{rest}</div>'
                    )
            else:
                html_parts.append(f'<div class="analysis-detail">{stripped}</div>')
        elif stripped.startswith("- "):
            html_parts.append(
                f'<div class="analysis-detail">→ {stripped[2:]}</div>'
            )
        else:
            html_parts.append(f'<div class="analysis-detail">{stripped}</div>')

    st.markdown(
        f'<div class="analysis-section">{"".join(html_parts)}</div>',
        unsafe_allow_html=True,
    )


# ── 사이드바 ────────────────────────────────────

def sidebar_watchlist() -> list[str]:
    st.sidebar.header("📋 감시 종목 설정")

    current_stocks = ""
    if WATCHLIST_FILE.exists():
        lines = []
        for line in WATCHLIST_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.split("#")[0].strip()
            if stripped:
                lines.append(stripped)
        current_stocks = "\n".join(lines)

    stocks_input = st.sidebar.text_area(
        "종목코드 (한 줄에 하나)",
        value=current_stocks,
        height=150,
        help="종목코드를 한 줄에 하나씩 입력하세요. 예: 005930",
    )

    if st.sidebar.button("💾 종목 목록 저장"):
        codes = [line.strip() for line in stocks_input.splitlines() if line.strip()]
        content = "# 감시 종목 목록\n" + "\n".join(codes) + "\n"
        WATCHLIST_FILE.write_text(content, encoding="utf-8")
        st.sidebar.success(f"{len(codes)}종목 저장 완료!")
        st.rerun()

    codes = [line.strip() for line in stocks_input.splitlines() if line.strip()]
    return codes


def check_alerts(data: list[tuple[Orderbook, AnalysisResult]], portfolio: dict[str, StockHolding]):
    """알림 조건 체크"""
    prev_intensities = st.session_state.get("prev_intensities", {})

    for ob, analysis in data:
        name = ob.stock_name
        cp = ob.current_price
        if not cp:
            continue

        # 1. 목표가/손절가 도달 알림
        holding = portfolio.get(ob.stock_code)
        if holding and holding.has_position():
            if holding.target_price and cp >= holding.target_price:
                st.toast(f"🎯 {name} 목표가 {holding.target_price:,}원 도달! (현재 {cp:,}원)", icon="🎯")
            if holding.stop_loss_price and cp <= holding.stop_loss_price:
                st.toast(f"🛑 {name} 손절가 {holding.stop_loss_price:,}원 도달! (현재 {cp:,}원)", icon="🛑")

        # 2. 체결강도 급변 알림 (30% 이상 변화)
        ti = ob.trading_intensity
        prev_ti = prev_intensities.get(ob.stock_code, 0)
        if prev_ti and ti and abs(ti - prev_ti) >= 30:
            direction = "급등" if ti > prev_ti else "급락"
            st.toast(
                f"⚡ {name} 체결강도 {direction}! {prev_ti:.0f}% → {ti:.0f}%",
                icon="⚡",
            )
        if ti:
            prev_intensities[ob.stock_code] = ti

        # 3. VI 근접 알림 (3% 이내)
        if ob.vi_price and cp:
            vi_dist = abs(ob.vi_price - cp) / cp * 100
            if vi_dist <= 3:
                st.toast(
                    f"⚠️ {name} VI 발동가 근접! ({ob.vi_price:,}원, {vi_dist:.1f}% 남음)",
                    icon="⚠️",
                )

    st.session_state["prev_intensities"] = prev_intensities


def render_portfolio(ob: Orderbook, holding: StockHolding):
    """보유 종목 손익 표시"""
    if not holding.has_position():
        return

    cp = ob.current_price
    if not cp:
        return

    pl = holding.profit_loss(cp)
    pl_pct = holding.profit_pct(cp)
    pl_color = "price-up" if pl > 0 else ("price-down" if pl < 0 else "price-flat")
    pl_sign = "+" if pl > 0 else ""

    st.markdown("##### 💰 내 보유 현황")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("매입가", f"{holding.buy_price:,}원")
    p2.metric("보유 수량", f"{holding.quantity:,}주")
    p3.metric("평가금액", f"{holding.eval_amount(cp):,}원",
              delta=f"매입금 {holding.buy_amount():,}원")
    p4.metric("평가손익",
              f"{pl_sign}{pl:,}원",
              delta=f"{pl_sign}{pl_pct:.2f}%")

    # 목표가/손절가 표시
    targets = []
    if holding.target_price:
        tp = holding.target_profit()
        targets.append(f"🎯 목표가 {holding.target_price:,}원 (도달 시 +{tp:,}원)")
    if holding.stop_loss_price:
        sl = holding.stop_loss_amount()
        targets.append(f"🛑 손절가 {holding.stop_loss_price:,}원 (도달 시 {sl:,}원)")
    if targets:
        st.caption(" | ".join(targets))


# ── 사이드바: 매매 설정 ─────────────────────────

def sidebar_portfolio(stock_codes: list[str]):
    """사이드바 매매 설정"""
    st.sidebar.markdown("---")
    st.sidebar.header("💰 매매 설정")

    portfolio = load_portfolio()

    # 종목 선택
    stock_names = {}
    data = st.session_state.get("data", [])
    for ob, _ in data:
        stock_names[ob.stock_code] = ob.stock_name

    code_options = {
        f"{stock_names.get(c, c)} ({c})": c for c in stock_codes
    }

    selected_label = st.sidebar.selectbox(
        "종목 선택", list(code_options.keys()),
        key="portfolio_stock_select",
    )
    if not selected_label:
        return

    selected_code = code_options[selected_label]
    holding = portfolio.get(selected_code, StockHolding(stock_code=selected_code))

    # 입력 필드
    buy_price = st.sidebar.number_input(
        "매입가 (원)", min_value=0, value=holding.buy_price,
        step=100, key=f"buy_{selected_code}",
    )
    quantity = st.sidebar.number_input(
        "보유 수량 (주)", min_value=0, value=holding.quantity,
        step=1, key=f"qty_{selected_code}",
    )
    target_price = st.sidebar.number_input(
        "목표가 (원, 0=미설정)", min_value=0, value=holding.target_price,
        step=100, key=f"target_{selected_code}",
    )
    stop_loss_price = st.sidebar.number_input(
        "손절가 (원, 0=미설정)", min_value=0, value=holding.stop_loss_price,
        step=100, key=f"stop_{selected_code}",
    )

    if st.sidebar.button("💾 매매 설정 저장", key="save_portfolio"):
        new_holding = StockHolding(
            stock_code=selected_code,
            buy_price=buy_price,
            quantity=quantity,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
        )
        save_holding(new_holding)
        st.sidebar.success("저장 완료!")
        st.rerun()


# ── 메인 ────────────────────────────────────────

def main():
    st.title("📈 주식 호가창 분석 봇")

    stock_codes = sidebar_watchlist()
    if not stock_codes:
        st.warning("사이드바에서 감시 종목을 입력하세요.")
        return

    st.sidebar.markdown("---")
    if len(stock_codes) > 3:
        st.sidebar.info(
            f"감시 종목: {len(stock_codes)}개\n\n"
            f"KIS WebSocket 최대 3종목 동시 구독\n"
            f"→ {len(stock_codes)}종목 배치 교대 수집"
        )
    else:
        st.sidebar.info(f"감시 종목: {len(stock_codes)}개")

    # 전체 갱신 버튼
    refresh_all = st.button("🔄 전체 갱신", type="primary")

    market_data, settings = init_market_data()
    analyzer = RuleBasedAnalyzerAdapter(
        imbalance_threshold_pct=settings.analysis.imbalance_threshold_pct,
        wall_volume_ratio=settings.analysis.wall_volume_ratio,
    )

    if refresh_all or "data" not in st.session_state:
        with st.spinner("📡 전체 데이터 수집 중... (종목당 약 2초 소요)"):
            try:
                data = run_async(fetch_all_data(market_data, analyzer, stock_codes))
                st.session_state["data"] = data
            except Exception as e:
                st.error(f"데이터 수집 실패: {e}")
                return

    data = st.session_state.get("data", [])
    if not data:
        st.warning("수신된 데이터가 없습니다. 장 시간을 확인하세요.")
        return

    # 사이드바: 매매 설정
    sidebar_portfolio(stock_codes)

    # 포트폴리오 로드
    portfolio = load_portfolio()

    # 알림 체크 (갱신 직후)
    if refresh_all:
        check_alerts(data, portfolio)

    # 탭 이름
    tab_names = []
    for ob, _ in data:
        name = ob.stock_name if ob.stock_name != ob.stock_code else ob.stock_code
        tab_names.append(f"{name} ({ob.stock_code})")

    tabs = st.tabs(tab_names)

    for i, (tab, (ob, analysis)) in enumerate(zip(tabs, data)):
        with tab:
            # 개별 종목 갱신 버튼
            if st.button(f"🔄 {ob.stock_name} 갱신", key=f"refresh_{ob.stock_code}"):
                with st.spinner(f"📡 {ob.stock_name} 수집 중..."):
                    try:
                        result = run_async(
                            fetch_single_stock(market_data, analyzer, ob.stock_code)
                        )
                        if result:
                            updated = list(st.session_state["data"])
                            updated[i] = result
                            st.session_state["data"] = updated
                            st.rerun()
                        else:
                            st.error("데이터 수신 실패")
                    except Exception as e:
                        st.error(f"갱신 실패: {e}")

            # 보유 현황 표시
            holding = portfolio.get(ob.stock_code, StockHolding(stock_code=ob.stock_code))
            render_portfolio(ob, holding)

            # 호가창 (목표가/손절가 전달)
            render_orderbook(ob, holding)
            st.markdown("---")
            st.subheader("📊 분석 결과")
            render_analysis(analysis)


if __name__ == "__main__":
    main()

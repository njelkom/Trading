"""
호가창 분석 REST API
GET /api/orderbook?stocks=005930,000660
"""

import asyncio
import sys
from dataclasses import replace, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.config.settings import load_settings
from src.infrastructure.kis.kis_market_data_adapter import KISMarketDataAdapter
from src.infrastructure.ai.rule_based_analyzer_adapter import RuleBasedAnalyzerAdapter
from src.infrastructure.storage.intensity_history import get_intensity_history

app = FastAPI(
    title="호가창 분석 API",
    description="KIS API 실시간 호가창 데이터 + 분석 결과를 JSON으로 제공",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 인스턴스
_market_data: KISMarketDataAdapter | None = None
_analyzer: RuleBasedAnalyzerAdapter | None = None


async def get_adapter() -> KISMarketDataAdapter:
    global _market_data, _analyzer
    if _market_data is None:
        settings = load_settings()
        _market_data = KISMarketDataAdapter(settings.kis)
        await _market_data.authenticate()
        _analyzer = RuleBasedAnalyzerAdapter(
            imbalance_threshold_pct=settings.analysis.imbalance_threshold_pct,
            wall_volume_ratio=settings.analysis.wall_volume_ratio,
        )
    return _market_data


@app.get("/")
async def root():
    return {
        "name": "호가창 분석 API",
        "endpoints": {
            "/api/orderbook": "호가 + 시세 + 분석 (GET ?stocks=005930,000660)",
            "/api/price": "현재가 조회 (GET ?stock=005930)",
            "/api/intensity": "체결강도 히스토리 (GET ?stock=005930)",
        }
    }


@app.get("/api/orderbook")
async def get_orderbook(
    stocks: str = Query(default="005930", description="종목코드 (쉼표 구분)"),
):
    """호가창 + 시세 + 분석 결과를 JSON으로 반환"""
    market_data = await get_adapter()
    stock_codes = [s.strip() for s in stocks.split(",") if s.strip()]

    # 종목명 조회
    missing = [c for c in stock_codes if not market_data.has_stock_name(c)]
    if missing:
        await market_data.fetch_stock_names(missing)

    # WebSocket 호가 수집
    await market_data.connect_ws()
    all_orderbooks = {}
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

    # REST 시세 + 이동평균 조회
    results = []
    for code in stock_codes:
        if code not in all_orderbooks:
            results.append({"stock_code": code, "error": "호가 데이터 수신 실패"})
            continue

        ob = all_orderbooks[code]
        try:
            price_info = await market_data.get_current_price(code)
            await asyncio.sleep(0.5)
            ma_info = await market_data.get_moving_averages(code)
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
        except Exception:
            pass
        await asyncio.sleep(1.0)

        # 분석
        analysis = await _analyzer.analyze(ob)

        results.append({
            "stock_code": ob.stock_code,
            "stock_name": ob.stock_name,
            "current_price": ob.current_price,
            "change_pct": ob.change_pct,
            "trading_intensity": ob.trading_intensity,
            "bid_ratio_pct": ob.bid_ratio_pct,
            "volume": ob.volume,
            "volume_rate": ob.volume_rate,
            "open_price": ob.open_price,
            "high_price": ob.high_price,
            "low_price": ob.low_price,
            "prev_close": ob.prev_close,
            "w52_high": ob.w52_high,
            "w52_low": ob.w52_low,
            "vi_price": ob.vi_price,
            "ma5": ob.ma5,
            "ma20": ob.ma20,
            "ma60": ob.ma60,
            "spread": ob.spread,
            "spread_pct": round(ob.spread_pct, 4),
            "ask_entries": [
                {"price": e.price, "volume": e.volume}
                for e in ob.ask_entries
            ],
            "bid_entries": [
                {"price": e.price, "volume": e.volume}
                for e in ob.bid_entries
            ],
            "total_ask_volume": ob.total_ask_volume,
            "total_bid_volume": ob.total_bid_volume,
            "analysis": {
                "signal": analysis.signal.label,
                "text": analysis.text,
            },
        })

    return {"stocks": results}


@app.get("/api/price")
async def get_price(
    stock: str = Query(description="종목코드"),
):
    """현재가 간단 조회"""
    market_data = await get_adapter()

    if not market_data.has_stock_name(stock):
        await market_data.fetch_stock_names([stock])

    price_info = await market_data.get_current_price(stock)
    return {
        "stock_code": stock,
        "stock_name": market_data.get_stock_name(stock),
        **price_info,
    }


@app.get("/api/intensity")
async def get_intensity(
    stock: str = Query(description="종목코드"),
):
    """체결강도 히스토리 조회"""
    history = get_intensity_history(stock)
    return {
        "stock_code": stock,
        "count": len(history),
        "history": history,
    }

"""
한국투자증권 KIS OpenAPI 어댑터
- REST: 접근토큰 발급, 현재가 조회, 종목명 조회
- WebSocket: 실시간 호가 수신 (최대 3종목 구독 제한 대응)
"""

import asyncio
import json
import os
from collections.abc import Callable, Awaitable
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import websockets

from src.application.ports.market_data_port import MarketDataPort
from src.domain.entities.orderbook import Orderbook, OrderbookEntry
from src.domain.exceptions import AuthenticationError, ConnectionError
from src.infrastructure.config.settings import KISSettings


ORDERBOOK_TR_ID = "H0STASP0"
MAX_SUBSCRIBE = 3
TOKEN_CACHE_FILE = Path(__file__).parent / ".token_cache.json"


class KISMarketDataAdapter(MarketDataPort):
    def __init__(self, settings: KISSettings):
        self._settings = settings
        self._access_token: str = ""
        self._token_expires: datetime = datetime.min
        self._approval_key: str = ""
        self._stock_names: dict[str, str] = {}
        self._ws = None
        self._subscribed: list[str] = []

    # ── 인증 ──────────────────────────────────────

    async def authenticate(self) -> None:
        await self._issue_access_token()
        await self._issue_approval_key()

    async def _issue_access_token(self) -> None:
        # 캐시된 토큰이 유효하면 재사용
        cached = self._load_token_cache()
        if cached:
            self._access_token = cached["token"]
            self._token_expires = datetime.fromisoformat(cached["expires"])
            print("  (캐시된 토큰 사용)")
            return

        url = f"{self._settings.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self._settings.app_key,
            "appsecret": self._settings.app_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if "access_token" not in data:
                    raise AuthenticationError(f"토큰 발급 실패: {data}")
                self._access_token = data["access_token"]
                expires_in = int(data.get("expires_in", 86400))
                self._token_expires = datetime.now() + timedelta(
                    seconds=expires_in - 60
                )
                self._save_token_cache()

    def _load_token_cache(self) -> dict | None:
        try:
            if not TOKEN_CACHE_FILE.exists():
                return None
            with open(TOKEN_CACHE_FILE) as f:
                data = json.load(f)
            expires = datetime.fromisoformat(data["expires"])
            if datetime.now() >= expires:
                return None
            return data
        except Exception:
            return None

    def _save_token_cache(self) -> None:
        try:
            data = {
                "token": self._access_token,
                "expires": self._token_expires.isoformat(),
            }
            with open(TOKEN_CACHE_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    async def _issue_approval_key(self) -> None:
        url = f"{self._settings.base_url}/oauth2/Approval"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self._settings.app_key,
            "secretkey": self._settings.app_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if "approval_key" not in data:
                    raise AuthenticationError(
                        f"WebSocket 접속키 발급 실패: {data}"
                    )
                self._approval_key = data["approval_key"]

    # ── 종목명 조회 ──────────────────────────────────

    async def fetch_stock_names(self, stock_codes: list[str]) -> None:
        url = (
            f"{self._settings.base_url}"
            "/uapi/domestic-stock/v1/quotations/search-info"
        )
        async with aiohttp.ClientSession() as session:
            for i, code in enumerate(stock_codes):
                try:
                    if i > 0:
                        await asyncio.sleep(1.0)
                    headers = {
                        "authorization": f"Bearer {self._access_token}",
                        "appkey": self._settings.app_key,
                        "appsecret": self._settings.app_secret,
                        "tr_id": "CTPF1002R",
                    }
                    params = {"PRDT_TYPE_CD": "300", "PDNO": code}
                    async with session.get(url, headers=headers, params=params) as resp:
                        data = await resp.json()
                        output = data.get("output", {})
                        name = output.get("prdt_abrv_name", "")
                        self._stock_names[code] = name if name else code
                        print(f"  [{code}] {self._stock_names[code]}")
                except Exception as e:
                    print(f"[WARN] {code} 종목명 조회 실패: {e}")
                    self._stock_names[code] = code

    def get_stock_name(self, code: str) -> str:
        return self._stock_names.get(code, code)

    def has_stock_name(self, code: str) -> bool:
        """종목명이 실제로 조회된 적 있는지 확인"""
        name = self._stock_names.get(code)
        return name is not None and name != code

    # ── WebSocket 연결 관리 ──────────────────────────

    async def connect_ws(self) -> None:
        # 기존 연결이 있으면 먼저 정리
        await self.disconnect_ws()
        uri = self._settings.ws_url
        self._ws = await websockets.connect(uri, ping_interval=30)

    async def disconnect_ws(self) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
            self._subscribed = []

    async def subscribe_stocks(self, stock_codes: list[str]) -> None:
        """현재 구독 해제 후 새 종목 구독 (최대 3종목)"""
        if not self._ws:
            await self.connect_ws()

        # 기존 구독 해제
        for code in self._subscribed:
            try:
                await self._send_subscribe(code, subscribe=False)
            except Exception:
                pass
            await asyncio.sleep(0.3)

        self._subscribed = []

        # 새 종목 구독
        for code in stock_codes[:MAX_SUBSCRIBE]:
            await self._send_subscribe(code, subscribe=True)
            await asyncio.sleep(0.3)
            self._subscribed.append(code)

    async def collect_orderbooks(self, timeout_sec: float = 3.0) -> dict[str, Orderbook]:
        """현재 구독 중인 종목의 호가 데이터를 수집"""
        if not self._ws:
            return {}

        result: dict[str, Orderbook] = {}
        end_time = asyncio.get_event_loop().time() + timeout_sec

        while asyncio.get_event_loop().time() < end_time:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
                orderbook = self._parse_message(raw)
                if orderbook:
                    result[orderbook.stock_code] = orderbook
                    # 구독한 종목 모두 수신했으면 조기 종료
                    if all(c in result for c in self._subscribed):
                        break
            except asyncio.TimeoutError:
                continue
            except (websockets.exceptions.ConnectionClosed, OSError):
                try:
                    await self.connect_ws()
                    for code in self._subscribed:
                        await self._send_subscribe(code, subscribe=True)
                        await asyncio.sleep(0.3)
                except Exception:
                    break

        return result

    async def _send_subscribe(self, stock_code: str, subscribe: bool = True) -> None:
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1" if subscribe else "2",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": ORDERBOOK_TR_ID,
                    "tr_key": stock_code,
                }
            },
        }
        await self._ws.send(json.dumps(msg))

    # ── 기존 인터페이스 (하위 호환) ──────────────────

    async def stream_orderbook(
        self,
        stock_codes: list[str],
        callback: Callable[[Orderbook], Awaitable[None]],
    ) -> None:
        missing = [c for c in stock_codes if c not in self._stock_names]
        if missing:
            await self.fetch_stock_names(missing)

        await self.connect_ws()
        await self.subscribe_stocks(stock_codes[:MAX_SUBSCRIBE])

        try:
            async for raw in self._ws:
                try:
                    orderbook = self._parse_message(raw)
                    if orderbook:
                        await callback(orderbook)
                except Exception as e:
                    print(f"[파싱 오류] {e} | raw: {raw[:80]}")
        finally:
            await self.disconnect_ws()

    # ── 파싱 ─────────────────────────────────────────

    def _parse_message(self, raw: str) -> Orderbook | None:
        if raw.startswith("{"):
            return None

        parts = raw.split("|")
        if len(parts) < 4:
            return None

        tr_id = parts[1]
        if tr_id != ORDERBOOK_TR_ID:
            return None

        data_parts = parts[3].split("^")
        if len(data_parts) < 50:
            return None

        stock_code = data_parts[0]

        # H0STASP0 레이아웃:
        # [3~12] 매도호가 1~10 (가격), [13~22] 매수호가 1~10 (가격)
        # [23~32] 매도잔량 1~10,       [33~42] 매수잔량 1~10
        ask_entries = [
            OrderbookEntry(
                price=int(data_parts[3 + i]),
                volume=int(data_parts[23 + i]),
            )
            for i in range(10)
        ]

        bid_entries = [
            OrderbookEntry(
                price=int(data_parts[13 + i]),
                volume=int(data_parts[33 + i]),
            )
            for i in range(10)
        ]

        return Orderbook(
            stock_code=stock_code,
            stock_name=self._stock_names.get(stock_code, stock_code),
            timestamp=datetime.now(),
            ask_entries=ask_entries,
            bid_entries=bid_entries,
        )

    # ── REST: 이동평균 조회 ────────────────────────

    async def get_moving_averages(self, stock_code: str) -> dict[str, int]:
        """일별 시세에서 5/20/60일 이동평균 계산"""
        url = (
            f"{self._settings.base_url}"
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        )
        headers = {
            "authorization": f"Bearer {self._access_token}",
            "appkey": self._settings.app_key,
            "appsecret": self._settings.app_secret,
            "tr_id": "FHKST01010400",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        result = {"ma5": 0, "ma20": 0, "ma60": 0}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    data = await resp.json()
                    rows = data.get("output", [])

            closes = [int(r.get("stck_clpr", 0)) for r in rows if r.get("stck_clpr")]
            if len(closes) >= 5:
                result["ma5"] = round(sum(closes[:5]) / 5)
            if len(closes) >= 20:
                result["ma20"] = round(sum(closes[:20]) / 20)
            if len(closes) >= 30:
                # 30일치만 가용하면 30일 평균으로 대체 표시
                result["ma60"] = round(sum(closes[:len(closes)]) / len(closes))
        except Exception:
            pass

        return result

    # ── REST: 현재가 + 체결강도 조회 ────────────────

    async def get_current_price(self, stock_code: str) -> dict:
        async with aiohttp.ClientSession() as session:
            # 현재가 조회
            headers = {
                "authorization": f"Bearer {self._access_token}",
                "appkey": self._settings.app_key,
                "appsecret": self._settings.app_secret,
                "tr_id": "FHKST01010100",
            }
            params = {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": stock_code,
            }
            async with session.get(
                f"{self._settings.base_url}"
                "/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=headers, params=params,
            ) as resp:
                data = await resp.json()
                output = data.get("output", {})

            result = {
                "name": self._stock_names.get(stock_code, stock_code),
                "price": int(output.get("stck_prpr", 0)),
                "change_pct": float(output.get("prdy_ctrt", 0)),
                "volume": int(output.get("acml_vol", 0)),
                "volume_rate": float(output.get("prdy_vrss_vol_rate", 0)),
                "open_price": int(output.get("stck_oprc", 0)),
                "high_price": int(output.get("stck_hgpr", 0)),
                "low_price": int(output.get("stck_lwpr", 0)),
                "prev_close": int(output.get("stck_sdpr", 0)),
                "w52_high": int(output.get("w52_hgpr", 0)),
                "w52_low": int(output.get("w52_lwpr", 0)),
                "vi_price": int(output.get("stck_sspr", 0)),
                "trading_intensity": 0.0,
            }

            # 체결강도 조회 (inquire-ccnl)
            await asyncio.sleep(0.5)
            headers["tr_id"] = "FHKST01010300"
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
            }
            try:
                async with session.get(
                    f"{self._settings.base_url}"
                    "/uapi/domestic-stock/v1/quotations/inquire-ccnl",
                    headers=headers, params=params,
                ) as resp:
                    data = await resp.json()
                    output1 = data.get("output1", data.get("output", []))
                    if isinstance(output1, list) and output1:
                        result["trading_intensity"] = float(
                            output1[0].get("tday_rltv", 0)
                        )
                    elif isinstance(output1, dict):
                        result["trading_intensity"] = float(
                            output1.get("tday_rltv", 0)
                        )
            except Exception:
                pass

            return result

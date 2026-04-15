from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OrderbookEntry:
    price: int
    volume: int


@dataclass(frozen=True)
class Orderbook:
    stock_code: str
    stock_name: str
    timestamp: datetime
    ask_entries: list[OrderbookEntry]  # 매도 호가 (낮은 가격순)
    bid_entries: list[OrderbookEntry]  # 매수 호가 (높은 가격순)
    current_price: int = 0             # 현재가
    change_pct: float = 0.0           # 전일 대비 등락률 (%)
    trading_intensity: float = 0.0    # 체결강도 (%)
    volume: int = 0                   # 누적 거래량
    volume_rate: float = 0.0          # 전일 대비 거래량 비율 (%)
    open_price: int = 0               # 시가
    high_price: int = 0               # 장중 고가
    low_price: int = 0                # 장중 저가
    prev_close: int = 0               # 전일 종가
    w52_high: int = 0                 # 52주 최고가
    w52_low: int = 0                  # 52주 최저가
    vi_price: int = 0                 # 정적 VI 발동가
    ma5: int = 0                      # 5일 이동평균
    ma20: int = 0                     # 20일 이동평균
    ma60: int = 0                     # 60일 이동평균

    @property
    def total_ask_volume(self) -> int:
        return sum(e.volume for e in self.ask_entries)

    @property
    def total_bid_volume(self) -> int:
        return sum(e.volume for e in self.bid_entries)

    @property
    def bid_ratio_pct(self) -> float:
        total = self.total_ask_volume + self.total_bid_volume
        if total == 0:
            return 50.0
        return round(self.total_bid_volume / total * 100, 1)

    @property
    def spread(self) -> int:
        if not self.ask_entries or not self.bid_entries:
            return 0
        return self.ask_entries[0].price - self.bid_entries[0].price

    @property
    def spread_pct(self) -> float:
        if not self.bid_entries or self.bid_entries[0].price == 0:
            return 0.0
        return self.spread / self.bid_entries[0].price * 100

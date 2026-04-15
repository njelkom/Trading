from dataclasses import dataclass

from src.domain.value_objects.signal import Signal


@dataclass(frozen=True)
class AnalysisResult:
    stock_code: str
    stock_name: str
    text: str
    signal: Signal
    current_price: int = 0
    change_pct: float = 0.0
    trading_intensity: float = 0.0
    volume: int = 0
    volume_rate: float = 0.0
    open_price: int = 0
    high_price: int = 0
    low_price: int = 0
    prev_close: int = 0
    w52_high: int = 0
    w52_low: int = 0
    vi_price: int = 0
    ma5: int = 0
    ma20: int = 0
    ma60: int = 0

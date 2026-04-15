from enum import Enum


class Signal(Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"

    @property
    def label(self) -> str:
        labels = {
            Signal.BUY: "매수 우위",
            Signal.SELL: "매도 우위",
            Signal.NEUTRAL: "중립",
        }
        return labels[self]

    @property
    def emoji(self) -> str:
        emojis = {
            Signal.BUY: "\U0001f7e2",
            Signal.SELL: "\U0001f534",
            Signal.NEUTRAL: "\U0001f7e1",
        }
        return emojis[self]

"""
포트폴리오 저장/로드 (종목별 매입가, 보유수량, 목표가, 손절가)
JSON 파일 기반
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path

PORTFOLIO_FILE = Path(__file__).parent.parent.parent.parent / "portfolio.json"


@dataclass
class StockHolding:
    stock_code: str
    buy_price: int = 0        # 매입가
    quantity: int = 0          # 보유 수량
    target_price: int = 0     # 목표가
    stop_loss_price: int = 0  # 손절가

    def eval_amount(self, current_price: int) -> int:
        """평가금액"""
        return current_price * self.quantity

    def buy_amount(self) -> int:
        """매입금액"""
        return self.buy_price * self.quantity

    def profit_loss(self, current_price: int) -> int:
        """평가손익"""
        if not self.buy_price or not self.quantity:
            return 0
        return (current_price - self.buy_price) * self.quantity

    def profit_pct(self, current_price: int) -> float:
        """수익률 (%)"""
        if not self.buy_price:
            return 0.0
        return round((current_price - self.buy_price) / self.buy_price * 100, 2)

    def target_profit(self) -> int:
        """목표가 도달 시 예상 수익금"""
        if not self.target_price or not self.buy_price or not self.quantity:
            return 0
        return (self.target_price - self.buy_price) * self.quantity

    def stop_loss_amount(self) -> int:
        """손절가 도달 시 예상 손실금"""
        if not self.stop_loss_price or not self.buy_price or not self.quantity:
            return 0
        return (self.stop_loss_price - self.buy_price) * self.quantity

    def has_position(self) -> bool:
        return self.buy_price > 0 and self.quantity > 0


def load_portfolio() -> dict[str, StockHolding]:
    """전체 포트폴리오 로드"""
    try:
        if PORTFOLIO_FILE.exists():
            with open(PORTFOLIO_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return {
                code: StockHolding(**holding)
                for code, holding in data.items()
            }
    except Exception:
        pass
    return {}


def save_portfolio(portfolio: dict[str, StockHolding]) -> None:
    """전체 포트폴리오 저장"""
    try:
        data = {code: asdict(h) for code, h in portfolio.items()}
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_holding(stock_code: str) -> StockHolding:
    """종목별 보유 정보 조회"""
    portfolio = load_portfolio()
    return portfolio.get(stock_code, StockHolding(stock_code=stock_code))


def save_holding(holding: StockHolding) -> None:
    """종목별 보유 정보 저장"""
    portfolio = load_portfolio()
    portfolio[holding.stock_code] = holding
    save_portfolio(portfolio)

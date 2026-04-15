from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable

from src.domain.entities.orderbook import Orderbook


class MarketDataPort(ABC):
    @abstractmethod
    async def authenticate(self) -> None:
        ...

    @abstractmethod
    async def stream_orderbook(
        self,
        stock_codes: list[str],
        callback: Callable[[Orderbook], Awaitable[None]],
    ) -> None:
        ...

    @abstractmethod
    async def get_current_price(self, stock_code: str) -> dict:
        ...

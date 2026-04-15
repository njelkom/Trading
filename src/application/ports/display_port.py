from abc import ABC, abstractmethod

from src.domain.entities.orderbook import Orderbook
from src.domain.entities.analysis_result import AnalysisResult


class DisplayPort(ABC):
    @abstractmethod
    def show_banner(self) -> None:
        ...

    @abstractmethod
    def clear_and_banner(self) -> None:
        ...

    @abstractmethod
    def show_step(self, msg: str) -> None:
        ...

    @abstractmethod
    def show_ok(self, msg: str) -> None:
        ...

    @abstractmethod
    def show_error(self, msg: str) -> None:
        ...

    @abstractmethod
    def show_orderbook(self, orderbook: Orderbook) -> None:
        ...

    @abstractmethod
    def show_analyzing(self, stock_code: str) -> None:
        ...

    @abstractmethod
    def show_analysis(self, result: AnalysisResult) -> None:
        ...

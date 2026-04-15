from abc import ABC, abstractmethod

from src.domain.entities.orderbook import Orderbook
from src.domain.entities.analysis_result import AnalysisResult


class AnalyzerPort(ABC):
    @abstractmethod
    async def analyze(self, orderbook: Orderbook) -> AnalysisResult:
        ...

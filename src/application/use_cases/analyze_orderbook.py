from src.application.ports.analyzer_port import AnalyzerPort
from src.application.ports.display_port import DisplayPort
from src.domain.entities.orderbook import Orderbook
from src.domain.entities.analysis_result import AnalysisResult


class AnalyzeOrderbookUseCase:
    def __init__(self, analyzer: AnalyzerPort, display: DisplayPort):
        self._analyzer = analyzer
        self._display = display

    async def execute(self, orderbook: Orderbook) -> AnalysisResult:
        self._display.show_analyzing(orderbook.stock_code)
        result = await self._analyzer.analyze(orderbook)
        self._display.show_analysis(result)
        return result

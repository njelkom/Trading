# CLAUDE.md - 주식 호가창 분석 봇

## 프로젝트 개요

한국투자증권(KIS) OpenAPI를 통해 실시간 호가창 데이터를 수신하고, Claude AI로 분석하는 봇.
현재 단계: 호가창 분석 봇 (실시간 트레이딩은 추후 구현 예정)

## 기술 스택

- **언어**: Python 3.12+
- **비동기**: asyncio, aiohttp, websockets
- **AI**: Anthropic Python SDK (claude-sonnet-4-20250514)
- **외부 API**: 한국투자증권 KIS OpenAPI (REST + WebSocket)
- **설정**: python-dotenv (.env)

## 클린 아키텍처 원칙

이 프로젝트는 클린 아키텍처(Clean Architecture) 기반으로 개발한다.
모든 코드 변경은 아래 레이어 구조와 의존성 규칙을 따라야 한다.

### 디렉토리 구조 (목표)

```
src/
├── domain/              # 엔티티, 값 객체, 비즈니스 규칙 (의존성 없음)
│   ├── entities/        # Orderbook, Stock, AnalysisResult 등
│   └── value_objects/   # Price, Volume, Signal 등
│
├── application/         # 유스케이스, 포트(인터페이스)
│   ├── use_cases/       # AnalyzeOrderbook, StreamOrderbook 등
│   ├── ports/           # ABC 인터페이스 (MarketDataPort, AnalyzerPort 등)
│   └── dto/             # 유스케이스 입출력 DTO
│
├── infrastructure/      # 외부 시스템 어댑터 (포트 구현체)
│   ├── kis/             # KIS API 연동 (REST, WebSocket)
│   ├── ai/              # Claude API 연동
│   └── config/          # 환경변수, 설정 로더
│
├── presentation/        # UI/출력 레이어
│   └── terminal/        # 터미널 출력, 포맷팅
│
└── main.py              # 컴포지션 루트 (DI, 부트스트랩)
```

### 의존성 규칙

- **domain** -> 아무것도 import하지 않음 (순수 Python만)
- **application** -> domain만 import
- **infrastructure** -> application(포트), domain을 import
- **presentation** -> application(DTO), domain을 import
- **main.py** -> 모든 레이어를 import하여 조립 (Composition Root)

외부 라이브러리(aiohttp, websockets, anthropic 등)는 infrastructure 레이어에서만 사용한다.

### 핵심 포트(인터페이스)

```python
# application/ports/market_data_port.py
class MarketDataPort(ABC):
    async def stream_orderbook(self, stock_codes, callback): ...
    async def get_current_price(self, stock_code) -> dict: ...

# application/ports/analyzer_port.py  
class AnalyzerPort(ABC):
    async def analyze(self, stock_code, orderbook) -> AnalysisResult: ...

# application/ports/display_port.py
class DisplayPort(ABC):
    def show_orderbook(self, stock_code, orderbook): ...
    def show_analysis(self, stock_code, result): ...
```

## 개발 컨벤션

### 일반

- 한국어 주석/문서, 영어 코드(변수명, 함수명)
- 타입 힌트 필수 (Python 3.12+ 네이티브 문법 사용)
- 비동기 함수는 async/await 사용 (asyncio 기반)
- 모든 설정값은 환경변수(.env)에서 로드, 하드코딩 금지

### 네이밍

- 파일/모듈: snake_case
- 클래스: PascalCase
- 함수/변수: snake_case
- 상수: UPPER_SNAKE_CASE
- 포트(인터페이스): `*Port` 접미사
- 어댑터(구현체): 구체적 이름 (예: `KISMarketDataAdapter`)

### 에러 처리

- domain 레이어: 커스텀 예외 정의
- infrastructure 레이어: 외부 API 에러를 도메인 예외로 변환
- 최상위(main)에서만 catch-all 처리

## 실행 방법

```bash
pip install -r requirements.txt
cp .env.example .env  # API 키 설정
python main.py
```

## 환경변수 (.env)

```
KIS_APP_KEY=        # 한투 앱 키
KIS_APP_SECRET=     # 한투 앱 시크릿
KIS_ACCOUNT_NO=     # 계좌번호 (예: 50123456-01)
ANTHROPIC_API_KEY=  # Claude API 키
WATCH_STOCKS=005930,000660,035420  # 감시 종목코드
```

## 주의사항

- .env 파일은 절대 커밋하지 않는다
- KIS 모의투자 환경에서 먼저 테스트한다
- Claude API 비용을 고려하여 분석 간격(ANALYSIS_INTERVAL_SECONDS)을 적절히 설정한다
- 본 봇은 정보 제공 목적이며, 투자 권유가 아니다

# 주식 호가창 분석 봇

한국투자증권(KIS) OpenAPI 실시간 호가창 수신 + Claude AI 분석 봇

## 아키텍처

클린 아키텍처(Clean Architecture) 기반으로 레이어가 분리되어 있습니다.

```
src/
├── domain/                  # 엔티티, 값 객체, 비즈니스 규칙
│   ├── entities/            # Orderbook, AnalysisResult
│   ├── value_objects/       # Signal (BUY/SELL/NEUTRAL)
│   └── exceptions.py        # 도메인 예외
│
├── application/             # 유스케이스, 포트(인터페이스)
│   ├── ports/               # MarketDataPort, AnalyzerPort, DisplayPort
│   └── use_cases/           # AnalyzeOrderbook, StreamOrderbook
│
├── infrastructure/          # 외부 시스템 어댑터
│   ├── kis/                 # KIS OpenAPI (REST + WebSocket)
│   ├── ai/                  # Claude API 연동
│   └── config/              # 환경변수 설정 로더
│
├── presentation/            # UI 레이어
│   └── terminal/            # 터미널 ANSI 컬러 출력
│
└── main.py                  # Composition Root (DI 조립)
```

### 의존성 방향

```
presentation ──┐
               ├──> application ──> domain
infrastructure ┘
```

외부 라이브러리(aiohttp, websockets, anthropic)는 infrastructure에서만 사용합니다.

## 사전 준비

### 1. KIS OpenAPI 발급
1. [한국투자증권 OpenAPI 포털](https://apiportal.koreainvestment.com) 접속
2. 로그인 → My API → 앱 등록
3. App Key / App Secret 발급
4. 모의투자로 먼저 테스트 권장

### 2. Claude API 발급
1. [Anthropic Console](https://console.anthropic.com) 접속
2. API Keys → Create Key

## 설치 및 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일 열어서 실제 키 입력

# 실행
python run.py
```

## 주의사항

- 본 봇은 **정보 제공 목적**으로만 사용하세요
- 투자 손실에 대한 책임은 사용자 본인에게 있습니다
- KIS 모의투자 환경에서 충분히 테스트 후 실전 전환 권장
- Claude API 비용을 고려하여 분석 간격을 적절히 설정하세요

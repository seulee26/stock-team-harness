# 주식 리서치 하네스

Codex·Claude 리서치 팀과 토스증권 연결을 한 폴더에서 쓸 수 있습니다. 토스 계좌 조회, 수수료 계산, 알림 판정은 로컬에서 실행합니다. 연구팀에는 정해진 형식의 공개 시세만 전달합니다. 구조와 보안 경계는 `harness/ARCHITECTURE.md`에 있습니다.

## 빠른 실행

패키지 루트에서 실행합니다. macOS와 Linux의 Python 3.9 이상이 필요합니다. 기본 조회에 추가 라이브러리는 필요 없습니다.

```bash
python3 harness/stock_harness.py portfolio
python3 harness/stock_harness.py sale-fee KOSPI 100000000
python3 harness/stock_harness.py check-alert
python3 harness/stock_harness.py watch-alert --notify mac
```

- `portfolio`는 보유 종목, 종목별 평가손익·수익률과 원화·달러 매수 가능 금액을 반환합니다.
- `sale-fee`는 내 계좌 요율을 적용합니다. 국내 코스피·코스닥 일반주식은 원화, 미국주식은 달러로 입력합니다. 금액은 한 건의 총 체결대금 기준이며 환전과 양도소득세는 별도입니다. 거래세·SEC Fee 기준일은 2026년 11월 20일입니다. `--json`으로 적용 요율과 계산 항목을 확인할 수 있습니다. [국내 거래세](https://www.nabo.go.kr/board/file/down.do?fid=33319156) · [토스 미국주식 비용](https://corp.tossinvest.com/ko/faq?page=1&searchTitleKeyword=%EC%88%98%EC%88%98%EB%A3%8C&tab=101)
- 계좌가 여러 개면 `api getAccounts`로 확인한 뒤 `--account`로 사용할 계좌를 지정합니다.

## 로컬 연결

소유자만 읽을 수 있는 파일에 `TOSSINVEST_CLIENT_ID`, `TOSSINVEST_CLIENT_SECRET`을 넣고 `TOSSINVEST_ENV_FILE`로 해당 파일을 지정하거나 두 환경 변수를 전달합니다. 토스증권 Open API의 허용 IP에서 실행합니다. 토큰과 알림 상태는 사용자 전용 로컬 상태 폴더에 저장됩니다. [토스증권 인증 안내](https://developers.tossinvest.com/docs/auth)

## 종가 알림

`harness/ant-alert.example.json`은 가상 ANT 규칙입니다. 최근 두 미국 정규장의 종가가 모두 $99를 넘고 저가가 모두 $93 이상일 때의 동작을 예시로 보여줍니다. 가상 검토 상한은 $101입니다. 실제 규칙은 별도 JSON 파일을 만든 뒤 `--rule`로 지정하세요.

거래시간 API로 개장·마감·조기 마감을 확인한 뒤, 분봉의 종료 시각을 기준으로 두 정규장만 집계합니다. 장 마감 5분 뒤부터 확인하며 분봉이 빠져 있으면 알림을 보류합니다. `check-alert --json`으로 판정에 사용한 날짜와 데이터 수를 볼 수 있습니다. 새 규칙은 JSON을 복사하고 `--rule`로 지정합니다. [미국 거래시간 API](https://developers.tossinvest.com/docs/market-info) · [분봉 조회 API](https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/MarketDataApi.md#getCandles)

`watch-alert`는 프로세스가 실행되는 동안 5분마다 확인합니다. 조건이 처음 성립할 때만 알리고, 조건이 해제된 뒤 다시 성립하면 다시 알립니다. 기본 알림은 터미널 출력이며 `--notify mac`은 Mac 알림이 허용된 로그인 세션에서 사용합니다.

## 리서치와 과거 검증

```bash
python3 harness/stock_harness.py research-plan ANT
python3 harness/stock_harness.py market-packet ANT
python3 harness/stock_harness.py research-check /path/to/public-evidence.json
python3 harness/stock_harness.py replay-alert harness/sample-alert-replay.json --through 2026-10-08
```

- `research-plan`은 공개 자료 조사 역할의 순서와 기준시각을 정합니다. 과거 기준은 시간대가 붙은 `--as-of`로 지정합니다.
- `market-packet`은 달러·원화 등 공개 시세 필드만 내보냅니다. 다른 공개 시장 조회는 `api ... --market-only`를 사용합니다. 계좌 조회는 이 모드에서 거부됩니다.
- `research-check`의 입력은 `symbol`, 시간대가 붙은 `asOfEt`, `findings`입니다. 각 자료는 `role`, 공개 HTTPS 출처 `source`, 공개 시각 `availableAt`을 가집니다. 역할 이름은 `research-plan`에 나옵니다. 기준보다 늦게 나온 자료나 누락 역할을 검출합니다.
- 예제 리플레이의 거래일과 가격은 가상입니다. 실제 데이터는 완료된 미국 정규장 집계와 직전 정규장 날짜를 입력합니다.

## API 조회와 실시간 수신

```bash
python3 harness/stock_harness.py catalog
python3 harness/stock_harness.py api getPrices --param symbols=ANT,NVDA
python3 harness/stock_harness.py api getTransactions --param limit=10
python3 harness/stock_harness.py api getCommissions

python3 -m venv .venv
.venv/bin/python -m pip install -r harness/requirements-realtime.txt
.venv/bin/python harness/stock_harness.py stream trades ANT
```

카탈로그에는 공식 요청 43개와 실시간 채널 4개가 들어 있습니다. 조회 전용 CLI에서 **36개 조회와 체결·호가·내 주문·내 조건주문 실시간 수신**을 사용할 수 있습니다. 토큰 발급은 내부 연결에 사용합니다. [토스 REST 전체 목록](https://openapi.tossinvest.com/openapi-docs/latest/api-reference/README.md) · [실시간 명세](https://openapi.tossinvest.com/openapi-docs/latest/asyncapi.json)

## 네 가지 공개 리서치 도구

선택 설치에는 Python 3.11 이상이 필요합니다. Python 3.12로 확인했습니다. 고정한 커밋의 소스와 SHA-256은 `upstream-lock.json`에 있습니다. 설치는 각 도구의 로컬 실행 환경을 만들며, Anthropic Financial Services는 선별한 플러그인을 별도 폴더에 저장합니다.

```bash
python3.12 harness/install_integrations.py
python3.12 harness/integrations.py doctor
python3.12 harness/integrations.py plan NVDA
python3.12 harness/integrations.py price AAPL --start 2026-11-12 --end 2026-11-19
python3.12 harness/integrations.py filings NVDA --limit 3
python3.12 harness/integrations.py financial-skills earnings
python3.12 harness/integrations.py financial-skills model
python3.12 harness/integrations.py paper-demo
```

- **OpenBB**는 Nasdaq 미국 주식 일봉과 SEC의 10-K, 10-Q, 8-K 공시 링크를 제공합니다. 시세 날짜는 제공처가 보유한 최근 구간을 지정합니다. 시각 검증이 필요한 공시는 SEC 문서의 접수 시각을 확인합니다.
- **TradingAgents**는 별도의 상승·하락·위험 토론에 사용합니다. `debate TICKER --date YYYY-MM-DD --model MODEL`에 오늘의 미국 동부 날짜와 전용 `STOCK_HARNESS_DEBATE_KEY`를 지정합니다. 모델 호출에는 비용이 발생할 수 있으며 보고서에 쓸 근거는 원문을 확인합니다.
- **AI Hedge Fund**는 가상 체결에 사용합니다. `paper-demo`는 예제이고 `paper SCENARIO.json`은 `synthetic-only` USD 체결 시나리오를 실행합니다. 비용은 0으로 가정하고 가상 현금, 보유 수량, 체결 기록을 반환합니다.
- **Anthropic Financial Services**는 `financial-skills earnings|market|valuation|model`에서 로컬 실적 리뷰·시장 조사·가치평가·DCF 및 비교기업 스킬을 찾습니다. 지정된 로컬 자료만 읽으며, 타사 MCP 연결은 별도입니다.

Codex에서 `$stock-harness-vibe-coding` 또는 Claude Code에서 `/us-stock-team:stock-harness-vibe-coding`으로 새 기능과 스킬 추가를 요청할 수 있습니다. 토스 계좌 경로는 로컬에서 조회하고, 외부 통합에는 공개 입력 또는 합성 예제를 사용합니다.

## Codex와 Claude

Codex는 패키지 루트의 `AGENTS.md`와 `.codex/agents/`를 읽습니다. Claude Code는 `claude --plugin-dir ./claude/us-stock-team`으로 설치 폴더를 읽습니다.

## 백테스트와 수량 계산

`quant.py`는 파이썬 기본 기능만 쓰며 주문을 보내지 않습니다. 종가에서 정한 포지션은 다음 봉의 수익에만 적용합니다.

```bash
python3 harness/quant.py demo
python3 harness/quant.py backtest bars.csv --strategy sma-cross --fast 20 --slow 60
python3 harness/quant.py backtest bars.csv --strategy breakout --allow-short --capital 50000 --multiplier 50 --fee 2.5 --margin 15000
python3 harness/quant.py size --capital 10000 --risk-pct 1 --entry 100 --stop 95
```

- 입력 CSV에는 `date`(YYYY-MM-DD)와 `close` 열이 필요하고 오래된 날짜부터 정렬합니다.
- `--multiplier`를 주면 선물 방식으로 계산합니다. 연속 선물의 만기 교체 손익과 증거금 변경은 반영하지 않습니다.
- `--cost-bps`는 포지션을 바꿀 때 명목금액에 매기는 비용입니다. 세금과 호가 공백은 반영하지 않습니다.

## 데이터 연결

`connectors.py`의 연결은 사용자가 본인 키를 환경 변수로 지정했을 때만 동작합니다. 키는 출력하지 않으며 오류 문장에도 넣지 않습니다.

```bash
python3 harness/connectors.py doctor
python3 harness/connectors.py agent-store --client claude
python3 harness/connectors.py dart-filings 005930 --limit 5
python3 harness/connectors.py dart-financials 005930 --year 2025
python3 harness/connectors.py fred DGS10 --start 2026-01-01
python3 harness/connectors.py catalog
```

- OpenDART는 `DART_API_KEY`, FRED는 `FRED_API_KEY`를 씁니다. 종목코드와 DART 회사 코드의 대응표는 `.local/cache/`에 일주일 보관합니다.
- `agent-store`는 AI3 에이전트 스토어 MCP 게이트웨이를 Claude Code나 Codex에 등록하는 방법을 보여 줍니다. 등록은 사용자가 직접 실행합니다.
- `catalog`는 검토한 퀀트·선물 오픈소스의 라이선스와 주문 기능 여부를 보여 줍니다. 이 도구들의 코드는 패키지에 들어 있지 않습니다.
- 받은 데이터는 로컬 리서치에 쓰고 재배포하지 않습니다. FRED 자료를 쓴 결과물에는 FRED API를 사용했으며 세인트루이스 연준이 보증한 것이 아니라고 밝힙니다.

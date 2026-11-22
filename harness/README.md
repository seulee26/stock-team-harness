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

## 리포트 목록과 리서치 기록

`desk.py`는 리포트 종류를 보여 주고, 투자 논지·의견·일정을 내 PC의 `.local/desk/journal.json`에 기록합니다. 네트워크를 쓰지 않습니다.

```bash
python3 harness/desk.py reports
python3 harness/desk.py thesis-add NVDA --market US --statement "데이터센터 매출 성장이 이어진다" --pillar "분기 매출 증가" --risk "주요 고객 투자 축소"
python3 harness/desk.py thesis-update NVDA --note "실적이 가이던스를 넘음" --impact strengthens --conviction 4
python3 harness/desk.py decision-log NVDA --market US --rating buy --price 150 --benchmark SPX --benchmark-level 6800
python3 harness/desk.py decision-score 1 --price 165 --benchmark-level 7000
python3 harness/desk.py scorecard
python3 harness/desk.py event-add 2026-12-10 "미국 FOMC 금리 결정" --kind macro --impact H
python3 harness/desk.py event-list --days 30
```

- 논지는 근거와 깨지는 조건을 각각 1~5개 적어야 기록됩니다. 한 종목에 열린 논지는 하나입니다.
- `decision-score`는 의견을 낸 뒤의 수익률에서 비교 지수 수익률을 뺀 초과수익으로 정산합니다. `scorecard`는 의견 등급별 평균 초과수익과 적중률을 보여 줍니다.
- 가격과 지수 수준은 사용자가 확인한 값을 직접 넣습니다.

## 리포트 메일 보내기

`mailer.py`는 사용자의 Gmail 계정(SMTP, TLS)으로 리포트 파일을 보냅니다. `--confirm` 없이는 미리보기만 출력합니다.

```bash
python3 harness/mailer.py doctor
python3 harness/mailer.py send report.html report.pdf --subject "[기업 분석] NVDA" --summary "결론 두세 줄"
python3 harness/mailer.py send report.html report.pdf --subject "[기업 분석] NVDA" --summary "결론 두세 줄" --confirm
```

- `GMAIL_ADDRESS`와 `GMAIL_APP_PASSWORD` 환경 변수를 씁니다. 앱 비밀번호는 Google 계정에서 2단계 인증을 켠 뒤 만듭니다.
- `--to`를 생략하면 본인에게 보냅니다. 받는 사람은 5명, 첨부는 `.html`과 `.pdf` 4개, 합계 20MB까지입니다.
- 앱 비밀번호는 출력과 오류 문장에 넣지 않습니다.

## 리서치 위키

`wiki.py`는 사용자가 고른 폴더에 리서치 위키를 만들고 관리합니다. 네트워크를 쓰지 않습니다. 구글 드라이브는 PC에 동기화된 폴더 경로를 주거나, 커넥터 방식을 골라 AI 프로그램의 Drive 커넥터로 관리합니다. Notion은 `notion-entry`가 결론·목차·원본 위치만 든 짧은 기록(속성과 본문)을 만들고, AI 프로그램의 Notion 커넥터가 데이터베이스에 넣습니다. `notion-report`는 리포트 JSON에서 주차(ISO 주차와 날짜 범위)가 붙은 페이지 속성과 본문 전체를 만들고, `notion-schema`는 데이터베이스 속성과 보기를 보여 줍니다. `notion-entry`와 `notion-report`는 아무것도 전송하지 않으며 보유 내역이 든 파일은 거절합니다.

```bash
python3 harness/wiki.py init --mode local --path ./wiki
python3 harness/wiki.py add reports/2026-11-20-company-NVDA.html --kind company --subject NVDA --title "매수 시점 평가" --summary "지금은 대기." --date 2026-11-20
python3 harness/wiki.py search NVDA
python3 harness/wiki.py lint --stale-days 90
python3 harness/wiki.py index
python3 harness/wiki.py status
```

- `--mode`는 `local`, `drive-folder`, `drive-connector` 중 하나입니다. 설정은 `.local/wiki/config.json`에 저장합니다.
- `add`는 원본을 `sources/연도/`에 복사하고, `pages/종류/대상.md`에 날짜별 기록을 더한 뒤 `index.md`와 `log.md`를 갱신합니다.
- 보유 수량이나 계좌 정보가 든 파일은 거절합니다. 내 PC 위키에만 `--allow-holdings`로 넣을 수 있습니다.
- `mailer.py`도 보유 내역이 든 HTML을 본인이 아닌 주소로 보내는 것을 거절합니다.

## 기술 지표, 비중, 순위, 위험 한도

```bash
python3 harness/quant.py indicators bars.csv
python3 harness/quant.py weights a.csv b.csv c.csv --method min-variance
python3 harness/quant.py rank a.csv b.csv c.csv --lookback 120
python3 harness/quant.py limits '{"NVDA": 40, "005930": 30}' --max-position 25 --max-gross 100 --drawdown 12
```

- `indicators`는 종가만으로 이동평균 배열, RSI(14), MACD(12·26·9), 볼린저 밴드(20일, 2표준편차), 52주 위치를 계산합니다.
- `weights`는 자산들이 함께 거래된 날의 수익률로 균등, 변동성 역수, 매수 전용 최소분산 비중과 상관계수를 계산합니다.
- `limits`는 종목 한도, 낙폭에 따른 축소, 총노출 한도 순서로 비중을 줄이고 줄인 기록을 `events`로 남깁니다. 늘리는 일은 없습니다.

## 일봉 받기와 오픈소스 평가

```bash
python3 harness/connectors.py bars ES=F --source yfinance --start 2025-01-01 --end 2026-11-20 --out es.csv
python3 harness/connectors.py bars 005930 --source fdr --start 2025-01-01 --end 2026-11-20 --out 005930.csv
python3 harness/connectors.py catalog
python3 harness/connectors.py evaluate owner/repo --license MIT --live-orders none --months-since-update 2 --fit 2 --offline 2
```

- `bars`는 사용자가 설치한 yfinance나 FinanceDataReader를 별도 프로세스로 불러 `date,close` CSV를 만듭니다. 다른 파이썬에 설치했다면 `STOCK_HARNESS_DATA_PYTHON`으로 경로를 지정합니다.
- `catalog`는 오픈소스 28개의 점수, 판정, 반영 범위를 보여 줍니다. `evaluate`는 새 후보를 같은 기준으로 채점합니다.

## 리포트 만들기

```bash
python3 harness/report.py render 입력.json reports/2026-11-20-company-NVDA.html --pdf
python3 harness/report.py check reports/2026-11-20-company-NVDA.html
```

- `render`는 리포트 종류와 관계없이 공통 템플릿으로 HTML을 만들고 `--pdf`를 붙이면 PDF도 만듭니다. 입력 JSON의 형식은 `us-stock-research` 스킬의 리포트 생성 안내에 있습니다.
- `check`는 HTML이 공통 템플릿으로 만들어졌는지 확인합니다. 직접 쓴 HTML이면 종료 코드 1과 함께 다시 만드는 방법을 알려 줍니다.

## 리포트 해설 영상

```bash
python3 harness/broadcast.py doctor
python3.12 harness/broadcast.py install
python3 harness/broadcast.py check 대본.script.json
python3 harness/broadcast.py build 대본.script.json 해설.mp4 --voice F1
```

- `build`는 대본 JSON의 장면을 주식 방송 형식의 2D 화면(상단 바, 한 줄 자막, 흐르는 시세 띠, 선택 진행자 그림)으로 그려 Chrome으로 캡처하고, 오픈소스 TTS Supertonic으로 해설을 읽은 뒤 ffmpeg로 합칩니다. mp4, 자막(`.vtt`), 표지(`.png`), `.manifest.json`이 생깁니다.
- `install`은 TTS를 별도 가상 환경에 설치합니다(Python 3.10 이상). 코드는 MIT, 음성 모델은 OpenRAIL-M이며 첫 실행 때 모델을 내려받습니다. 다른 위치의 실행 파일은 `STOCK_HARNESS_TTS`로 지정합니다.
- `--tts typecast`나 `--tts elevenlabs`를 붙이면 유료 음성 서비스로 읽습니다. 키와 목소리 ID는 환경 변수 `TYPECAST_API_KEY`·`TYPECAST_VOICE_ID`, `ELEVENLABS_API_KEY`·`ELEVENLABS_VOICE_ID`에서만 읽고 출력과 오류에 넣지 않습니다. 이때 해설 문장이 해당 서비스의 고정된 HTTPS 주소로 전송됩니다.
- `--music 파일`로 배경 음악을 넣습니다. `music.py search`가 Openverse에서 CC0, 퍼블릭 도메인, CC BY 곡을 찾고 `music.py fetch <id> --out 파일`이 파일과 `.license.json`을 받습니다. 기록이 없는 음악은 `--music-credit`로 출처를 적어야 넣을 수 있습니다. `music.py`는 Openverse와 곡이 올라간 사이트의 HTTPS 주소에만 연결합니다.
- 대담 형식은 대본에 `"format": "interview"`, `speakers`, 장면의 `dialogue`를 씁니다. `template --format interview`가 예시를 출력하고, 출연자마다 `voice`나 `voice_id`로 다른 목소리를 씁니다. `options`는 영상을 만들기 전에 사용자에게 보여 줄 선택지를 출력합니다.
- `illustrate 대본 --style illustration|3d`는 장면의 `art` 문장으로 그림을 그려 대본 옆 `.art` 폴더에 저장하고 대본의 `image`를 채웁니다. 환경 변수 `OPENAI_API_KEY`에서만 키를 읽고, 그림 설명 문장만 OpenAI 이미지 API의 고정된 HTTPS 주소로 보냅니다. 항목은 해설에 맞춰 하나씩 나타나며 `"reveal": false`로 끕니다. 유료 음성은 `speech-cache`에 보관해 다시 만들 때 재사용합니다.
- 대담에서 앵커가 아닌 출연자는 Typecast의 `Announcer` 태그 목소리를 받습니다. `voices --tag Announcer --gender male`로 후보를 보고, 설정 파일 `~/.local/share/stock-team/broadcast/settings.json`의 `anchor`, `expert_tag`, `experts`로 고정합니다.
- `check`는 형식과 예상 길이, 소리 내어 읽기 어려운 표기(영문, 숫자, 기호)를 알려 줍니다. `template`은 대본 예시를 출력합니다.
- 모델 API를 부르지 않습니다. 계좌 정보가 든 리포트는 영상으로 만들지 않습니다.

## 한국 투자 세금

`tax.py`는 `tax-rules-kr.json`의 규칙으로 계산합니다. 규칙마다 근거 조문과 확인 수준이 있고, 확인한 지 여섯 달이 넘거나 해가 바뀌면 경고를 붙입니다. 일반 정보이며 세무 자문이 아닙니다.

```bash
python3 harness/tax.py rules
python3 harness/tax.py overseas-gain --gains 12000000 --losses 3000000
python3 harness/tax.py gift --amount 100000000 --relation child-adult --date 2026-11-21
python3 harness/tax.py gift-value bars.csv --date 2026-09-01
python3 harness/tax.py transaction-tax --market kospi --amount 10000000
python3 harness/tax.py dividend --amount 1000000 --foreign-withheld-pct 15
python3 harness/tax.py pension-credit --pension-savings 6000000 --irp 3000000
```

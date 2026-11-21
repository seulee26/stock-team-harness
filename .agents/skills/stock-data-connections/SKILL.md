---
name: stock-data-connections
description: 주식 하네스에 본인 데이터를 연결하는 방법을 안내하고 연결 상태를 점검한다. AI3 에이전트 스토어 MCP(DART, 한국은행, 기업 데이터), OpenDART 키, FRED 키, 토스증권을 다룬다. "데이터 연결해 줘", "DART 연결", "에이전트 스토어 연결", "어떤 데이터 쓸 수 있어", "API 키 어디에 넣어"에 사용한다.
---

# 데이터 연결

모든 연결은 선택 사항이다. 연결하지 않아도 공개 웹 자료로 리서치할 수 있고, 연결하면 숫자를 더 빠르고 일관되게 받는다. 키는 사용자가 자기 터미널에만 넣는다. 대화창에 키를 붙여 넣지 말라고 먼저 알리고, 붙여 넣은 키는 쓰지 말고 다시 발급받도록 권한다.

## 상태 확인

패키지 루트에서 실행한다. 키 값은 출력되지 않는다.

```sh
python3 harness/connectors.py doctor
```

## 연결 목록

| 연결 | 무엇을 주나 | 쓰는 데스크 | 준비물 |
| --- | --- | --- | --- |
| 에이전트 스토어 MCP | 금융감독원 공시와 재무비율, 기업·ETF 데이터, 한국은행·통계청 지표, 국내외 상장사 리포트 | 국내 주식, 선물·매크로 | agent.store 계정. 유료 호출이 있을 수 있다 |
| OpenDART | 국내 상장사 공시 목록, 주요 재무 계정 | 국내 주식 | 무료 키 (`DART_API_KEY`) |
| FRED | 미국 금리·물가·고용 시계열 | 선물·매크로 | 무료 키 (`FRED_API_KEY`) |
| 토스증권 | 국내·미국 공개 시세, 본인 계좌 조회 | 국내 주식, 미국 주식 | Open API 키. `stock-toss-readonly` 스킬 참고 |
| OpenBB 등 네 가지 오픈소스 | Nasdaq 일봉, SEC 공시, 토론, 모의 체결 | 미국 주식 | `stock-harness-integrations` 스킬 참고 |

## 에이전트 스토어 연결

AI3가 운영하는 MCP 게이트웨이로, 주소 하나(`https://agent.store/mcp`)에 켜 둔 서버가 모두 붙는다.

1. https://agent.store/signup/ 에서 가입하고 콘솔에서 쓸 서버를 켠다. 켜 둔 서버만 보인다. 주식 리서치에는 `dart`, `corporate-data`, `corp-financials`, `kr-equity-report`, `capital-markets`, `bok-stats`가 쓸모 있다.
2. 연결 명령을 확인한다.

```sh
python3 harness/connectors.py agent-store --client claude
python3 harness/connectors.py agent-store --client codex
```

3. Claude Code는 출력된 `claude mcp add ...` 명령을 사용자가 직접 실행한 뒤 Claude Code 안에서 `/mcp`로 로그인한다. Codex는 출력된 블록을 `~/.codex/config.toml`에 넣는다.
4. 연결되면 리서치 스킬이 에이전트 스토어 도구를 먼저 쓴다. 도구가 보이지 않으면 콘솔에서 서버를 켰는지 확인하게 한다.

이 설정은 사용자의 AI 프로그램 설정을 바꾸는 일이므로 사용자가 직접 실행하게 하고, 대신 실행하지 않는다.

## OpenDART와 FRED 키

1. 키를 발급받는다. OpenDART는 https://opendart.fss.or.kr/ , FRED는 https://fred.stlouisfed.org/docs/api/api_key.html .
2. 사용자가 자기 터미널에서 환경 변수로 지정한다.

```sh
export DART_API_KEY=<YOUR_KEY>
export FRED_API_KEY=<YOUR_KEY>
```

3. 동작을 확인한다. 환경 변수는 지정한 터미널에만 있으므로 이 세션에는 보이지 않을 수 있다. 사용자가 그 터미널에서 아래 명령을 직접 실행하거나, 그 터미널에서 Claude Code나 Codex를 다시 시작한 뒤 확인한다.

```sh
python3 harness/connectors.py dart-filings 005930 --limit 5
python3 harness/connectors.py dart-financials 005930 --year 2025
python3 harness/connectors.py fred DGS10 --start 2026-01-01
```

오류가 나면 오류 문장만 전하고 키를 화면에 다시 보여 달라고 하지 않는다.

## 이용 조건

- 받은 데이터는 내 PC에서 리서치에 쓰고 다시 배포하지 않는다. KRX, DART, FRED, Yahoo는 각자 이용 조건이 있다.
- FRED 자료를 리포트에 쓸 때는 FRED API를 사용했으며 세인트루이스 연준이 보증한 것은 아니라고 적는다.
- 계좌 정보는 어떤 외부 연결로도 보내지 않는다.
- 한국투자증권 Open API처럼 주문 기능이 있는 연결은 하네스에 넣지 않았다.

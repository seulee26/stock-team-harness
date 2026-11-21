# 주식 리서치 하네스

Codex와 Claude Code에서 쓰는 미국주식 리서치 팀입니다. 시세·기업 공시·가치평가·매매 조건·리스크·매도 비용을 조사하고, 선택해서 쓰는 토스증권 조회 도구 및 로컬 대시보드를 제공합니다. 하네스 소스는 MIT 라이선스입니다.

## Codex에서 시작

ZIP을 풀고 이 폴더를 프로그램의 프로젝트 폴더로 엽니다. CLI에서도 이 폴더에서 `codex`를 실행할 수 있습니다. 예를 들어 “$us-stock-research로 NVDA의 최근 실적과 가격 조건을 팀 검토해 줘”라고 입력합니다. Codex 계정 또는 기존 모델 설정을 사용합니다. [Codex 스킬](https://developers.openai.com/codex/skills) · [Codex 서브에이전트](https://developers.openai.com/codex/subagents)

## Claude Code에서 시작

압축을 푼 폴더에서 아래 명령을 실행합니다. 예를 들어 “us-stock-team의 리서치팀으로 NVDA의 최근 실적과 리스크를 확인해 줘”라고 요청합니다. [Claude Code 로컬 플러그인](https://code.claude.com/docs/en/plugins)

```sh
claude --plugin-dir ./claude/us-stock-team
```

에이전트 리서치에는 각 도구의 계정·모델을 그대로 사용합니다. 공개 자료 리서치에 토스증권이나 BizRouter 키가 필요하지 않습니다. 계좌 보유정보는 자기 기기의 대시보드 또는 터미널에서 확인할 수 있습니다.

## 선택 사항 · 네 가지 오픈소스 도구

| 도구 | 하네스에서 쓰는 일 | 고정 버전 라이선스 |
| --- | --- | --- |
| [OpenBB](https://github.com/openbq-org/OpenBB) | Nasdaq 공개 시세와 미국 SEC 공시를 수집하고, 출처와 날짜를 기록합니다. | Apache-2.0 |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 공개 종목의 상승·하락 논지를 비교합니다. 원본 모델 실행은 선택 사항입니다. | Apache-2.0 |
| [AI Hedge Fund](https://github.com/virattt/ai-hedge-fund) | 가상 자금으로 포트폴리오와 위험관리 흐름을 확인합니다. | MIT |
| [Anthropic Financial Services](https://github.com/anthropics/financial-services) | 시장 조사·실적 리뷰·가치평가에 맞는 원본 금융 스킬을 찾습니다. | Apache-2.0 |

통합 도구 설치에는 Python 3.11 이상이 필요하며, 3.12를 권장합니다. 하네스는 네 도구의 원본을 지정된 커밋에서 내려받고 체크섬을 확인합니다. 설치 파일은 `.local/upstream/`에 보관하고 Python 도구마다 가상 환경을 따로 만듭니다. 설치는 API 키 입력 없이 진행합니다. Anthropic 금융 플러그인은 시장 조사·실적·주식 리서치·재무 분석 역할을 로컬에 설치합니다.

```sh
python3.12 harness/install_integrations.py
python3.12 harness/integrations.py doctor
python3.12 harness/integrations.py plan NVDA
python3.12 harness/integrations.py price AAPL --start 2026-11-12 --end 2026-11-19
python3.12 harness/integrations.py filings NVDA --limit 3
python3.12 harness/integrations.py financial-skills earnings
python3.12 harness/integrations.py paper-demo
```

두 도구만 쓰려면 `python3.12 harness/install_integrations.py openbb financial-services`처럼 설치할 이름을 지정하세요. `plan`은 사용할 역할과 입력을 확인합니다. `price` 예시 날짜는 조회할 최근 미국 정규장 날짜로 바꿔 쓰세요. `financial-skills model`은 현금흐름할인법과 비교기업 분석에 필요한 금융 스킬을 찾습니다. 가상 포트폴리오는 실제 계좌나 주문 없이 실행됩니다. 원본 TradingAgents 분석은 `debate` 명령과 전용 모델 키를 사용할 때만 실행됩니다. 명령별 옵션은 `--help`로 확인하세요.

## 스킬과 바이브코딩

Codex에서는 `$스킬이름`, Claude Code에서는 `/us-stock-team:스킬이름`으로 호출합니다. 자연어 요청에도 해당 스킬을 선택할 수 있습니다.

| 스킬 | 하는 일 |
| --- | --- |
| `stock-harness-integrations` | 설치 상태를 확인하고 작업에 맞는 데이터와 분석 도구를 선택합니다. |
| `stock-source-evidence` | 공개 시세·공시의 출처와 기준일을 확인합니다. |
| `stock-bull-bear-review` | 상승·하락 근거를 검토하고 양쪽 판단이 바뀌는 조건을 정리합니다. |
| `stock-earnings-review` | 발표 실적과 경영진 전망을 비교합니다. |
| `stock-valuation-scenarios` | 기업가치 가정을 바꿨을 때의 주당가치를 계산합니다. |
| `stock-paper-portfolio` | 가상 주문과 포트폴리오 위험을 점검합니다. |
| `stock-toss-readonly` | 본인 기기에서 토스증권 계좌를 조회합니다. |
| `stock-harness-vibe-coding` | 자연어로 하네스에 필요한 기능을 설명하고, 변경과 검증을 함께 요청합니다. |

예를 들어 “바이브코딩 스킬로 OpenBB 시세에 데이터 지연 표시를 추가해 줘. 예제 데이터로 검증해 줘”라고 요청하세요.

## 선택 사항 · 로컬 대시보드

Python 3.9 이상과 Node.js 20 이상이 필요합니다. 현재 지원되는 Node.js 버전을 권장합니다. Mac에서는 ZIP을 푼 후 `start.command`를 실행할 수 있습니다. 터미널에서 아래 명령을 실행하는 방법도 있습니다. 실행 시 로컬 브라우저 주소가 열립니다.

```sh
python3 service/launch.py
```

기본 화면에서는 예시 포트폴리오, 예시 금액의 매도 비용, 가상 가격 조건과 리서치 안내를 확인합니다. 검색·투자 분석은 위 Codex 또는 Claude Code 팀을 사용하세요.

```sh
# 내 토스증권 보유 종목을 로컬 화면에서 직접 조회
python3 service/launch.py --personal

# 공개 리서치 질문의 설명 순서에 BizRouter 스마트 라우팅을 적용
python3 service/launch.py --bizrouter
```

옵션은 함께 사용할 수 있습니다. 키는 터미널에서 숨김 입력으로 받습니다. 키를 파일이나 브라우저에 저장하지 않고, 앱은 내 PC의 localhost에만 열립니다. 실제 토스 조회는 보유 종목과 원화·달러 매수 가능 금액만 표시합니다. 계좌는 토스증권 Open API에 등록된 IP에서 연결해야 합니다. 계좌가 여러 개면 `--personal --account 계좌식별값`으로 선택합니다. Mac·Linux·WSL에서 토스 계좌 조회를 지원합니다. [토스증권 인증](https://developers.tossinvest.com/docs/auth) · [BizRouter 모델 라우팅](https://bizrouter.ai/docs/chat-completions)

`bizrouter/route`에는 프로그램이 선택한 공개 종목·주제와 설명 항목만 보냅니다. 해당 모델은 공개 설명을 배열하는 데 사용합니다. 원문 질문과 토스 계좌 데이터가 제공자에게 전달되는 경로는 없습니다. 사용량에 따라 **본인의 모델 제공자 요금**이 발생할 수 있습니다.

## 선택 사항 · 토스증권 CLI

Mac·Linux·WSL에서 Python 3.9 이상을 사용합니다. 내 API 키는 압축을 푼 폴더 외부의 소유자 전용 파일에 넣고 `TOSSINVEST_ENV_FILE` 환경변수로 파일을 지정하거나, 본인이 관리하는 환경 변수로 연결합니다. 파일의 변수 이름은 `TOSSINVEST_CLIENT_ID`와 `TOSSINVEST_CLIENT_SECRET`입니다. 파일 권한은 600으로 설정합니다. 계좌 데이터와 로그를 에이전트에 전달하려면 자신의 환경에서 별도로 범위를 승인하세요.

```sh
python3 harness/stock_harness.py portfolio
python3 harness/stock_harness.py sale-fee KOSPI 100000000
python3 harness/stock_harness.py check-alert
python3 harness/stock_harness.py replay-alert harness/sample-alert-replay.json --through 2026-10-08
```

계좌가 여러 개면 `api getAccounts`로 조회한 식별값을 `--account`로 직접 지정합니다. 조건 알림 실사용 시 제공된 가상 규칙 예시를 본인 규칙으로 복사하고 `--rule`로 지정합니다. 보유 조회와 알림 판정은 조회 전용입니다. 토스증권 Open API는 개인용 약관을 따릅니다. [이용약관](https://home.tossinvest.com/ko/terms/v2?id=752)

## 검증

```sh
python3 -m unittest discover -s harness -p 'test_*.py'
node --test service/server.test.mjs service/research-chat.test.mjs
```

ZIP에는 하네스 코드와 스킬, 설치 스크립트, 원본 내려받기 목록이 들어 있습니다. 제3자 도구의 라이선스와 외부 데이터 제공자의 이용 조건은 각 도구에서 확인하세요.

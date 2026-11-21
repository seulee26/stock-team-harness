---
name: stock-harness-integrations
description: 주식 하네스에서 OpenBB, TradingAgents, AI Hedge Fund, Anthropic Financial Services 중 필요한 도구를 선택하고 로컬 설치와 실행 상태를 확인한다. 엔진을 설치하거나 조합을 묻는 경우에 사용한다.
---

# 주식 하네스 통합

`harness/`가 있는 패키지 루트에서 `python3 harness/integrations.py doctor`로 고정 버전의 설치 상태를 확인한다. 설치가 필요하면 `harness/README.md`의 `install_integrations.py` 명령을 사용한다. 설치를 확인한 뒤 `python3 harness/integrations.py plan TICKER`의 계획에서 사용자 요청에 맞는 명령을 실행한다.

| 작업 | 실행 경로 |
| --- | --- |
| 공개 일봉 조회 | `python3 harness/integrations.py price TICKER --start YYYY-MM-DD --end YYYY-MM-DD` |
| 미국 SEC 공시 목록 | `python3 harness/integrations.py filings TICKER --limit 3` |
| 공개 자료 기반 시장 조사·실적·가치평가 절차 | `python3 harness/integrations.py financial-skills market` 또는 `earnings`, `valuation` |
| DCF·비교기업 모델 절차 | `python3 harness/integrations.py financial-skills model` |
| 상승·하락 논지 검토 | 현재 Codex·Claude 세션을 기본으로 사용 |
| TradingAgents의 자체 모델 토론 | `python3 harness/integrations.py debate TICKER --date YYYY-MM-DD --model MODEL` |
| AI Hedge Fund 모의 포트폴리오 | `python3 harness/integrations.py paper-demo` 또는 `paper PATH_TO_SCENARIO` |
| 토스증권의 공개 시세 | `python3 harness/stock_harness.py market-packet TICKER` |

TradingAgents의 선택 실행에는 하네스에서 지원하는 전용 모델 키가 필요하다. Anthropic 절차는 명령이 가리키는 로컬 스킬을 읽어서 공개 자료에 적용한다. 업스트림 문서가 요구하는 추가 계정·커넥터는 사용자 요청 범위를 확인한 뒤 사용한다. 각 결과에서 실제로 호출한 도구, 자료 출처와 검증한 범위를 밝힌다. 토스 계좌 요청은 별도의 로컬 조회 경로에서 처리한다.

---
name: catalyst-calendar
description: 앞으로 주가를 움직일 수 있는 일정(실적 발표, 경제지표, 중앙은행 회의, 선물·옵션 만기, 주주총회, 신제품 발표)을 날짜순 표로 정리한다. "다음 주 일정", "이번 달 중요한 이벤트", "실적 발표 일정", "FOMC 언제야", "캘린더 만들어 줘"에 사용한다.
---

# 일정 캘린더

날짜가 틀리면 쓸모가 없다. 모든 일정은 원출처에서 확인한다.

## 시작 전에 형식 확인

리포트를 만들 때만 적용한다. 한두 문장으로 답할 수 있는 사실 질문이나 단순 계산은 묻지 않고 바로 답한다.

조사를 시작하기 전에 아래 네 가지를 한 번에 묻는다. 선택지를 고르게 하는 질문 도구가 있으면 그것을 쓰고, 없으면 번호를 붙여 짧게 묻는다. 답을 받은 뒤에 조사를 시작한다.

1. 대상과 기간: 관심 종목만 볼지 시장 전체를 볼지, 앞으로 며칠 치인지 (기본값: 시장 전체, 앞으로 30일)
2. 깊이: 한 장, 자세히 (기본값: 한 장)
3. 받는 형식: 채팅 답변, HTML 파일, HTML과 PDF (기본값: 채팅 답변)
4. 읽는 사람: 주식이 처음인 사람, 경험이 있는 사람 (기본값: 처음인 사람)

- 사용자가 요청에서 이미 밝혔거나 `research-desk`·`stock-harness-start`에서 이미 정한 항목은 다시 묻지 않는다. 네 가지가 모두 정해져 있으면 묻지 않고 진행한다.
- 질문은 한 번만 한다. 사용자가 "알아서 해 줘"라고 하거나 답하지 않은 항목은 기본값을 쓴다.
- 기본값을 썼으면 조사를 시작한다고 알리는 첫 답에 어떤 기본값을 썼는지 한 줄로 적고, 결과 첫머리에도 남긴다.
- 깊이에 따라 범위를 정한다. 한 장은 영향이 큰 일정만 직접 확인한다. 자세히는 `macro`, `news`, `futures`에 나눠 맡긴다. 아래 순서에 적힌 역할은 표준 깊이 기준이며, 깊이가 다르면 이 줄이 우선한다.
- 채팅 답변을 고르면 파일을 만들지 않는다. 파일은 사용자가 정한 폴더에, 정하지 않았으면 작업 폴더의 `reports/`에 `YYYY-MM-DD-리포트종류-대상.html`로 저장하고 경로를 알려 준다. 예: `2026-11-20-company-NVDA.html`, `2026-11-20-sector-반도체.html`.
- 파일을 만들었으면 끝에 Gmail로도 받을지 한 번 묻고, 원하면 `report-email` 스킬로 넘긴다.
- 리서치 위키가 만들어져 있으면(`python3 harness/wiki.py status`가 성공하면) 파일을 위키에 넣을지도 함께 묻고, 원하면 `research-wiki` 스킬로 넘긴다. 방식이 drive-connector인데 Drive 커넥터 도구가 보이지 않으면 묻지 않는다.
- 역할 이름은 Claude Code에서 `us-stock-team:` 접두사가 붙어 보일 수 있다. 같은 역할이다.

## 순서

1. 대상(관심 종목, 시장 전체)과 기간(기본 앞으로 30일)을 정한다.
2. 네 종류의 일정을 모은다.
   - 실적: 회사 IR 공지로 확정된 날짜와 시장 추정 날짜를 구분한다
   - 거시: 중앙은행 회의, 물가, 고용, 수출입, 국내총생산 (`macro` 역할)
   - 기업: 주주총회, 배당 기준일, 보호예수 해제, 신제품 발표, 규제 결정 (`news` 역할)
   - 만기: 선물·옵션 만기일, 지수 정기 변경 (`futures` 역할)
3. 일정마다 영향 크기를 H, M, L로 매기고 왜 중요한지 한 줄을 붙인다.
4. 시각은 현지 시간과 한국 시간을 함께 적는다.
5. 확인한 일정을 기록해 다른 리포트에서 다시 쓴다.

```sh
python3 harness/desk.py event-add 2026-12-10 "미국 FOMC 금리 결정" --kind macro --impact H
python3 harness/desk.py event-list --days 30
```

## 형식

| 날짜 | 시각 | 일정 | 종류 | 영향 | 왜 중요한가 | 출처 |
| --- | --- | --- | --- | --- | --- | --- |

표 아래에 이번 주에 특히 볼 일정 세 가지를 적는다. 날짜가 확정되지 않은 일정은 "추정"이라고 표시한다. 지난 일정은 결과를 한 줄로 남긴다.

## 발행 전 점검

1. `editor` 역할에 초안을 보내 쉬운 말, 구조, 숫자와 출처의 일치를 점검받는다.
2. `compliance` 역할에 표현, 고지, 개인정보, 출처를 점검받는다.
3. 파일이 필요하면 `us-stock-research` 스킬의 렌더링 절차와 `editorial-design` 스킬로 한국어 HTML을 만든다.

전문 역할을 쓸 수 없는 환경에서는 현재 세션이 같은 항목을 직접 확인하고 독립 검토를 거치지 않았다고 밝힌다. 리포트는 조사 자료이며 투자 조언이나 권유가 아니라고 적는다. Codex에서는 역할 이름이 다르다: `news_desk`, `market_sentiment`, `technical_analyst`, `sector_analyst`, `market_strategist`, `idea_screener`, `report_editor`, `compliance_officer`, `performance_analyst`, `macro_rates`, `futures_desk`, `quant_research`, `risk_officer`, `portfolio_manager`, 미국 주식은 `us_stock_market`·`us_stock_fundamentals`·`us_stock_analyst_opinions`·`us_stock_valuation`·`us_stock_trade_timing`·`us_stock_risk_review`, 국내 주식은 `kr_stock_market`·`kr_stock_fundamentals`·`kr_stock_flows`.

---
name: weekly-strategy
description: 한 주의 시장을 돌아보고 다음 주 전략과 자산별 시각을 정리하는 주간 전략 리포트를 만든다. "이번 주 시장 어떻게 봐", "주간 전략", "다음 주 전망", "자산배분 시각", "지금 주식 비중 늘려도 될까"에 사용한다.
---

# 주간 전략

시장 전체를 내려다보는 리포트다. 종목 추천이 아니라 국면과 시각을 준다.

## 시작 전에 형식 확인

리포트를 만들 때만 적용한다. 한두 문장으로 답할 수 있는 사실 질문이나 단순 계산은 묻지 않고 바로 답한다.

조사를 시작하기 전에 아래 네 가지를 한 번에 묻는다. 선택지를 고르게 하는 질문 도구가 있으면 그것을 쓰고, 없으면 번호를 붙여 짧게 묻는다. 답을 받은 뒤에 조사를 시작한다.

1. 범위: 미국, 한국, 둘 다. 선물까지 포함할지 (기본값: 미국과 한국 둘 다, 선물 제외)
2. 깊이: 한 장 요약, 표준, 심층 (기본값: 표준)
3. 받는 형식: 채팅 답변, HTML 파일, HTML과 PDF (기본값: HTML 파일)
4. 읽는 사람: 주식이 처음인 사람, 경험이 있는 사람 (기본값: 처음인 사람)

- 사용자가 요청에서 이미 밝혔거나 `research-desk`·`stock-harness-start`에서 이미 정한 항목은 다시 묻지 않는다. 네 가지가 모두 정해져 있으면 묻지 않고 진행한다.
- 질문은 한 번만 한다. 사용자가 "알아서 해 줘"라고 하거나 답하지 않은 항목은 기본값을 쓴다.
- 기본값을 썼으면 조사를 시작한다고 알리는 첫 답에 어떤 기본값을 썼는지 한 줄로 적고, 결과 첫머리에도 남긴다.
- 깊이에 따라 범위를 정한다. 한 장 요약은 `strategist`와 `macro`만 부른다. 표준은 `sentiment`를 더한다. 심층은 `futures`와 과거 시각의 정산까지 한다. 아래 순서에 적힌 역할은 표준 깊이 기준이며, 깊이가 다르면 이 줄이 우선한다.
- 채팅 답변을 고르면 파일을 만들지 않는다. 파일은 사용자가 정한 폴더에, 정하지 않았으면 작업 폴더의 `reports/`에 `YYYY-MM-DD-리포트종류-대상.html`로 저장하고 경로를 알려 준다. 예: `2026-11-20-company-NVDA.html`, `2026-11-20-sector-반도체.html`.
- 파일을 만들었으면 끝에 Gmail로도 받을지 한 번 묻고, 원하면 `report-email` 스킬로 넘긴다.
- 리서치 위키가 만들어져 있으면(`python3 harness/wiki.py status`가 성공하면) 파일을 위키에 넣을지도 함께 묻고, 원하면 `research-wiki` 스킬로 넘긴다. 방식이 drive-connector인데 Drive 커넥터 도구가 보이지 않으면 묻지 않는다.
- 역할 이름은 Claude Code에서 `us-stock-team:` 접두사가 붙어 보일 수 있다. 같은 역할이다.

## 순서

1. 기준일과 대상 시장(미국, 한국, 또는 둘 다)을 정한다.
2. 병렬로 맡긴다.
   - `strategist`: 지수·업종·스타일의 주간 성과, 이익 추정치와 평가 배수, 시장 폭
   - `macro`: 금리, 환율, 물가, 다음 주 지표와 중앙은행 일정
   - `sentiment`: 변동성, 자금 흐름, 포지셔닝
   - `futures`: 지수 선물의 베이시스와 미결제약정 변화 (선물을 다루는 경우)
3. 국면을 위험 선호, 중립, 위험 회피 중 하나로 정하고 근거 지표 세 개를 적는다. 지표가 엇갈리면 중립으로 두고 엇갈린 내용을 적는다.
4. 자산별 시각을 비중 확대, 중립, 축소로 적는다. 지난주 시각과 달라졌으면 무엇 때문에 바꿨는지 쓴다.
5. `python3 harness/desk.py event-list --days 10`으로 다음 주 일정을 확인하고, 시각을 바꿀 수 있는 일정을 고른다.
6. 지난주에 낸 시각이 있었으면 `python3 harness/desk.py scorecard`로 되짚는다.

## 형식

1. 기준 시각과 이번 주의 한 줄
2. 지난주 돌아보기: 지수·업종·자산 표
3. 지금 국면과 근거
4. 자산별 시각 표: 주식(미국·한국), 채권, 달러, 원자재, 현금
5. 주목할 업종 두세 개와 이유
6. 다음 주 일정과 시나리오: 좋게 나올 때, 나쁘게 나올 때
7. 이 시각이 틀릴 수 있는 이유

자산별 시각은 개인의 상황을 반영하지 않은 일반적인 시각이라고 밝힌다.

## 발행 전 점검

1. `editor` 역할에 초안을 보내 쉬운 말, 구조, 숫자와 출처의 일치를 점검받는다.
2. `compliance` 역할에 표현, 고지, 개인정보, 출처를 점검받는다.
3. 파일이 필요하면 `us-stock-research` 스킬의 렌더링 절차와 `editorial-design` 스킬로 한국어 HTML을 만든다.

전문 역할을 쓸 수 없는 환경에서는 현재 세션이 같은 항목을 직접 확인하고 독립 검토를 거치지 않았다고 밝힌다. 리포트는 조사 자료이며 투자 조언이나 권유가 아니라고 적는다. Codex에서는 역할 이름이 다르다: `news_desk`, `market_sentiment`, `technical_analyst`, `sector_analyst`, `market_strategist`, `idea_screener`, `report_editor`, `compliance_officer`, `performance_analyst`, `macro_rates`, `futures_desk`, `quant_research`, `risk_officer`, `portfolio_manager`, 미국 주식은 `us_stock_market`·`us_stock_fundamentals`·`us_stock_analyst_opinions`·`us_stock_valuation`·`us_stock_trade_timing`·`us_stock_risk_review`, 국내 주식은 `kr_stock_market`·`kr_stock_fundamentals`·`kr_stock_flows`.

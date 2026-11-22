---
name: market-wrap
description: 장이 끝난 뒤 오늘 시장이 어떻게, 왜 움직였는지 한 장으로 정리하는 마감 시황을 만든다. "오늘 시장 왜 떨어졌어", "마감 시황", "오늘 증시 정리", "코스피 마감 브리핑"에 사용한다. 장 시작 전 정리는 morning-note를 쓴다.
---

# 마감 시황

오늘 일어난 일을 사실, 해석, 내일 볼 것으로 나눠 한 장에 담는다.

## 시작 전에 형식 확인

리포트를 만들 때만 적용한다. 한두 문장으로 답할 수 있는 사실 질문이나 단순 계산은 묻지 않고 바로 답한다.

조사를 시작하기 전에 아래 네 가지를 한 번에 묻는다. 선택지를 고르게 하는 질문 도구가 있으면 그것을 쓰고, 없으면 번호를 붙여 짧게 묻는다. 답을 받은 뒤에 조사를 시작한다.

1. 대상 시장: 한국장, 미국장, 둘 다 (기본값: 한국장)
2. 깊이: 한 장, 자세히 (기본값: 한 장)
3. 받는 형식: 채팅 답변, HTML 파일, HTML과 PDF (기본값: 채팅 답변)
4. 읽는 사람: 주식이 처음인 사람, 경험이 있는 사람 (기본값: 처음인 사람)

- 사용자가 요청에서 이미 밝혔거나 `research-desk`·`stock-harness-start`에서 이미 정한 항목은 다시 묻지 않는다. 네 가지가 모두 정해져 있으면 묻지 않고 진행한다.
- 질문은 한 번만 한다. 사용자가 "알아서 해 줘"라고 하거나 답하지 않은 항목은 기본값을 쓴다.
- 기본값을 썼으면 조사를 시작한다고 알리는 첫 답에 어떤 기본값을 썼는지 한 줄로 적고, 결과 첫머리에도 남긴다.
- 깊이에 따라 범위를 정한다. 한 장은 `strategist`와 `news`만 부른다. 자세히는 `technical`과 수급·심리 역할을 더한다. 아래 순서에 적힌 역할은 표준 깊이 기준이며, 깊이가 다르면 이 줄이 우선한다.
- 채팅 답변을 고르면 파일을 만들지 않는다. 파일은 사용자가 정한 폴더에, 정하지 않았으면 작업 폴더의 `reports/`에 `YYYY-MM-DD-리포트종류-대상.html`로 저장하고 경로를 알려 준다. 예: `2026-11-20-company-NVDA.html`, `2026-11-20-sector-반도체.html`.
- 리포트 파일은 항상 같은 디자인으로 만든다. 내용을 JSON으로 정리해 `python3 harness/report.py render 입력.json 출력.html`(PDF도 받으려면 `--pdf`)로 만들고, HTML을 직접 써서 만들지 않는다. 만든 뒤 `python3 harness/report.py check 출력.html`로 확인한다.
- 파일을 만들었으면 끝에 Gmail로도 받을지 한 번 묻고, 원하면 `report-email` 스킬로 넘긴다.
- 리서치 위키가 만들어져 있으면(`python3 harness/wiki.py status`가 성공하면) 파일을 위키에 넣을지도 함께 묻고, 원하면 `research-wiki` 스킬로 넘긴다. 방식이 drive-connector인데 Drive 커넥터 도구가 보이지 않으면 묻지 않는다.
- 역할 이름은 Claude Code에서 `us-stock-team:` 접두사가 붙어 보일 수 있다. 같은 역할이다.

## 순서

1. 대상 시장과 거래일을 정하고 정규장이 끝났는지 확인한다. 끝나지 않았으면 장중 시황이라고 밝힌다. 오늘이 주말이나 휴장일이면 마지막 거래일 기준으로 쓰고 그 날짜를 적는다.
2. 병렬로 맡긴다.
   - `strategist`: 지수 종가와 등락률, 업종별 등락, 대형·중소형과 성장·가치의 차이, 상승·하락 종목 수
   - `news`: 오늘 가격을 움직인 사건과 발생 시각
   - `technical`: 주요 지수의 추세와 지지·저항
   - 한국장이면 `kr-flows`에 외국인·기관·개인 순매수를, 미국장이면 `sentiment`에 변동성 지수와 옵션 흐름을 묻는다.
3. 가격 움직임과 사건의 시간 순서를 맞춘다. 사건이 가격보다 늦었으면 원인으로 쓰지 않는다. 원인이 분명하지 않으면 가설이라고 적는다.
4. 많이 오른 종목과 내린 종목 각 3~5개를 이유와 함께 적는다. 이유를 확인하지 못했으면 그렇게 적는다.

## 형식

1. 기준 시각과 오늘의 한 줄
2. 지수와 업종 표
3. 오늘 시장을 움직인 것 두세 가지
4. 눈에 띈 종목
5. 수급 또는 심리
6. 내일 볼 것

## 발행 전 점검

1. `editor` 역할에 초안을 보내 쉬운 말, 구조, 숫자와 출처의 일치를 점검받는다.
2. `compliance` 역할에 표현, 고지, 개인정보, 출처를 점검받는다.
3. 파일이 필요하면 `us-stock-research` 스킬의 렌더링 절차와 `editorial-design` 스킬로 한국어 HTML을 만든다.

전문 역할을 쓸 수 없는 환경에서는 현재 세션이 같은 항목을 직접 확인하고 독립 검토를 거치지 않았다고 밝힌다. 리포트는 조사 자료이며 투자 조언이나 권유가 아니라고 적는다. Codex에서는 역할 이름이 다르다: `news_desk`, `market_sentiment`, `technical_analyst`, `sector_analyst`, `market_strategist`, `idea_screener`, `report_editor`, `compliance_officer`, `performance_analyst`, `macro_rates`, `futures_desk`, `quant_research`, `risk_officer`, `portfolio_manager`, 미국 주식은 `us_stock_market`·`us_stock_fundamentals`·`us_stock_analyst_opinions`·`us_stock_valuation`·`us_stock_trade_timing`·`us_stock_risk_review`, 국내 주식은 `kr_stock_market`·`kr_stock_fundamentals`·`kr_stock_flows`.

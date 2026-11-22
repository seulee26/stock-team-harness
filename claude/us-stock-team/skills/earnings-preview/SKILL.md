---
name: earnings-preview
description: 실적 발표를 앞둔 종목에 대해 발표일, 시장 기대치, 봐야 할 지표, 시나리오별 주가 반응을 한 장으로 정리한다. "실적 발표 전에 뭘 봐야 해", "엔비디아 실적 프리뷰", "다음 주 실적 일정과 기대치", "어닝 전 체크포인트"에 사용한다. 발표된 실적의 평가는 stock-earnings-review를 쓴다.
---

# 실적 프리뷰

발표 전에 읽는 한 장이다. 숫자를 맞히려는 것이 아니라 무엇을 봐야 하는지 정리한다.

## 시작 전에 형식 확인

리포트를 만들 때만 적용한다. 한두 문장으로 답할 수 있는 사실 질문이나 단순 계산은 묻지 않고 바로 답한다.

조사를 시작하기 전에 아래 네 가지를 한 번에 묻는다. 선택지를 고르게 하는 질문 도구가 있으면 그것을 쓰고, 없으면 번호를 붙여 짧게 묻는다. 답을 받은 뒤에 조사를 시작한다.

1. 대상: 어떤 종목의 어느 분기 실적인지 (기본값: 다음에 발표될 분기. 종목은 기본값이 없다)
2. 깊이: 한 장, 자세히 (기본값: 한 장)
3. 받는 형식: 채팅 답변, HTML 파일, HTML과 PDF (기본값: 채팅 답변)
4. 읽는 사람: 주식이 처음인 사람, 경험이 있는 사람 (기본값: 처음인 사람)

- 사용자가 요청에서 이미 밝혔거나 `research-desk`·`stock-harness-start`에서 이미 정한 항목은 다시 묻지 않는다. 네 가지가 모두 정해져 있으면 묻지 않고 진행한다.
- 질문은 한 번만 한다. 사용자가 "알아서 해 줘"라고 하거나 답하지 않은 항목은 기본값을 쓴다. 기본값이 없는 항목은 사용자가 "알아서 해 줘"라고 해도 반드시 묻는다.
- 기본값을 썼으면 조사를 시작한다고 알리는 첫 답에 어떤 기본값을 썼는지 한 줄로 적고, 결과 첫머리에도 남긴다.
- 깊이에 따라 범위를 정한다. 한 장은 공시 역할과 의견 역할만 부른다. 자세히는 시세 역할과 `sentiment`를 더한다. 아래 순서에 적힌 역할은 표준 깊이 기준이며, 깊이가 다르면 이 줄이 우선한다.
- 채팅 답변을 고르면 파일을 만들지 않는다. 파일은 사용자가 정한 폴더에, 정하지 않았으면 작업 폴더의 `reports/`에 `YYYY-MM-DD-리포트종류-대상.html`로 저장하고 경로를 알려 준다. 예: `2026-11-20-company-NVDA.html`, `2026-11-20-sector-반도체.html`.
- 리포트 파일은 항상 같은 디자인으로 만든다. 내용을 JSON으로 정리해 `python3 harness/report.py render 입력.json 출력.html`(PDF도 받으려면 `--pdf`)로 만들고, HTML을 직접 써서 만들지 않는다. 만든 뒤 `python3 harness/report.py check 출력.html`로 확인한다.
- 파일을 만들었으면 끝에 Gmail로도 받을지 한 번 묻고, 원하면 `report-email` 스킬로 넘긴다.
- 리서치 위키가 만들어져 있으면(`python3 harness/wiki.py status`가 성공하면) 파일을 위키에 넣을지도 함께 묻고, 원하면 `research-wiki` 스킬로 넘긴다. 방식이 drive-connector인데 Drive 커넥터 도구가 보이지 않으면 묻지 않는다.
- 역할 이름은 Claude Code에서 `us-stock-team:` 접두사가 붙어 보일 수 있다. 같은 역할이다.

## 순서

1. 오늘 날짜를 적고 발표일과 시각을 확인한다. 회사가 확정한 일정과 시장 추정 일정을 구분한다.
2. 병렬로 맡긴다.
   - 미국 종목: `fundamentals`(지난 분기 실적과 회사 가이던스), `analyst-opinions`(컨센서스와 최근 추정치 변화), `market`(주가 흐름과 일정)
   - 국내 종목: `kr-fundamentals`, `kr-flows`, `kr-market`
   - `sentiment`: 옵션이 가격에 반영한 발표 당일 변동폭 (미국 종목)
3. 봐야 할 지표를 업종에 맞게 3~5개 고른다. 예: 반도체는 데이터센터 매출과 재고, 은행은 순이자마진, 플랫폼은 이용자 수와 광고 단가.
4. 지난 4개 분기의 실적 발표 때 기대치 대비 결과와 다음 날 주가 반응을 표로 만든다.
5. 세 가지 시나리오(기대 이상, 부합, 미달)마다 매출·이익 범위, 핵심 원인, 예상되는 주가 반응 방향을 적는다.

## 형식

1. 기준 시각, 발표 일시, 한 줄 요약
2. 시장 기대치 표: 매출, 영업이익, 주당이익, 가이던스 (출처와 집계일)
3. 꼭 봐야 할 지표 3~5개와 이유
4. 과거 4개 분기 반응 표
5. 시나리오 표
6. 발표 뒤 확인할 것

컨센서스는 집계처와 집계일을 반드시 적는다. 출처가 없으면 숫자를 만들지 않는다. 발표가 끝나면 `stock-earnings-review`로 이어 간다.

## 발행 전 점검

1. `editor` 역할에 초안을 보내 쉬운 말, 구조, 숫자와 출처의 일치를 점검받는다.
2. `compliance` 역할에 표현, 고지, 개인정보, 출처를 점검받는다.
3. 파일이 필요하면 `us-stock-research` 스킬의 렌더링 절차와 `editorial-design` 스킬로 한국어 HTML을 만든다.

전문 역할을 쓸 수 없는 환경에서는 현재 세션이 같은 항목을 직접 확인하고 독립 검토를 거치지 않았다고 밝힌다. 리포트는 조사 자료이며 투자 조언이나 권유가 아니라고 적는다. Codex에서는 역할 이름이 다르다: `news_desk`, `market_sentiment`, `technical_analyst`, `sector_analyst`, `market_strategist`, `idea_screener`, `report_editor`, `compliance_officer`, `performance_analyst`, `macro_rates`, `futures_desk`, `quant_research`, `risk_officer`, `portfolio_manager`, 미국 주식은 `us_stock_market`·`us_stock_fundamentals`·`us_stock_analyst_opinions`·`us_stock_valuation`·`us_stock_trade_timing`·`us_stock_risk_review`, 국내 주식은 `kr_stock_market`·`kr_stock_fundamentals`·`kr_stock_flows`.

---
name: sector-report
description: 산업 하나의 시장 규모, 성장 요인, 경쟁 구도, 가치사슬, 대표 기업을 정리한 산업 리포트를 만든다. "반도체 산업 정리해 줘", "2차전지 밸류체인", "AI 데이터센터 수혜주", "이 산업에서 누가 유리해", "업종 리포트"에 사용한다.
---

# 산업 리포트

산업을 모르는 사람이 읽고 구조를 이해할 수 있어야 한다. 종목 나열로 끝내지 않는다.

## 시작 전에 형식 확인

리포트를 만들 때만 적용한다. 한두 문장으로 답할 수 있는 사실 질문이나 단순 계산은 묻지 않고 바로 답한다.

조사를 시작하기 전에 아래 네 가지를 한 번에 묻는다. 선택지를 고르게 하는 질문 도구가 있으면 그것을 쓰고, 없으면 번호를 붙여 짧게 묻는다. 답을 받은 뒤에 조사를 시작한다.

1. 범위: 어떤 산업을, 미국·한국 중 어느 시장 기업 중심으로 볼지 (기본값: 미국과 한국 기업 모두. 산업은 기본값이 없다)
2. 깊이: 한 장 요약, 표준, 심층 (기본값: 표준)
3. 받는 형식: 채팅 답변, HTML 파일, HTML과 PDF (기본값: HTML 파일)
4. 읽는 사람: 주식이 처음인 사람, 경험이 있는 사람 (기본값: 처음인 사람)

- 사용자가 요청에서 이미 밝혔거나 `research-desk`·`stock-harness-start`에서 이미 정한 항목은 다시 묻지 않는다. 네 가지가 모두 정해져 있으면 묻지 않고 진행한다.
- 질문은 한 번만 한다. 사용자가 "알아서 해 줘"라고 하거나 답하지 않은 항목은 기본값을 쓴다. 기본값이 없는 항목은 사용자가 "알아서 해 줘"라고 해도 반드시 묻는다.
- 기본값을 썼으면 조사를 시작한다고 알리는 첫 답에 어떤 기본값을 썼는지 한 줄로 적고, 결과 첫머리에도 남긴다.
- 깊이에 따라 범위를 정한다. 한 장 요약은 `sector`만 부르고 대표 기업을 5개로 줄인다. 표준은 `news`, `strategist`를 더하고 대표 기업의 재무 확인에 미국 기업은 `fundamentals`, 한국 기업은 `kr-fundamentals`를 쓴다. 심층은 기업을 10개까지 늘리고 `risk-review`에 쟁점 검토를 맡긴다. 아래 순서에 적힌 역할은 표준 깊이 기준이며, 깊이가 다르면 이 줄이 우선한다.
- 채팅 답변을 고르면 파일을 만들지 않는다. 파일은 사용자가 정한 폴더에, 정하지 않았으면 작업 폴더의 `reports/`에 `YYYY-MM-DD-리포트종류-대상.html`로 저장하고 경로를 알려 준다. 예: `2026-11-20-company-NVDA.html`, `2026-11-20-sector-반도체.html`.
- 리포트 파일은 항상 같은 디자인으로 만든다. 내용을 JSON으로 정리해 `python3 harness/report.py render 입력.json 출력.html`(PDF도 받으려면 `--pdf`)로 만들고, HTML을 직접 써서 만들지 않는다. 만든 뒤 `python3 harness/report.py check 출력.html`로 확인한다.
- 파일을 만들었으면 끝에 Gmail로도 받을지 한 번 묻고, 원하면 `report-email` 스킬로 넘긴다.
- 리서치 위키가 만들어져 있으면(`python3 harness/wiki.py status`가 성공하면) 파일을 위키에 넣을지도 함께 묻고, 원하면 `research-wiki` 스킬로 넘긴다. 방식이 drive-connector인데 Drive 커넥터 도구가 보이지 않으면 묻지 않는다.
- 역할 이름은 Claude Code에서 `us-stock-team:` 접두사가 붙어 보일 수 있다. 같은 역할이다.

## 순서

1. 산업의 범위를 한 문단으로 정한다. 무엇을 포함하고 무엇을 빼는지 적는다.
2. 병렬로 맡긴다.
   - `sector`: 시장 규모와 성장률, 수요 요인, 가치사슬, 경쟁 구도, 규제
   - `news`: 최근 석 달의 산업 뉴스와 정책 변화
   - `strategist`: 업종 지수의 성과와 평가 배수
3. 대표 기업 5~10개를 미국과 한국에서 고른다. 한국 기업은 `kr-fundamentals`, 미국 기업은 `fundamentals`에 핵심 재무를 확인받는다.
4. 가치사슬 단계마다 누가 돈을 버는지(이익률)와 누가 가격을 정하는지를 적는다.
5. 산업 사이클의 현재 위치를 재고, 가동률, 수주, 판매 가격 같은 지표로 보여 준다.
6. 낙관론과 비관론이 갈리는 지점 두세 개를 양쪽 근거와 함께 쓴다.

## 형식

1. 기준 시각과 한 줄 결론
2. 이 산업은 무엇인가: 쉬운 설명과 범위
3. 시장 규모와 성장: 출처와 기준 연도
4. 가치사슬 그림 또는 표
5. 대표 기업 비교 표: 매출, 이익률, 성장률, 시가총액, 평가 배수 (회계기간과 통화 통일)
6. 지금 사이클의 위치
7. 갈리는 쟁점
8. 앞으로 볼 지표와 일정

비교가 맞지 않는 기업은 표에서 빼고 이유를 적는다. 개별 종목을 깊이 보려면 기업 분석 스킬로 넘긴다.

## 발행 전 점검

1. `editor` 역할에 초안을 보내 쉬운 말, 구조, 숫자와 출처의 일치를 점검받는다.
2. `compliance` 역할에 표현, 고지, 개인정보, 출처를 점검받는다.
3. 파일이 필요하면 `us-stock-research` 스킬의 렌더링 절차와 `editorial-design` 스킬로 한국어 HTML을 만든다.

전문 역할을 쓸 수 없는 환경에서는 현재 세션이 같은 항목을 직접 확인하고 독립 검토를 거치지 않았다고 밝힌다. 리포트는 조사 자료이며 투자 조언이나 권유가 아니라고 적는다. Codex에서는 역할 이름이 다르다: `news_desk`, `market_sentiment`, `technical_analyst`, `sector_analyst`, `market_strategist`, `idea_screener`, `report_editor`, `compliance_officer`, `performance_analyst`, `macro_rates`, `futures_desk`, `quant_research`, `risk_officer`, `portfolio_manager`, 미국 주식은 `us_stock_market`·`us_stock_fundamentals`·`us_stock_analyst_opinions`·`us_stock_valuation`·`us_stock_trade_timing`·`us_stock_risk_review`, 국내 주식은 `kr_stock_market`·`kr_stock_fundamentals`·`kr_stock_flows`.

---
name: thesis-tracker
description: 투자 논지를 근거와 깨지는 조건으로 적어 두고, 새 실적이나 뉴스가 나올 때마다 아직 유효한지 점검한다. "내 투자 아이디어 기록해 줘", "이 종목 계속 들고 가도 돼", "논지 점검", "투자 일지", "지난번 판단 맞았어"에 사용한다.
---

# 투자 논지 점검

논지는 틀렸음을 확인할 수 있게 써야 한다. "좋은 회사라서"는 논지가 아니다.

## 시작 전에 형식 확인

리포트를 만들 때만 적용한다. 한두 문장으로 답할 수 있는 사실 질문이나 단순 계산은 묻지 않고 바로 답한다.

조사를 시작하기 전에 아래 네 가지를 한 번에 묻는다. 선택지를 고르게 하는 질문 도구가 있으면 그것을 쓰고, 없으면 번호를 붙여 짧게 묻는다. 답을 받은 뒤에 조사를 시작한다.

1. 할 일: 새 논지를 기록할지, 기존 논지를 점검할지 (기본값: 기록이 있으면 점검, 없으면 새로 기록. 종목은 기본값이 없다)
2. 깊이: 한 장, 자세히 (기본값: 한 장)
3. 받는 형식: 채팅 답변, HTML 파일, HTML과 PDF (기본값: 채팅 답변)
4. 읽는 사람: 주식이 처음인 사람, 경험이 있는 사람 (기본값: 처음인 사람)

- 사용자가 요청에서 이미 밝혔거나 `research-desk`·`stock-harness-start`에서 이미 정한 항목은 다시 묻지 않는다. 네 가지가 모두 정해져 있으면 묻지 않고 진행한다.
- 질문은 한 번만 한다. 사용자가 "알아서 해 줘"라고 하거나 답하지 않은 항목은 기본값을 쓴다. 기본값이 없는 항목은 사용자가 "알아서 해 줘"라고 해도 반드시 묻는다.
- 기본값을 썼으면 조사를 시작한다고 알리는 첫 답에 어떤 기본값을 썼는지 한 줄로 적고, 결과 첫머리에도 남긴다.
- 깊이에 따라 범위를 정한다. 한 장은 기록과 최근 사실만 대조한다. 자세히는 `risk-review`와 `performance`를 더한다. 아래 순서에 적힌 역할은 표준 깊이 기준이며, 깊이가 다르면 이 줄이 우선한다.
- 채팅 답변을 고르면 파일을 만들지 않는다. 파일은 사용자가 정한 폴더에, 정하지 않았으면 작업 폴더의 `reports/`에 `YYYY-MM-DD-리포트종류-대상.html`로 저장하고 경로를 알려 준다. 예: `2026-11-20-company-NVDA.html`, `2026-11-20-sector-반도체.html`.
- 파일을 만들었으면 끝에 Gmail로도 받을지 한 번 묻고, 원하면 `report-email` 스킬로 넘긴다.
- 리서치 위키가 만들어져 있으면(`python3 harness/wiki.py status`가 성공하면) 파일을 위키에 넣을지도 함께 묻고, 원하면 `research-wiki` 스킬로 넘긴다. 방식이 drive-connector인데 Drive 커넥터 도구가 보이지 않으면 묻지 않는다.
- 역할 이름은 Claude Code에서 `us-stock-team:` 접두사가 붙어 보일 수 있다. 같은 역할이다.

## 처음 기록할 때

1. 논지를 한 문장으로 쓴다: 무엇이, 왜, 언제까지 달라질 것인가.
2. 논지를 받치는 근거 3~5개와, 논지가 깨지는 조건 3~5개를 적는다. 조건은 숫자나 사건으로 쓴다. 프로그램은 각각 1~5개를 받는다.
3. 목표 가격과 손절 기준을 해당 통화의 절대 가격으로 적는다.
4. 기록한다.

```sh
python3 harness/desk.py thesis-add NVDA --market US --statement "데이터센터 매출 성장이 내년까지 이어진다" --pillar "분기 데이터센터 매출 증가" --pillar "주요 고객의 설비투자 계획 상향" --pillar "영업이익률 유지" --risk "주요 고객 설비투자 축소 발표" --risk "두 분기 연속 매출 가이던스 하회" --risk "영업이익률 5%포인트 이상 하락" --target 180 --stop 120
```

5. 의견을 냈으면 기준 가격과 비교 지수 수준을 함께 남긴다.

```sh
python3 harness/desk.py decision-log NVDA --market US --rating buy --price 150 --benchmark SPX --benchmark-level 6800
```

## 점검할 때

1. `python3 harness/desk.py thesis-list NVDA`로 기록을 읽는다.
2. 마지막 점검 뒤에 나온 실적, 공시, 뉴스를 해당 시장의 역할과 `news`에 확인받는다.
3. 근거마다 강화, 약화, 변화 없음으로 표시한다. 깨지는 조건에 닿았는지 본다.
4. `risk-review`에 논지를 가장 약하게 만드는 증거를 찾게 한다.
5. 결과를 기록한다. 확신도는 1(약함)부터 5(강함)까지다.

```sh
python3 harness/desk.py thesis-update NVDA --note "3분기 데이터센터 매출이 가이던스를 넘음" --impact strengthens --conviction 4
```

6. 깨지는 조건에 닿았으면 그대로 알리고 닫는다. 이유를 바꿔 가며 논지를 이어 가지 않는다.

```sh
python3 harness/desk.py thesis-close NVDA --reason "주요 고객이 설비투자 축소를 발표함"
```

7. `performance` 역할에 `scorecard` 정산을 맡겨 지금까지의 의견이 지수 대비 어땠는지 본다.

## 형식

1. 기준 시각, 논지 한 문장, 현재 상태(유효, 약화, 깨짐)
2. 근거 점검 표: 근거, 최근 사실, 강화·약화
3. 깨지는 조건 점검 표
4. 가격: 기록 당시, 현재, 목표, 손절
5. 다음 점검일과 확인할 것

기록은 내 PC의 `.local/desk/`에만 저장된다.

## 발행 전 점검

1. `editor` 역할에 초안을 보내 쉬운 말, 구조, 숫자와 출처의 일치를 점검받는다.
2. `compliance` 역할에 표현, 고지, 개인정보, 출처를 점검받는다.
3. 파일이 필요하면 `us-stock-research` 스킬의 렌더링 절차와 `editorial-design` 스킬로 한국어 HTML을 만든다.

전문 역할을 쓸 수 없는 환경에서는 현재 세션이 같은 항목을 직접 확인하고 독립 검토를 거치지 않았다고 밝힌다. 리포트는 조사 자료이며 투자 조언이나 권유가 아니라고 적는다. Codex에서는 역할 이름이 다르다: `news_desk`, `market_sentiment`, `technical_analyst`, `sector_analyst`, `market_strategist`, `idea_screener`, `report_editor`, `compliance_officer`, `performance_analyst`, `macro_rates`, `futures_desk`, `quant_research`, `risk_officer`, `portfolio_manager`, 미국 주식은 `us_stock_market`·`us_stock_fundamentals`·`us_stock_analyst_opinions`·`us_stock_valuation`·`us_stock_trade_timing`·`us_stock_risk_review`, 국내 주식은 `kr_stock_market`·`kr_stock_fundamentals`·`kr_stock_flows`.

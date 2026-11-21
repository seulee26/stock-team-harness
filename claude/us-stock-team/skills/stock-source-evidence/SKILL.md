---
name: stock-source-evidence
description: 종목의 공개 시세, 공시, 실적 출처를 확인하고 분석 기준시각에 맞춰 정리한다. OpenBB 데이터 교차검증, 시세 제공처 비교, 과거 시점 재현에 사용한다.
---

# 공개 데이터와 출처

1. 종목·거래소·주식 클래스·통화와 분석 기준시각을 확인한다. 미국 종목의 기본 시계는 미국 동부시간이다. 필요한 역할과 조사 시각은 `python3 harness/stock_harness.py research-plan TICKER`에서 확인한다.
2. 공개 일봉이 필요하면 `python3 harness/integrations.py price TICKER --start YYYY-MM-DD --end YYYY-MM-DD`로 OpenBB를 호출한다. 시세 기준시각, 정규장·시간외 구분, 주식분할·배당 조정 여부는 제공처 원문에서 확인한다. 조정종가로 수익률을 구했다면 목표가와 비교할 때 쓰는 실제 종가와 이름을 구분한다. 거래량 단위와 거래일 공백도 확인한다.
3. `python3 harness/integrations.py filings TICKER --limit 3`로 SEC 공시 목록을 찾는다. 공시 수치는 회사 IR의 실적 발표와 SEC 원문에서 회계기간, 발표시각, GAAP·비GAAP, 통화·단위를 확인한다. 회사 전망, 외부 추정치와 실적을 각각 출처에 연결한다. 종목·기간·단위가 다른 값을 한 열에서 비교하려면 먼저 기준을 맞춘다.
4. 토스 시세를 조사 역할에 전달할 때는 `python3 harness/stock_harness.py market-packet TICKER` 출력만 사용한다. 토스 계좌와 보유 데이터는 공개 근거 파일에 포함하지 않는다.
5. 심층 근거 파일에 역할 `role`, 공개 HTTPS 주소 `source`, 공개 시각 `availableAt`을 기록한다. 시세 관측 시각과 시장에 공개된 시각을 구분한다. `python3 harness/stock_harness.py research-check PATH_TO_EVIDENCE`로 기준시각 이후 자료와 역할 누락을 확인한다.

이름이 같아도 기간·조정·세션이 다르면 두 수치를 함께 표시한다. 자료 공백은 원인과 확인 가능한 마지막 시점을 적는다. 출처를 교체할 때 바뀐 제공처와 계산 기준도 결과에 남긴다.

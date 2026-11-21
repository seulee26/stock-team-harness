# 출처와 날짜 기준

## 출처 선택

| 필요한 정보 | 우선 확인할 곳 |
| --- | --- |
| 재무제표, 주식 수, 부채, 리스크 | [SEC EDGAR 검색](https://www.sec.gov/edgar/search/), [EDGAR 공개 API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), 해당 기업 IR |
| 실적 발표와 가이던스, 기업행동, 일정 | 해당 기업 IR의 실적 보도자료·이벤트 페이지와 SEC 8-K 또는 6-K 및 첨부자료 |
| 가격과 거래시간 | [Nasdaq 시장 데이터](https://www.nasdaq.com/market-activity), [Nasdaq 일별 가격](https://www.nasdaq.com/market-activity/quotes/historical), [NYSE 거래시간·휴장일](https://www.nyse.com/trade/hours-calendars). 가격표에 렌더링된 거래일·세션·값을 실제로 확인하고, 접근이 어려우면 날짜와 세션이 명시된 신뢰할 수 있는 시세 제공처로 전환한다. |
| 금리, 물가, 고용, GDP | [FRED 10년물](https://fred.stlouisfed.org/series/DGS10), [Fed FOMC](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [BLS](https://www.bls.gov/), [BEA](https://www.bea.gov/). 과거 시점의 수정 가능 지표는 당시 보도자료 또는 [ALFRED](https://alfred.stlouisfed.org/) 빈티지를 확인한다. |
| ETF, 벤치마크 | 펀드 운용사와 지수 산출기관의 원문. 보유 종목, 순자산, NAV·시장가격 각각의 기준일을 확인한다. |
| 컨센서스와 뉴스 | 날짜가 찍힌 제공처의 컨센서스, 회사 IR·공시, 원발표 기관, 날짜가 명확한 보도. 추정치의 집계 시점, 대상 기간, GAAP·조정 여부를 실제로 확인한다. |

공개 공시 API의 XBRL 집계에서 단위·개념·기간·공시 번호를 확인하고 최신 10-K/10-Q 원문과 교차 확인한다. 기업 고유 태그나 분기·세그먼트 정보가 빠지면 원문 표를 읽는다. 프로그램으로 EDGAR에 접근하는 경우 [SEC 이용 정책](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)을 따른다.

## 비교 가능한 관측값

- 시세에는 티커·거래소·USD 가격·거래 세션·거래소 기준 시각 또는 거래일·출처를 남긴다. 거래일이 확인된 종가로 대체했으면 날짜를 표시한다. 장전·장후 수익률은 해당 세션과 비교 종가를 적는다. 과거 밸류에이션의 기준가는 당시 정규장 거래 가격을 쓰고, 이후 실시된 분할이나 배당이 소급 반영된 조정주가 여부를 점검한다.
- 실적은 회계기간 종료일과 공개일을 분리한다. 기준시각이 중요한 경우 SEC 접수시각과 IR 발표시각을 확인한다. 정정 공시는 기준일 이전에 공개된 버전까지 반영한다. 기준시각 이후에 새로 공개된 실적이나 정정 자료는 제외한다. 이후에 제공된 가격 아카이브는 당시 확정된 관측값의 확인에 사용할 수 있다.
- 여러 출처가 다르면 조정주가·원주가, 세션, 통화, 분기·누적, 연결·별도, GAAP·비GAAP 차이부터 확인한다. 숫자를 하나로 합치기 전에 해당 정의의 원자료와 대조한다.
- 회사가 발표한 실적 일정과 제공업체의 추정일을 표시한다. 가이던스와 컨센서스는 각각 기간과 집계시점을 표시한다. 발표 이후에 재집계된 전망으로 이전 실적의 서프라이즈를 계산하지 않는다.

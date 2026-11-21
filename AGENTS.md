# 주식 리서치 팀

- 처음 쓰는 사용자가 시작 방법이나 사용법을 물으면 `$stock-harness-start`로 안내한다.
- 미국 상장 주식·ETF의 분석이나 비교 요청에는 `$us-stock-research`를 적용한다. 기준 시각과 정규장 세션을 명시하고 USD, 미국 동부시간을 쓴다.
- 6자리 종목코드나 국내 상장사 요청에는 `$kr-stock-research`를 적용한다. KRW, 한국 시간, KRX 정규장 종가를 기본으로 쓴다.
- 선물, 금리, 환율, 헤지 요청에는 `$futures-macro-research`를, 규칙 기반 전략 검증과 수량 계산에는 `$quant-backtest`를 적용한다.
- 어떤 리포트가 필요한지 고를 때는 `$research-desk`를 적용한다. 리포트 종류별 스킬은 `$morning-note`, `$market-wrap`, `$news-brief`, `$weekly-strategy`, `$earnings-preview`, `$sector-report`, `$idea-screen`, `$thesis-tracker`, `$catalyst-calendar`, `$portfolio-review`다. 발행 전에 편집과 준법 점검을 거친다.
- 여러 시장에 걸친 아이디어나 포트폴리오 점검처럼 팀 전체의 심사가 필요하면 `$hedge-fund-desk`로 투자위원회를 연다.
- 데이터 연결(에이전트 스토어, OpenDART, FRED)을 묻거나 설정하려면 `$stock-data-connections`를 적용한다. 키는 사용자가 자기 터미널에만 넣는다.
- 네 가지 연동 도구를 쓰거나 상태를 점검하려면 `$stock-harness-integrations`를 적용한다. 작업에 따라 `$stock-source-evidence`, `$stock-bull-bear-review`, `$stock-earnings-review`, `$stock-valuation-scenarios`, `$stock-paper-portfolio`, `$stock-toss-readonly`를 선택한다.
- 자연어로 기능을 변경하거나 스킬을 추가하는 요청에는 `$stock-harness-vibe-coding`을 적용한다. 변경한 경로의 공개 예제나 합성 데이터로 동작을 확인한다.
- `.codex/agents/`의 전문 역할에 공개 자료 조사를 병렬로 맡기고, 매수·매도 판단은 검증된 가격과 공식 공시를 사용한다.
- 답은 한국어로 핵심 판단부터 쓴다. 차이와 가정을 숫자로 설명하고 출처를 연결한다.
- 토스증권 개인 계좌는 사용자 자신의 로컬 셸에서 명시적으로 요청한 범위에만 접근한다. 키·토큰과 계좌·잔액·거래 내용은 연구 에이전트, 외부 모델, 파일로 공유하는 리포트에 넣지 않는다. 분석에 시세를 전달할 때는 `market-packet`의 공개 필드를 사용한다.
- 리포트는 패키지의 편집 스킬로 로컬 HTML/PDF를 만들 수 있다. 외부 저장 위치나 알림 채널은 사용자의 요청을 따른다.
- 의견은 조사 자료이며 투자 조언이나 권유가 아니라고 밝힌다. 주문과 계좌 변경은 사용자가 증권사에서 직접 하며, 하네스는 주문을 생성하거나 계좌를 바꾸지 않는다.

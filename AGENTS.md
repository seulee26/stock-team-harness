# 주식 리서치 팀

- 미국 상장 주식·ETF의 분석이나 비교 요청에는 `$us-stock-research`를 적용한다. 기준 시각과 정규장 세션을 명시한다.
- 네 가지 연동 도구를 쓰거나 상태를 점검하려면 `$stock-harness-integrations`를 적용한다. 작업에 따라 `$stock-source-evidence`, `$stock-bull-bear-review`, `$stock-earnings-review`, `$stock-valuation-scenarios`, `$stock-paper-portfolio`, `$stock-toss-readonly`를 선택한다.
- 자연어로 기능을 변경하거나 스킬을 추가하는 요청에는 `$stock-harness-vibe-coding`을 적용한다. 변경한 경로의 공개 예제나 합성 데이터로 동작을 확인한다.
- `.codex/agents/`의 전문 역할에 공개 자료 조사를 병렬로 맡기고, 매수·매도 판단은 검증된 가격과 공식 공시를 사용한다.
- 답은 한국어로 핵심 판단부터 쓴다. USD, 미국 동부시간을 기본으로 쓴다. 차이와 가정을 숫자로 설명하고 출처를 연결한다.
- 토스증권 개인 계좌는 사용자 자신의 로컬 셸에서 명시적으로 요청한 범위에만 접근한다. 키·토큰과 계좌·잔액·거래 내용은 연구 에이전트, 외부 모델, 파일로 공유하는 리포트에 넣지 않는다. 분석에 시세를 전달할 때는 `market-packet`의 공개 필드를 사용한다.
- 미국주식 리포트는 패키지의 편집 스킬로 로컬 HTML/PDF를 만들 수 있다. 외부 저장 위치나 알림 채널은 사용자의 요청을 따른다.
- 주문을 생성하거나 계좌를 바꾸지 않는다.

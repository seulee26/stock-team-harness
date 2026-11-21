---
name: stock-harness-vibe-coding
description: Codex나 Claude Code에서 자연어로 주식 하네스의 데이터 소스, 토론, 평가와 모의투자 기능을 추가하거나 조합한다. 하네스 코드·스킬을 변경하고 실행 및 공개 패키징까지 검증할 때 사용한다.
---

# 주식 하네스 바이브코딩

사용자가 설명한 결과를 CLI 입력·출력과 완료 조건으로 구체화한다. 예를 들어 “NVDA 일봉으로 상승·하락 근거를 갱신해 줘”라면 OpenBB가 반환하는 공개 시세 필드와 토론이 읽는 근거를 먼저 확인한다. “가상 계좌에 거래 비용을 포함해 줘”라면 모의 입력과 현금·수량 계산부터 검증한다.

1. `python3 harness/integrations.py doctor`로 로컬 구성을 확인하고 `harness/ARCHITECTURE.md`에서 해당 경로를 찾는다. 공개 데이터는 OpenBB, 논지 토론은 TradingAgents와 세션 에이전트, 실적과 가치평가 절차는 Anthropic Financial Services, 모의 장부는 AI Hedge Fund 경계를 따른다.
2. 해당 명령의 실제 호출 경로, 공유 JSON 필드와 생성되는 배포물을 확인한 뒤 하네스와 스킬을 수정한다. OpenBB 가격 필드를 추가하면 출처·거래일·가격 단위를 함께 넘긴다. 같은 합성 입력을 Codex와 Claude Code가 처리하도록 `.agents/skills`와 Claude 플러그인에 적용한다. 업스트림 버전을 변경할 때는 `harness/upstream-lock.json`의 커밋과 체크섬 및 라이선스 확인을 함께 갱신한다.
3. 테스트는 공개 자료 또는 합성 입력으로 재현한다. `python3 -m unittest discover -s harness`와 수정한 명령을 실행한다. 코드 변경과 설치 환경의 결과를 대조하고 모델 API를 사용했다면 실제 호출과 모의 검증의 범위를 기록한다.
4. 릴리스 빌더가 있는 원본 프로젝트에서 공개 번들은 `python3 service/build_open_source.py`로 생성한다. 새 ZIP을 별도 경로에 풀어 바뀐 명령을 다시 실행한다. 설치 디렉터리, 토스 계좌·환경 파일·키와 개인 보고서가 공개 ZIP에 들어가지 않도록 파일 목록을 확인한다.

새 기능을 설명할 때 사용한 도구, 실행 명령과 확인 결과를 먼저 적는다. 사용자 요청의 실행 경로가 시세·모의투자라면 토스 계좌 접근을 프로젝트 변경에 요구하지 않는다.

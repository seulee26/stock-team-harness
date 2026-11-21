# 미국주식 리서치 팀

미국 상장 주식과 ETF를 분석해 한국어 리포트를 만듭니다. 매수·매도 판단 기준, 애널리스트 의견, 핵심 실적과 출처를 확인할 수 있습니다. HTML이 기본이며 PDF로도 내보낼 수 있습니다.

## Claude Code에서 쓰기

압축을 푼 패키지 루트에서 Claude Code에 로그인하고 플러그인을 불러옵니다.

```bash
claude --plugin-dir ./claude/us-stock-team
```

```text
/us-stock-team:us-stock-research MSFT 최신 실적과 주가를 초보자용으로 분석해줘.
```

현재 세션이 리드를 맡고 공시·재무, 시세·이벤트, 애널리스트 의견을 조사합니다. 에이전트 위임을 쓸 수 있는 환경에서는 전문 역할을 활용합니다. [Claude 플러그인 매니페스트](https://code.claude.com/docs/en/plugins-reference)

`/us-stock-team:stock-harness-integrations`로 네 가지 연동 도구를 확인할 수 있습니다. 기능을 추가하거나 수정하려면 `/us-stock-team:stock-harness-vibe-coding`을 호출하세요. [설치와 스킬 목록](../../README.md)

## 토스증권 연동

패키지 루트의 [하네스 안내](../../harness/README.md)를 따릅니다. 연결 정보는 사용하는 기기에서 지정합니다.

## 참고한 공식 구현

Anthropic의 금융 서비스 저장소에서 Market Researcher가 리서치·비교·문서화 역할을 분리하는 방식과 플러그인 파일 구조를 참고했습니다. 이 미국주식 패키지는 기존 프로젝트의 한국어 스킬, 공개 자료 워크플로와 HTML 렌더러를 Claude에 맞춰 구성한 작업물입니다. [Anthropic Financial Services](https://github.com/anthropics/financial-services), [Market Researcher 관리형 에이전트 템플릿](https://github.com/anthropics/financial-services/tree/3e32c2287dcb637c184c01cc0ad82d6af7e9bb0f/managed-agent-cookbooks/market-researcher)

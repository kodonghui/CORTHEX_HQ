# 신기술 도전 리서치 — 2026-02-25

> 최신 기술/논문/모범사례 리서치 후 CORTHEX 적용 가능한 아이디어 정리
> 원본: `.claude/worktrees/fun-research/docs/todo/2026-02-25_신기술-도전-리서치.TODO.md`
> 원본: `.claude/worktrees/fun-research/docs/todo/2026-02-25_신기술-도전-리서치.TODO.md`

---

## 🔄 상세 검토 중 (대표님 결정 대기)

### S1. WebGPU 파티클 NEXUS
- **뭔가?**: 현재 NEXUS 3D의 70개 정적 노드를 → WebGPU 컴퓨트 셰이더 기반 **10만~100만개 파티클**로 업그레이드
- **왜 좋은가?**: 에이전트가 분석 중이면 해당 노드에서 빛 파티클이 쏟아지고, 부서 간 데이터 전달이 빛줄기로 보임. "자비스 홀로그램" 같은 느낌
- **어떻게?**: Three.js r171+ `three/webgpu` import 변경 → TSL(Three Shader Language)로 파티클 셰이더 → GPGPU 컴퓨트로 GPU에서 직접 물리 연산
- **난이도**: 중
- **참고**: [WebGPU 마이그레이션 가이드](https://www.utsubo.com/blog/webgpu-threejs-migration-guide) | [TSL 필드 가이드](https://blog.maximeheckel.com/posts/field-guide-to-tsl-and-webgpu/) | [은하 파티클 튜토리얼](https://threejsroadmap.com/blog/galaxy-simulation-webgpu-compute-shaders)

### S2. 에이전트 장기 기억 시스템 (Observational Memory)
- **뭔가?**: 에이전트가 이전 분석/대화를 **크로스-세션으로 기억**하게 하는 시스템
- **왜 좋은가?**: CIO가 "지난번 NVDA 분석에서 뭘 틀렸는지" 기억. 학습하는 직원.
- **어떻게?**: SQLite `agent_memories` 테이블 (에피소딕/시맨틱/절차적 3종) → 분석 완료 시 자동 기억 추출 → 다음 분석 시 프롬프트 주입. 벡터DB 불필요.
- **난이도**: 중
- **참고**: [Observational Memory 비용 10배 절감](https://venturebeat.com/data/observational-memory-cuts-ai-agent-costs-10x-and-outscores-rag-on-long) | [ICLR 2026 MemAgents](https://openreview.net/pdf?id=U51WxL382H)

### A2. MCP (Model Context Protocol) 도구 표준화
- **뭔가?**: CORTHEX의 89개 도구를 Anthropic 공식 표준 프로토콜로 감싸서, Claude/GPT/Gemini 누구든 같은 방식으로 사용
- **왜 좋은가?**: 현재 tools.yaml 수동 관리 → MCP 서버로 자동화. 외부 500+ 공개 MCP 서버 즉시 연결 가능.
- **어떻게?**: Python FastMCP SDK → `@mcp.tool()` 데코레이터로 기존 도구 래핑
- **난이도**: 중
- **참고**: [MCP 공식 Python SDK](https://github.com/modelcontextprotocol/python-sdk) | [MCP 서버 빌드](https://modelcontextprotocol.io/docs/develop/build-server)

### B3. Claude Agent SDK 연동
- **뭔가?**: Anthropic 공식 에이전트 SDK로 현재 수동 구현한 멀티에이전트 오케스트레이션 대체
- **왜 좋은가?**: 서브에이전트 병렬 실행 / 컨텍스트 격리 / 가드레일 / 트레이싱이 SDK에서 기본 제공. 서브에이전트는 Haiku로 돌려 비용 절감.
- **어떻게?**: `claude-agent-sdk-python` 설치 → `ClaudeSDKClient` + `subagents_enabled=True` → 기존 처장/전문가 구조를 SDK 오케스트레이터/서브에이전트로 매핑
- **난이도**: 상 (기존 아키텍처 상당부분 교체)
- **참고**: [Claude Agent SDK 공식](https://platform.claude.com/docs/en/agent-sdk/overview) | [서브에이전트 문서](https://platform.claude.com/docs/en/agent-sdk/subagents)

---

## ⬜ 보류 (나중에 도전)

### A1. 다크 글래스모피즘 UI
- Tailwind `backdrop-blur-xl` + `bg-white/5`로 "아이언맨 연구실" 느낌
- **난이도**: 하 | **참고**: [Dark Glassmorphism 2026](https://medium.com/@developer_89726/dark-glassmorphism-the-aesthetic-that-will-define-ui-in-2026-93aa4153088f)

### S3. 음성 사령관실 ("자비스, 시장 분석해")
- Web Speech API(무료) 음성 입력 → TTS 응답. 마이크 버튼 하나로 구현.
- **난이도**: 하 | **쿨팩터**: ★★★★★

### A3. AI-Trader 벤치마크 (CIO 성적표)
- 홍콩대학교 AI-Trader 벤치마크로 CIO 매매 판단 정확도 자동 채점
- **참고**: [AI-Trader 논문](https://arxiv.org/abs/2512.10971) | [GitHub](https://github.com/HKUDS/AI-Trader)

### B1. 사이버펑크 터미널 모드
- Arwes / Cybercore CSS 기반 "터미널 모드" 토글
- **참고**: [Arwes SF UI](https://arwes.dev/)

---

## 🔴 SS급 — 개어려운데 개쩌는 기술

### SS1. 디지털 트윈
- CORTHEX 전체 시스템의 실시간 디지털 복제본. What-if 시나리오 가상 시뮬레이션.
- **난이도**: 최상 | **쿨팩터**: ★★★★★★
- **참고**: [디지털 트윈 2026](https://www.rtinsights.com/digital-twins-in-2026-from-digital-replicas-to-intelligent-ai-driven-systems/)

### SS2. 뉴로-심볼릭 AI — "할루시네이션 킬러"
- LLM + 지식그래프 결합. CIO 판단을 논리적으로 교차검증해서 할루시네이션 차단.
- **난이도**: 최상 | **쿨팩터**: ★★★★★★
- **참고**: [지식그래프+LLM 논문](https://arxiv.org/pdf/2302.07200)

### SS3. 에이전트 디베이트 프로토콜 — "AI 토론회"
- 레드팀 에이전트가 CIO 매수 판단에 자동 반론 → 재반박 → 최종 신뢰도 조정
- **난이도**: 상 | **쿨팩터**: ★★★★★
- **참고**: [Agentic Red Teaming 2026](https://cloudsecurityguy.substack.com/p/why-agentic-ai-red-teaming-will-explode)

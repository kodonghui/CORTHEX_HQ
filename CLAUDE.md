# CORTHEX HQ - Claude 작업 규칙

> 상세 참조(API URL, 시크릿 목록, 모델표, 보고 템플릿, 비유 사전 등): `docs/claude-reference.md`

## 🔴 처장 = 5번째 분석가! (CEO 핵심 아이디어)
- **모든 부서 처장(CIO/CSO/CLO/CMO/CPO)은 전문가와 별개로 독자 분석을 병렬 수행**
- 구조: [처장 독자분석 + 전문가 N명] 병렬 gather → 전부 합쳐서 종합
- "종합할 때 도구 써라"(프롬프트 의존) ❌ → "독자분석 따로 돌려"(구조적 강제) ✅
- 이 구조를 깨뜨리는 코드 변경 절대 금지 | 코드: `_manager_with_delegation()` in arm_server.py

## 🔴 실시간 분석 모니터링 — 1분마다 보고!
- "로그 확인해" / "분석 모니터링" → `/api/activity-logs` 1분마다 자동 보고
- 전문가별 도구 호출 횟수 + 비용 + QA 결과 표. 완료까지 중단 없이

## 🔴 메모리 파일 금지!
- `~/.claude/` memory 폴더 저장 금지. **모든 상태/기록/설정은 git 파일에만**: `docs/`, `config/`, `CLAUDE.md`

## 🔴 서버 로그 — 되니까 "안 된다"고 말하지 마라!
- 분석 모니터링: `/api/activity-logs` | 배포 후: `/api/debug/server-logs` | 둘 다 외부 접근 가능
- **상세 API URL**: `docs/claude-reference.md` | Cloudflare WAF Skip 만료: 2026-03-07

---

## ⚡ 세션 시작
1. `git worktree list` → 다른 세션과 겹치면 전용 worktree 생성
2. `git fetch origin && git status` → 미커밋 있으면 대표님에게 물어볼 것
3. 깨끗하면 `git checkout main && git pull` → `git checkout -b claude/작업명 origin/main`
4. 먼저 탐색: `docs/project-status.md` → `docs/updates/` 최근 파일 → 관련 코드 Read

## 🔴 날짜/시간 — 한국 시간(KST) 기준!
- UTC → KST(+9시간) 변환 필수. TODO/업데이트/보고 모든 날짜는 한국 날짜 기준

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ | 도메인: `corthex-hq.com`
- 소유자: kodonghui (고동희 대표님, 법학전공 / 비개발자) | 언어: 한국어

## 소통 규칙
- 호칭: **"대표님"** (CEO님 금지). 존댓말 필수
- **뻔한 질문 금지**: "커밋할까요?" → 바로 실행
- **"논의" 키워드 → 코딩 금지**: 옵션 + 추천 제시, 대표님 결정 후 실행
- **"align" 키워드 → 내 이해를 먼저 설명**: 코딩 전에 현재 이해를 대표님에게 설명하고 교정받기
- **논의가 꼬리물기 → 확정 사항 반복 명시**: 멀티턴 논의 시 매 응답 상단에 "✅ 확정된 것" 섹션 표시. `docs/project-status.md`에도 맥락+이유+결정 전부 기록
- **소신 발언 필수**: B가 더 나으면 먼저 말할 것
- **"로컬에서 확인" 금지** → 항상 `corthex-hq.com`에서 확인
- 작업 완료 = 커밋 + 푸시 + 배포 + 서버 확인 + 빌드번호 보고

## 🔴 기술 설명 — 대표님은 비개발자!
- **비유는 처음 한 번만**: 새 용어 첫 등장 시만 설명. 이미 나온 용어는 그냥 씀 (대표님이 익히는 중)
- **구체적 숫자로**: "최적화했습니다" ❌ → "8,500줄→6,000줄" ✅
- **구조적으로**: 표/번호/구분선 사용, 글 덩어리 금지
- **한국어로**: 도구 권한 요청도 한국어 | **작업 과정 먼저 설명** 후 실행

## Git 규칙
- `origin/main` 기준 새 브랜치: `claude/작업명` | 마지막 커밋 `[완료]` → 자동 머지
- 중간에도 수시 커밋+푸시 | 기존 브랜치에 무관한 작업 추가 금지

## 파일 수정 규칙
- `web/templates/index.html` — Write 전체 덮어쓰기 절대 금지 → Edit 부분 수정만

## 🔴 토큰 절약 — 도구 사용 우선순위
- 파일 탐색: **Glob/Grep 직접 사용** 우선. Task 툴(서브에이전트)은 직접 검색 3회 이상 실패 시에만
- `project-status.md`는 최근 2주 기록만 유지. 이전 내용은 `docs/archive/project-status-archive.md`로 이관

## 🔴 모델 선택 — 소네트 vs 오퍼스 (매 작업 시 추천 필수!)

**작업 시작 시 반드시 추천 모델 먼저 말할 것.**

| 소네트로 충분 ✅ | 오퍼스 필요 🔴 |
|----------------|--------------|
| 버그 수정 (원인 명확) | 아키텍처 설계 (새 시스템 구조 결정) |
| 문서 작성/업데이트 | 복잡한 멀티에이전트 디버깅 |
| 코드 추가 (패턴 명확) | 여러 요인이 충돌하는 판단 |
| 로그 모니터링/분석 | 비용 큰 설계 결정 (되돌리기 어려운 것) |
| 파일 이동/정리 | "왜 이게 안 되지?" 원인 불명 버그 |
| 알려진 API 연동 | 새로운 알고리즘 설계 |
| 단순 질문/논의 | 논문/복잡한 개념 분석 |

**기본값: 소네트.** 위 오퍼스 조건 해당 시에만 오퍼스 추천.

**1M 컨텍스트 필요 여부도 함께 말할 것:**
- 1M 필요: 3,000줄+ 파일 전체 분석, 대규모 리팩토링, 여러 모듈 동시 추적
- 1M 불필요(200K 충분): 단일 파일 수정, 단순 버그, 문서, 로그 분석

## 🔴 에이전트 구조 개편 (2026-02-25 확정)

### 새 조직 (6명)
| 역할 | 새 이름 | 구 이름 |
|------|--------|--------|
| 비서실장 | 비서실장 | 동일 |
| 투자분석 | **금융분석팀장** | CIO(투자분석처장) |
| 법무 | **법무팀장** | CLO(법무처장) |
| 사업기획 | **전략팀장** | CSO(사업기획처장) |
| 마케팅 | **마케팅팀장** | CMO(마케팅처장) |
| 출판·기록 | **콘텐츠팀장** | CPO(출판처장) |

### 전문가급
- soul/yaml 보존 (회사 자산), UI에서는 제거
- 재도입 시점: 팀장 혼자 30분+ + 병렬이 실제로 의미 있을 때
- **그 시점이 오면 명시적으로 조언.** 매 작업마다 언급 금지.

### 리팩토링 필요 시점 조언
- arm_server.py 또는 핵심 파일이 **3,000줄 초과** 시 → 세션 시작 "오늘 할 일" 논의 때 리팩토링 BACKLOG 추가 언급
- 단, 매 작업마다 언급 금지. 줄수 초과 시에만.

## 🔴 외부 API — 반드시 최신 문서 검색 후 코딩!
- 모든 외부 API 코드 작성/수정 시 WebSearch로 최신 공식 문서 확인. 기억 의존 금지
- KIS: [API 포털](https://apiportal.koreainvestment.com) | Anthropic: [Extended Thinking](https://docs.claude.com/en/docs/build-with-claude/extended-thinking)

## 🔴 GitHub Secrets — 전부 등록됨! 다시 물어보지 마!
- 50+ 시크릿 등록 완료. "키가 없어요" 금지. deploy.yml → `/home/ubuntu/corthex.env` 자동 반영
- **전체 목록**: `docs/claude-reference.md` 참조

## UI/UX 규칙
- 한국어 | KST | Tailwind + Alpine.js | `hq-*` 컬러 토큰
- **폰트**: Pretendard + JetBrains Mono 2개만. 새 Google 폰트/`font-sans` 오버라이드 금지

## 🔴 웹 성능 코딩 규칙
1. CDN 라이브러리는 `_loadScript()` 동적 로드만. blocking `<script>` 금지
2. 새 탭은 `<template x-if>` 필수 (x-show는 home/command/schedule/knowledge만)
3. init()에 API 추가 금지 → `switchTab()` lazy load
4. 폰트 추가 금지 | CSS @import 금지 → preload
5. SSE 1개만 (`_connectCommsSSE()`) | setInterval은 탭 진입/이탈 관리

## 🔴 매매 설정 — 건드리지 마!
- `order_size: 0` = CIO 비중 자율 (정상!). 0을 다른 값으로 바꾸지 말 것

## 하드코딩 금지
- 모델명 정의: `config/agents.yaml` + `config/models.yaml` 2곳만. 코드에 직접 쓰기 금지
- **모델 변경 시 10곳 체크리스트 + 실제 모델 목록**: `docs/claude-reference.md`

## 데이터 저장
- SQLite DB(`settings` 테이블)에 저장. JSON 파일 금지 (배포 시 날아감)
- `save_setting()` / `load_setting()` | DB: `/home/ubuntu/corthex.db` (git 밖)

## 서버 배포
- Oracle Cloud ARM 4코어 24GB (춘천, Always Free) | `corthex-hq.com` (Cloudflare)
- 자동: `[완료]` push → auto-merge → deploy.yml → SSH → `git fetch + reset --hard`
- 서버에서 `git pull` 금지! | **상세**: `docs/claude-reference.md`, `docs/deploy-guide.md`

## 빌드/버전
- 빌드: `deploy.yml` `run_number` | 확인: `gh run list --workflow=deploy.yml --limit=1`
- 대표님 보고 시 **"빌드#N"** | 버전: `X.YY.ZZZ` (현재 `4.00.000`)

## 디버그 URL
- 버그 시 `/api/debug/xxx` 즉석 생성 → 대표님에게 URL 제공 | 계좌번호 마스킹, API 키 노출 금지

## AI 도구 자동호출
- `ai_handler.py` `ask_ai()` → 3개 프로바이더 도구 자동호출 | 스키마: `config/tools.yaml`
- 🔴 루프 횟수 제한 없음! 로그 `(23회)` = 도구 호출 횟수 표시 (제한 없음)

---
# 🚨🚨🚨 작업 완료 6단계 — 전부 안 하면 미완성! 🚨🚨🚨

> **이거 안 지키면 미완성이다. 커밋했다고 끝이 아니다. 6단계 전부.**

## ① docs/updates/날짜_요약.md 작성
## ② docs/project-status.md 업데이트
## ③ docs/todo/날짜.md 갱신
## ④ 🔴🔴🔴 docs/todo/BACKLOG.md 갱신 — 빼먹으면 미완성!!! 🔴🔴🔴

> **매 배포마다 반드시!** 완료 항목 ✅ 표시, 새 발견 항목 추가, "마지막 업데이트" 날짜+빌드 갱신.
> 이거 안 하면 다음 세션에서 이미 끝난 걸 또 하고, 발견된 버그를 잊어버린다.

## ⑤ 커밋 메시지 `[완료]` → 자동 머지 → 배포 확인

```
gh run list --workflow=deploy.yml --limit=1
```
→ **빌드번호(#N) 확인 후 대표님에게 반드시 보고**

## ⑥ 대표님 최종 보고 (이 형식으로!)

```
✅ 작업 완료 — 빌드#N 배포됨
바뀐 것:
- [변경사항 1]
- [변경사항 2]
확인 방법: https://corthex-hq.com/[해당경로]
```

> 버그 발견 시 전부 기록 (✅/🔴). 심각하면 🚨 즉시 보고
> 팀장 최종 기록 책임 | 전수검사: `docs/inspection-protocol.md`

## 🚨🚨🚨 Phase별 대형 작업 = 매 Phase마다 compact 대비! 🚨🚨🚨
> **리팩토링/대형 플랜처럼 여러 Phase로 나뉜 작업 시:**
> **1 Phase 끝날 때마다** → ① project-status.md ② BACKLOG.md ③ todo/날짜.md 전부 갱신
> **그래야 /compact 해도 다음 Phase를 바로 이어갈 수 있다!**
> compact 안 하고 2~3 Phase 연속 → 컨텍스트 폭발 → 실수 확률 급증

---

## 🔴 TODO 관리 — B안 구조 (2026-02-26 확정)
- **`docs/todo/BACKLOG.md`** ← 미완료 전부 여기만. ⬜ 이관-복붙 금지
- **`docs/todo/YYYY-MM-DD.md`** ← 오늘 완료한 것만 기록 (⬜ 남기기 금지)
- 대형 작업: `날짜_프로젝트명.TODO.md` | 상태: ⬜ 대기 / 🔄 진행중 / ✅ 완료 / 🔴 블로킹
- 🔴 **맥락 필수!**: 왜 필요한지 + 어떤 상황 + 구체적 현상까지 기록. 한 줄짜리 금지
- 🔴 **수시 업데이트**: 작업 중 완료 항목 발견 즉시 BACKLOG.md 체크. 배포 시만 갱신 금지
- 🔴🔴🔴 **배포 = BACKLOG 갱신 필수!** 위 6단계 ④번. 안 하면 미완성!!!

## 에이전트 소울
- 로드: ①`config/agents.yaml` system_prompt → ②`souls/agents/*.md` 폴백 | 웹 수정 불가

## 참조 문서
- `docs/corthex-vision.md` — CORTHEX 비전 (반드시 참조)
- `docs/ceo-ideas.md` — 대표님 아이디어 로그 (**아이디어/버그 발견 시 자동 업데이트**)
- `docs/monetization.md` — 수익화 | `docs/defining-age.md` — "Defining Age" 패러다임
- 리트마스터: https://github.com/kodonghui/leet-master

## 서버 우선 원칙
- 기계적 처리(태그, 형식 검증)는 서버 코드(`arm_server.py`). 에이전트는 "생각하는 일"에 집중

## 🔴 새 기능 구현 — 반드시 최신 레퍼런스 분석 후 착수!

**"그냥 만들기" 금지. 구현 전에 반드시 이 순서:**

1. **최신 업계 표준 검색**: WebSearch로 "best practices [기능명] 2026" 검색
   - 예: 다이어그램 툴 만들기 → Mermaid Live Editor / Excalidraw / draw.io 구조 분석
   - 예: 대시보드 만들기 → Linear / Notion / Vercel 대시보드 UX 패턴 분석

2. **오마주 분석 3단계**:
   - ① **무엇이 좋은가**: 레이아웃 / UX 패턴 / 인터랙션 / 데이터 구조
   - ② **왜 좋은가**: 사용자 인지 부하 감소 / 빠른 탐색 / 시각적 위계
   - ③ **어떻게 빌릴 건가**: 기술 스택 제약(Alpine.js + Tailwind) 내에서 재현

3. **결과물 기준**: "이 업계 도구와 비교해도 손색없다" 수준

**구체적 체크리스트:**
- 레이아웃: 동일 카테고리 최고 앱 3개 스크린샷 분석 후 차용
- 인터랙션: 드래그/줌/호버/단축키 — 사용자가 이미 아는 패턴 재사용
- 정보 밀도: 한 화면에 필요한 것만 (Notion 수준 미니멀 vs Figma 수준 고밀도)
- 에러 처리: 빈 상태(Empty State) / 로딩 스켈레톤 / 에러 메시지 UX 참조

> 상세 레퍼런스 목록: `docs/ux-references.md` (누적 업데이트)

## 🚨🚨🚨 다이어그램 — HTML 뷰어 필수! mermaid .md만 주면 미완성! 🚨🚨🚨
- **다이어그램/플로우차트 생성 시 반드시 3벌**:
  1. **`.md` 파일** — mermaid 코드 포함 (`docs/architecture/이름.md`)
  2. **`.html` 파일** — 브라우저에서 바로 열리는 뷰어 (`docs/architecture/이름.html`) ← **필수!**
  3. **대표님에게**: 아래 열기 방법 + "Ctrl+스크롤로 확대됩니다" 반드시 안내
- **로컬 HTML 전달 시 반드시 `file:///` URL로 제공** (크롬 주소창에 바로 붙여넣기 가능):
  - 형식: `file:///C:/Users/elddl/Desktop/PJ0_CORTHEX/CORTHEX_HQ/CORTHEX_HQ/docs/architecture/파일명.html`
  - 경로만 주면 안 됨. `file:///` 붙인 전체 URL로 줄 것.
- **html 없으면 미완성**: .md만 주면 VSCode 프리뷰에서 다이어그램이 너무 작아 읽을 수 없음
- **html 규칙**: mermaid.js CDN + dark 테마 + `useMaxWidth: false` + 섹션별 카드 레이아웃
- 참고 예시: `docs/architecture/tool-server-flow.html`
- 아키텍처 문서: `docs/architecture/` | 설계 결정 참조: `docs/ceo-ideas.md`

## 워크플로우 예측 (대표님 발명)
- 새 기능 → 코드 전수검사 → 워크플로우 예측 → 선제 보강 → 실제 테스트 → 로그 비교
- 저장: `docs/workflow-predictions/` | 상세: `docs/methodology/workflow-prediction.md`

## 노션 연동
- API `2022-06-28` (2025 금지). DB ID/Integration 상세: `docs/claude-reference.md`

## 기타
- TodoWrite로 진행 표시 (3개+ 작업 시). in_progress 1개만
- gh CLI 없으면 세션 시작 시 설치
- CLAUDE.md 수정 시: 간략하게, 중복 검사, 예시는 별도 파일. **200줄 이내 유지**

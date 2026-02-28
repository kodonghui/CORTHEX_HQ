# CORTHEX HQ - 프로젝트 현재 상태

> **목적**: 새 세션 시작 시 현재 상태 즉시 파악용. 매 작업 완료 시 업데이트.
> **아카이브**: `docs/archive/project-status-archive.md` (2/20~2/23 기록)

---

## 마지막 업데이트

- **날짜**: 2026-02-28
- **버전**: `4.00.000`
- **빌드**: #710 (에이전트 CLI 전환 — API→CLI Max 구독)
- **서버**: https://corthex-hq.com

---

## 2026-02-28 — 에이전트 CLI 전환 (빌드 #708~#710)

### 핵심 변경
- **모든 Claude 호출을 API → CLI(Max 구독)로 전환** → 에이전트 메인 호출 비용 $0
- 구조: 에이전트 메인 호출 → CLI(무료) / 분류·QA·도구내부 → API(소량)
- 하루 예상 비용: ~$3~7 → **~$0.1~0.3**

### 새로 만든 것
- `src/mcp_tool_server.py` — MCP 프록시 서버 (경량, 도구 실행은 HTTP로 메인 서버에 위임)
- `web/ai_handler.py` — `_call_claude_cli()` 함수 + `_USE_CLI_FOR_CLAUDE` 플래그
  - 모든 Claude 호출 자동 CLI 라우팅 (use_cli 파라미터 불필요)
  - CLI 실패 시 자동 API 폴백
  - stdin으로 프롬프트 전달 (--tools variadic 옵션 충돌 방지)
- `web/arm_server.py` — `/api/internal/tool-invoke` 내부 엔드포인트
- `web/agent_router.py` — `use_cli=True`, `cli_caller_id`, `cli_allowed_tools` 전달

### MCP 도구 연동 구조
```
CEO 명령 → ask_ai(use_cli=True) → claude -p (CLI)
              ↓ (도구 필요 시)
         MCP 프록시 → HTTP POST /api/internal/tool-invoke → ToolPool.invoke()
```

### 비활성화 방법
`ai_handler.py` → `_USE_CLI_FOR_CLAUDE = False` → 즉시 API 모드로 복귀

---

## 2026-02-28 — SNS 퍼블리셔 전면 수정 (빌드 #704~#706)

### 발견된 버그 + 수정
- ✅ **venv selenium 미설치** → TistoryPublisher/DaumCafePublisher 임포트 실패. 수동 설치+서버 재시작
- ✅ **CMO allowed_tools 누락** → gemini_image_generator/gemini_video_generator 추가 (빌드 #704)
- ✅ **tools.yaml 스키마 누락** → sns_manager에 media_urls/extra/category/visibility 파라미터 추가 (빌드 #705)
- ✅ **인스타 이미지 발행 실패** → _wait_for_processing을 이미지에도 적용 + 3회 재시도 (빌드 #706)
- ✅ **티스토리 셀렉터 깨짐** → 10개 CSS 셀렉터 순차 시도 + JS 폴백 (빌드 #706)
- ✅ **미디어 탭 느림** → 썸네일 API (300x300 JPEG, 원본 1.1MB → 13KB 98%↓) (빌드 #706)

### SNS 4종 발행 테스트 결과
| 콘텐츠 | 플랫폼 | 결과 |
|--------|--------|------|
| 텍스트 | 티스토리 | ✅ 큐등록 성공 (발행은 셀렉터 이슈 → 수정 배포됨) |
| 이미지 | 인스타그램 | ✅ 큐등록+발행 (재시도 로직 추가) |
| 동영상(Veo 3.1) | 인스타 릴스 | ✅ 큐등록+발행 성공 |
| 카드뉴스 5장 | 인스타 캐러셀 | ✅ 큐등록+발행 성공 |

---

## 2026-02-28 — 카드뉴스 시리즈 생성기 (빌드 #701)

- ✅ `gemini_image_generator.py` — `card_news_series` action 추가 (~140줄)
  - `_generate_card_news_series()`: 5~10장 순차 생성, 실패 시 건너뛰기
  - `_build_card_news_slide_prompt()`: 표지/내용/마무리 타입별 프롬프트 + 시리즈 일관성 지시
  - `slides_text` 파라미터: 줄바꿈 구분으로 슬라이드별 텍스트 지정
  - SNS 발행용 `media_urls` 리스트 자동 출력 → sns_manager submit에 바로 사용
- ✅ `tools.yaml/json` — card_news_series action + slide_count/slides_text 파라미터 문서화
- 사용법: 마케팅팀장 → `gemini_image_generator(action=card_news_series, topic="...", slide_count=7)` → 이미지 7장 생성 → `sns_manager(action=submit, media_urls=[...])` → 대표님 승인 → Instagram 캐러셀 자동 발행

---

## 2026-02-28 — SNS 웹 승인+자동발행 구현

### 변경 내용
- ✅ **웹 "승인+발행" 1클릭** — approve 시 `asyncio.create_task(_auto_publish_after_approve)` 자동 발행
- ✅ `_get_publisher()` 헬퍼 추출 — 기존 publish_sns()와 자동발행이 공유
- ✅ 프론트엔드: "승인" → "승인+발행" 버튼, approved 상태에 "발행 진행중..." 애니메이션
- ✅ 5초/15초/30초 자동 새로고침 (Selenium 발행 대기)

### 완료된 발행 플랫폼
- ✅ **티스토리** — Selenium + 카카오 OAuth
- ✅ **다음카페(서로연)** — Selenium + 카카오 OAuth → TinyMCE
- ✅ **Instagram** — Graph API, 대표님 직접 발행 성공 확인
- 🔴 **네이버 블로그** — 봉인 (CAPTCHA 차단)

### 남은 작업
- ⬜ 텔레그램 승인 시에도 자동 발행 연결
- ⬜ submit 즉시 텔레그램 알림
- ⬜ 카드뉴스 생성기

### 개발 디렉토리 분리
- `/home/ubuntu/corthex-dev/` — 개발 전용 (Claude 작업)
- `/home/ubuntu/CORTHEX_HQ/` — 배포 전용 (서버 실행, 수정 금지)
- git push로 반영 → GitHub Actions 자동 배포

---

## 2026-02-28 — SketchVibe 새 캔버스 + 삭제 (빌드 #694)

- ✅ 초기화 시 Mermaid + Drawflow 동시 클리어
- ✅ 저장된 다이어그램 삭제: DELETE API + 사이드바 × 버튼

## 2026-02-28 — SketchVibe 캔버스 직접 렌더링 (빌드 #692)

- ✅ Mermaid 결과를 사이드 패널이 아닌 **캔버스 영역에 직접 렌더링** (스케치 교체 UX)
- ✅ 캔버스 오버레이: 상단 바(맞아/초기화 버튼) + Mermaid 풀스크린 렌더링
- ✅ SSE 자동 연결: NEXUS 탭 열 때 자동, 닫을 때 해제
- 대표님 피드백: "내가 그린거를 교체하는거라구" → 캔버스 위에 직접 표시

## 2026-02-28 — SNS 자동발행 리서치 (네이버 봉인 / 티스토리·다음카페 준비)

### 네이버 블로그 — 봉인 🔴
- Selenium 자동화 시도: ActionChains / JS injection / undetected-chromedriver / chromedriver cdc_ 패치
- **전부 실패** — 네이버가 헤드리스 브라우저 자체를 CAPTCHA로 차단
- 쿠키 로그인: naver.com OK → blog.naver.com 글쓰기 접속 시 세션 불일치로 재로그인 요구
- `sns_manager.py` ALLOWED_PLATFORMS에서 naver_blog 제거, BLOCKED 처리
- 재도전 조건: 데스크톱 환경 or Naver 내부 API 역공학 or Playwright stealth

### 티스토리 — ✅ 로그인 + 글쓰기 접근 성공
- 티스토리 Open API **2024년 2월 완전 종료**. Selenium만 가능
- 카카오 로그인 성공 (CAPTCHA 없음, 카카오톡 인증 1회 필요)
- 글쓰기 페이지 접근 성공: `editor-tistory_ifr` iframe, `tagText` 입력 확인
- 올바른 OAuth 플로우: 티스토리 로그인 → "카카오계정으로 로그인" → 카카오 OAuth → 콜백
- GitHub Secrets 업데이트 완료: `KAKAO_ID`, `KAKAO_PW`, `TISTORY_BLOG_NAME`
- **다음 단계**: 실제 테스트 글 발행 (카카오톡 인증 후 쿠키 재사용 가능 확인)

### 다음카페 — ✅ 로그인 + 카페 접근 성공
- 다음카페 API **2018년 종료**. Selenium만 가능
- 카카오 로그인 후 cafe.daum.net 접근 성공 (서로연 카페)
- **다음 단계**: 글쓰기 페이지 접근 + 실제 테스트 글 발행
- 참고: 다음은 업스테이지에 매각 중 (2026.01 MOU)

### 다음 검토 대상
- 페이스북 (Graph API 기반, Meta 개발자 계정 필요)
- X/트위터 (API v2, 유료 플랜 $100/월 필요할 수 있음)

---

## 2026-02-28 — SketchVibe Phase 3 (아키텍처 재설계 — 서버변환 제거 + MCP 양방향)

- ✅ 서버 변환 제거 — `/convert` 엔드포인트 삭제 (Claude API 직접호출 → Claude Code MCP로 이관)
- ✅ SSE 엔드포인트 5개 추가 — save-canvas, push-event, request-approval, approve, stream
- ✅ MCP 도구 2개 추가 — `update_canvas()`, `request_approval()` (기존 3도구 보존)
- ✅ 프론트엔드 전면 재설계 — "변환하기" → "저장하기", SSE 구독, 실시간 Mermaid 렌더링
- ✅ 팔레트 버그 수정 — 동일 ID 두 개 존재 시 보이는 요소 선택 + 노드 랜덤 위치
- ✅ API 비용 표시 제거 ($0.0079 등)
- ✅ NEXUS 분할뷰 + 시스템플로우 삭제 — 캔버스 모드만 유지, HTML 151줄 제거, 모드버튼 삭제
- ✅ HTML 뷰어 404 수정 — `/api/sketchvibe/viewer/{name}` 엔드포인트 (nginx 우회)
- ✅ 크롬 빈 캔버스 수정 — SSE 연결 시 최근 Mermaid 즉시 복원
- ✅ 새 창 제거 + 저장 캔버스 목록 — Mermaid 인라인 렌더링 + confirmed 다이어그램 사이드바 표시

## 2026-02-28 — SketchVibe Phase 2 (정확도 + MCP + 구현 브리지)

- ✅ `_parse_drawflow()` 강화 — 노드타입→Mermaid 형태, 레이아웃 자동판단(LR/TD), 공간 그룹→subgraph, 분기 포트 정보
- ✅ Claude 프롬프트 확장 — sequenceDiagram/stateDiagram/classDiagram 지원, 매핑표+예시 2개
- ✅ `web/mcp_sketchvibe.py` 신규 — FastMCP 서버 (read_canvas, list_confirmed, get_confirmed)
- ✅ `.mcp.json` — sketchvibe MCP 서버 등록
- ✅ confirmed API 2개 — `GET /confirmed`, `GET /confirmed/{name}` (SQLite 기반)
- ✅ "맞아" 후 구현 안내 패널 — MCP URI + HTML 뷰어 + 캔버스 JSON 전달
- ✅ 모델 하드코딩 수정 — `load_setting("sketchvibe_model")` 기반

## 2026-02-28 — 릴스 자동 발행 파이프라인 (빌드 #675)

- ✅ `instagram_publisher.py` — `_resolve_media_url()` 추가 (상대→절대 URL 변환)
- ✅ 영상 생성기 2개 — 퍼블릭 URL 반환 추가
- ✅ **미디어 도구 8개 경로 버그 수정** — `os.getcwd()` → `__file__` 기반 절대경로 통일
- ✅ output/ 디렉토리 구조 + .gitkeep + .gitignore 정리

## 2026-02-28 — SketchVibe MVP 구현

- ✅ `web/handlers/sketchvibe_handler.py` 신규 (~230줄) — 변환/캔버스조회/저장 API 3개
- ✅ `web/arm_server.py` — sketchvibe_router 마운트
- ✅ `web/static/js/corthex-app.js` — 데이터 변수 5개 + 메서드 4개 (+128줄)
- ✅ `web/templates/index.html` — 토글 버튼 + 스케치바이브 패널 (+100줄)
- 파이프라인: 캔버스 스케치 + 자연어 → Claude → Mermaid 변환 → 확인 → .md/.html 저장
- UX: 타입 선택 없음(AI 자동 판단), 캔버스 모드 내 슬라이드 패널
- MCP: REST API `/api/sketchvibe/canvas`로 대체, 별도 MCP 서버는 Phase 2

## 2026-02-28 — Instagram 자동 발행 기능 추가

- ✅ `instagram_publisher.py` — OAuth→환경변수 토큰 전환 + User ID 자동 조회
- ✅ `sns_manager.py` — Instagram 잠금 해제 (ALLOWED_PLATFORMS + import 활성화)
- ✅ `agents.yaml` CMO — 지원 플랫폼 4→5개, Instagram 활성화
- ✅ `tools.yaml/json` — sns_manager 설명 업데이트
- ✅ 나노바나나 v2 교체 완료 (빌드 #673)

## 2026-02-28 (sketchvibe 세션)

- agents.yaml 모델/추론 업데이트 (비서실장 low, 사업기획 medium 등)
- Instagram 연동 준비: Meta 앱 + 토큰 발급 + GitHub Secrets 등록
- 스케치바이브 설계 전체 확정: `docs/todo/스케치바이브_아이디어.md`
  - 캔버스: Nexus Drawflow 재활용 확정
  - 전달: Claude MCP 서버
  - UX: 타입 선택 UI 없음, AI 자동 판단
  - MVP: Phase 1+2 둘 다, 별도 세션에서 개발
  - 개발 프롬프트 작성 완료 (대표님에게 전달됨)
- BACKLOG.md 스케치바이브 개발 항목 추가
- 상세: `docs/updates/2026-02-28_스케치바이브논의.md`

---

## ✅ BACKLOG 전체 소탕 — 완료 (빌드 #655)

KIS 버그 수정 + pricing 도구 합병 + 고객분석 도구 합병 + src/src 중복 정리.
249파일 변경, 70,240줄 삭제. 상세: `docs/updates/2026-02-27_BACKLOG소탕.md`

---

## ✅ arm_server.py 리팩토링 — 4-3 (P9 완료, 리팩토링 종료)

> **비유**: 11,637줄짜리 거대한 공장 1동 → 9개 전문 모듈로 분리 완료.

### 현재 상태

- **파일**: `web/arm_server.py` — **1,075줄** (P9 후, 91% 감소)
- **P1 완료**: `web/config_loader.py` 343줄 분리 (빌드 #656)
- **P2 완료**: `web/handlers/debug_handler.py` 591줄 분리 (빌드 #658)
- **P3 완료**: `web/handlers/argos_handler.py` 505줄 분리 (빌드 #659)
- **P4 완료**: `web/argos_collector.py` 1,026줄 분리 (빌드 #660)
- **P5 완료**: `web/batch_system.py` 1,808줄 분리 (빌드 #663)
- **P6 완료**: `web/trading_engine.py` 2,830줄 분리 (빌드 #665)
- **P7 완료**: `web/scheduler.py` 508줄 분리 (빌드 #667)
- **P8 완료**: `web/agent_router.py` 2,500줄 분리 (에이전트 라우팅/QA/노션/도구풀)
- **P9 완료**: `web/telegram_bot.py` 797줄 분리 (텔레그램 봇 전체)
- **등급**: D등급 → B등급 (God Object 완전 해소, 10,562줄 감소, 91%)

### 15개 논리 모듈 식별

| # | 모듈 | 줄수 | 함수 | 결합도 | 추출 난이도 |
|---|------|------|------|--------|-----------|
| 1 | 유틸리티+초기화 | 210 | 4 | 없음 | 🟢 쉬움 |
| 2 | 설정+데이터 로딩 | 1,200 | 13 | yaml,db | 🟢 쉬움 |
| 3 | WebSocket/SSE | 190 | 5 | ws_manager | 🟢 쉬움 |
| 4 | Soul Gym | 161 | 3 | ai_handler | 🟢 쉬움 |
| 5 | 도구 관리 | 194 | 3 | app_state | 🟢 쉬움 |
| 6 | 대시보드 API | 108 | 5 | 읽기 전용 | 🟢 쉬움 |
| 7 | 디버그 API | 338 | 11 | 진단용 | 🟢 쉬움 |
| 8 | ARGOS 수집 | 4,161 | 25 | 외부 API | 🟡 보통 |
| 9 | 배치 시스템 | 1,235 | 15 | agent callback | 🟡 보통 |
| 10 | 배치 체인 | 1,218 | 10 | 비동기 상태머신 | 🟡 보통 |
| 11 | 스케줄링/크론 | 1,836 | 10 | 전 모듈 참조 | 🔴 어려움 |
| 12 | 트레이딩/CIO | 4,333 | 31 | ARGOS↔순환 | 🔴 어려움 |
| 13 | 텔레그램 봇 | 4,705 | 7 | 허브 패턴 | 🔴 어려움 |
| 14 | **에이전트 라우팅** | **1,865** | **25** | **핵심 허브** | 🔴🔴 가장 어려움 |
| 15 | 라이프사이클 | 85 | 2 | 전체 조율 | 🟡 보통 |

### 핵심 의존성 (순환 참조 3곳)

| 함수 | 호출 횟수 | 영향 범위 |
|------|---------|---------|
| `ask_ai()` | 33곳 | 에이전트/배치/트레이딩/Soul Gym 전부 |
| `save_activity_log()` | 91곳 | 전 모듈 (시스템 로깅) |
| `update_task()` | 53곳 | 배치/스케줄링/트레이딩/에이전트 |
| `_call_agent()` | 22곳 | 배치/트레이딩/에이전트 라우팅 |

**순환 참조**:
- ARGOS ↔ 트레이딩 (가격 수집 ↔ 매매 신호)
- 크론 ↔ 전 모듈 (크론이 전부 호출, 전부가 크론에 등록)
- 에이전트 라우팅 ↔ 텔레그램 (에이전트→알림, 텔레그램→에이전트 호출)

### 8단계 추출 계획

> 원칙: **독립적인 것부터, 결합도 높은 것은 나중에**
> Phase마다 커밋+배포+검증 후 다음 진행
>
> 🚨🚨🚨 **매 Phase 완료 후 반드시 /compact 대비!** 🚨🚨🚨
> Phase 1개 끝날 때마다: ① 이 문서 업데이트 ② BACKLOG 갱신 ③ todo 날짜파일 갱신
> → 그래야 다음 Phase 시작 전 compact해도 맥락 안 잃음!
> **compact 안 하고 2~3 Phase 연속 돌리면 컨텍스트 폭발 → 실수 확률 급증**

| Phase | 추출 대상 | 목표 파일 | 예상 줄수 | 난이도 |
|-------|----------|---------|---------|--------|
| **P1** | ✅ 유틸+설정+라이프사이클 | `web/config_loader.py` (343줄) | 294줄 감소 | 🟢 완료 |
| **P2** | ✅ 디버그 API (Soul Gym/도구는 이미 분리됨) | `handlers/debug_handler.py` (591줄) | 515줄 감소 | 🟢 완료 |
| **P3** | ✅ ARGOS API (WebSocket은 결합도 높아 보류) | `handlers/argos_handler.py` (505줄) | 429줄 감소 | 🟢 완료 |
| **P4** | ✅ ARGOS 수집 (16함수+컨텍스트빌더) | `web/argos_collector.py` (1,026줄) | 963줄 감소 | 🟢 완료 |
| **P5** | ✅ 배치 시스템+체인 (10개 API + 4단계 체인) | `web/batch_system.py` (1,808줄) | 1,760줄 감소 | 🟢 완료 |
| **P6** | ✅ 트레이딩/CIO (6개 API + 정량분석 + 자동매매) | `web/trading_engine.py` (2,830줄) | 2,728줄 감소 | 🟢 완료 |
| **P7** | ✅ 스케줄링/크론 (1 API + 크론엔진 + Soul Gym루프) | `web/scheduler.py` (508줄) | 439줄 감소 | 🟢 완료 |
| **P8** | ✅ 에이전트 라우팅 | `web/agent_router.py` (2,500줄) | 2,666줄 감소 | 🔴🔴 완료 |
| **P9** | ✅ 텔레그램 봇 | `web/telegram_bot.py` (797줄) | 768줄 감소 | 🟡 완료 |

### 아키텍처 패턴

- **Dependency Injection**: `on_startup()`에서 콜백 등록 (하드코딩 import 금지)
- **이벤트 버스**: 텔레그램은 이벤트 구독 (직접 호출 금지)
- **팩토리 패턴**: 크론 작업은 레지스트리 등록 방식
- **순환 해소**: ARGOS↔트레이딩은 데이터를 인자로 전달 (직접 import 금지)

### 최종 목표 구조

```
web/
├─ arm_server.py          (300~400줄, thin main + 라우터 마운트만)
├─ config_loader.py       (설정 로딩, DB 영속, 초기화)
├─ agent_router.py        (에이전트 라우팅, ask_ai, _call_agent)
├─ argos_collector.py     (ARGOS 데이터 수집 전체)
├─ trading_engine.py      (매매 엔진, 시그널, 주문)
├─ batch_system.py        (배치 시스템 + 배치 체인)
├─ scheduler.py           (크론 스케줄러)
├─ soul_gym.py            (Soul Gym 진화)
├─ ws_handler.py          (WebSocket/SSE)
├─ dashboard_api.py       (대시보드 API)
├─ debug_api.py           (디버그 엔드포인트)
├─ tool_mgr.py            (도구 풀 관리)
└─ (기존) ai_handler.py, kis_client.py, ...
```

### ⚠️ 리스크

- 🔴 **에이전트 라우팅** (ask_ai 33곳 호출) — 가장 마지막에, 가장 신중하게
- 🔴 **ARGOS↔트레이딩 순환** — DI 패턴으로 해소 필요
- 🟡 **크론 스케줄러** — 전 모듈 의존, 팩토리 패턴 필수
- 🟢 **P1~P3은 안전** — 독립적, 기계적 분리

---

## 2026-02-28 — arm_server.py 리팩토링 P9 (텔레그램 봇 분리)

- ✅ `web/telegram_bot.py` 신규 (797줄) — CEO 텔레그램 인터페이스 전체
  - 명령 핸들러 12개 + 모델 선택 3단계 버튼
  - 한국어 AI 명령 (/토론, /심층토론, /전체, /순차)
  - 웹 응답 텔레그램 전달 (_forward_web_response_to_telegram)
- ✅ arm_server.py 1,843→1,075줄 (768줄 감소)
- ✅ P8 버그 수정: _NOTION_API_KEY 미임포트 → os.getenv 직접 호출
- ✅ **리팩토링 최종**: 11,637→1,075줄 (10,562줄 분리, 91%), D등급→B등급

## 2026-02-28 — arm_server.py 리팩토링 P7 (빌드 #667)

- ✅ `web/scheduler.py` 신규 (508줄) — 크론 엔진 + 워크플로우 실행 + Soul Gym 루프
  - 크론 표현식 파서/매처 (5필드 리눅스 표준)
  - 1분 주기 크론 루프 (ARGOS 수집, 환율 갱신, 가격 트리거, 사용자 예약)
  - 기본 스케줄 자동 등록 (CIO 일일/주간)
  - 워크플로우 순차 실행 + WebSocket 진행 알림 (1 API)
  - Soul Gym 24/7 상시 진화 루프
  - `start_background_tasks()`: on_startup 스케줄링 부분 통합 (11개 백그라운드 태스크)
- ✅ arm_server.py 4,948→4,509줄 (439줄 감소)
- ✅ 서버 배포 + 헬스체크 + 11개 백그라운드 태스크 전부 시작 확인
- 📌 **다음: P8** — 에이전트 라우팅 추출 (가장 어려움, 오퍼스 추천)

## 2026-02-28 — arm_server.py 리팩토링 P6 (빌드 #665)

- ✅ `web/trading_engine.py` 신규 (2,830줄) — CIO 신뢰도 학습 + 자동매매 + 정량분석
  - 6개 API 엔드포인트 trading_router로 이관
  - CIO 학습: ELO + Bayesian 보정 + 도구 효과 + 오답 패턴
  - 정량분석: RSI/MACD/볼린저/거래량/이평선 합의투표
  - 자동매매: 가격 트리거 + 손절/익절 + 봇 루프 + DST 감지
- ✅ arm_server.py 7,676→4,948줄 (2,728줄 감소)
- ✅ 서버 배포 + 헬스체크 + 트레이딩 API 검증 정상
- 📌 **다음: P7** — 스케줄링/크론 추출

## 2026-02-28 — arm_server.py 리팩토링 P5 (빌드 #661)

- ✅ `web/batch_system.py` 신규 (1,808줄) — 배치 큐 + AI Batch API + 배치 체인 4단계 오케스트레이터
  - 10개 API 엔드포인트 batch_router로 이관
  - 분류 → 팀장 지시서 → 전문가 배치 → 종합 보고서 (4단계 파이프라인)
  - 배치 폴러, 브로드캐스트 모드, 실시간 폴백
- ✅ arm_server.py 9,436→7,676줄 (1,760줄 감소)
- ✅ 서버 배포 + 배치 API 3종 검증 (queue/chains/pending 정상)
- 📌 **다음: P6** — 트레이딩/CIO 추출

## 2026-02-28 — arm_server.py 리팩토링 P4 (빌드 #660)

- ✅ `web/argos_collector.py` 신규 (1,026줄) — ARGOS 수집 16함수 + 컨텍스트 빌더
- ✅ arm_server.py 10,399→9,436줄 (963줄 감소)
- ✅ argos_handler.py 스텁 7개 → argos_collector 직접 import로 교체
- ✅ 서버 배포 + ARGOS 수집 동작 검증 정상

---

## 2026-02-27 — arm_server.py 리팩토링 P1 (빌드 #656)

- ✅ `web/config_loader.py` 신규 (343줄) — _log, _load_env_file, _load_config, _load_data, _build_agents_from_yaml, AGENTS, KST, 디렉토리 상수, MODEL_*_MAP
- ✅ arm_server.py 11,637→11,343줄 (294줄 감소)
- 📌 **다음: P2** — Soul Gym + 디버그 API + 도구관리 추출

---

## 2026-02-27 — BACKLOG 소탕 (빌드 #655)

- ✅ KIS `EXCG_ID_DVSN_CD` "" → "KRX" (한미반도체 주문 실패 해결)
- ✅ pricing 도구 합병 (sensitivity 612줄 삭제, optimizer에 Gabor-Granger+수익최적화 이식)
- ✅ 고객분석 도구 합병 (cohort_analyzer 413줄 삭제, ltv_model에 RFM+CAC 이식)
- ✅ src/src/ 중복 디렉토리 425파일 정리 (70,240줄 삭제)

## 2026-02-27 — 도구 전수 심사 + 서버 사전계산 아키텍처 (빌드 #650)

> **핵심**: 141개 도구 코드 전수 분석 → 4분류 → 금융팀장 도구 호출 44회→0회

- ✅ **141개 도구 전수 심사** — Opus 3개 에이전트 병렬 코드 분석 (교수급 48 / 실용급 65 / 오합지졸 1)
- ✅ **4분류 체계 확립** — 🟢서버실시간(ARGOS) / 🔵서버스폰(pool.invoke) / 🟡AI직접 / ⛔삭제
- ✅ **쓰레기 도구 4개 삭제** — newsletter_builder, dc_lawschool_crawler, orbi_crawler, rfm_segmentation
- ✅ **CIO 서버 사전계산 8개** — technical_analyzer→quant_section, dcf_valuator+risk_calculator→dcf_risk_section, correlation_analyzer+portfolio_optimizer_v2→STEP2 강제 실행
- ✅ **CIO allowed_tools 18개 제거** — ARGOS 대체 10개 + 서버 사전계산 8개 → AI 도구 호출 44회→0회
- ✅ **도구 분류 마스터 문서** — `docs/architecture/tool-classification.md` 대문짝만하게 작성
- 📌 **분류 마스터 문서**: `docs/architecture/tool-classification.md`
- 📌 **심사 상세**: `docs/architecture/tool-audit.md`

## 2026-02-27 — ARGOS C안 구현 (빌드 #642~647)
- ✅ **금융분석팀장 실시간 도구 10개 제거** — 서버 수집 데이터만 사용 (40분→정상)
- ✅ **thinking type 버그 수정** — adaptive→enabled (400 에러 해결)
- ✅ **technical_analyzer divide-by-zero** 수정
- ✅ **ARGOS 매크로 확장** — S&P500·NASDAQ·미국10년물·한국기준금리 추가 (11건)
- ✅ **ARGOS 재무지표 수집** — pykrx PER/PBR/EPS/BPS, KR 7개 종목 (7건)
- ✅ **ARGOS 업종지수 수집** — pykrx 11개 업종, 8건 수집 완료
- ✅ **collect/now API** — financial·sector 즉시수집 타입 추가

## 2026-02-27 — 버그 수정 + Phase 5 일괄 구현
- ✅ **R-3: 전력분석 데이터 누락** — update_task()에 agent_id 추가 (6곳)
- ✅ **R-5: 레이스컨디션** — ARGOS/Soul Gym bool→asyncio.Lock + state.py bg_lock/batch_lock
- ✅ **5-1: NEXUS 2D 분할뷰** — 3D 제거, Mermaid+Canvas 분할 레이아웃
- ✅ **5-2: Soul Gym 6팀장 확장** — benchmarks.yaml + 엔진 전면 개편 (팀장별 맞춤 벤치마크 3문항)
- ⬜ **4-3: arm_server.py 리팩토링** — 계획 수립 완료, 실행 보류 (대형 작업)

## 2026-02-26 추가 완료 (세션 5 — Phase 6 Final)
- ✅ **R-2: 작전일지 제목 요약** — `_extract_title_summary()` 마크다운 헤더/첫 문장 추출
- ✅ **N-1: 도구 137개 4분류** — API(62)/LLM(52)/LOCAL(18)/STUB(5), tools.yaml category 필드
- ✅ **N-2: NEXUS mermaid 플로우차트** — 3D+mermaid+캔버스 3모드 전환
- ✅ **N-6: 작전현황↔대시보드 역할 명시** — 상호 링크 + 부제 추가
- ✅ **N-7: 왼쪽바 도구함 카테고리** — 4그룹 컬러 분류 (초록/시안/보라/회색)
- ✅ **N-8: AGORA 독립 viewMode** — 지휘소 탭→상단 토글 분리
- ✅ **N-9: 보고서 QA 반려/재작성** — DB 3컬럼 + API + UI 섹션 반려
- ✅ **N-10: 모바일 반응형 전수** — grid 12개소 + 팝업/패널 반응형
- ✅ **N-11: 통신로그+전략실 타임라인 UX** — 세로선+도트+접이식 카드
- ✅ **R-5: 동시 명령 큐** — 코드 리뷰 정상 확인 (수정 불필요)
- ✅ **브랜치 정리** — 머지 완료 브랜치 25개+ 삭제 (로컬+원격)

## 2026-02-26 추가 완료 (세션 4)
- ✅ **아이폰 14 모바일 최적화** — 390×844px 뷰포트 전수 최적화
  - CSS: `<480px` 미디어쿼리에 iPhone 14 전용 규칙 추가 (카드/패딩/폰트 조정)
  - 명령 입력 드롭다운: `w-96`(384px 고정) → `w-full max-w-96`(반응형)
  - 입력바: Batch 토글 텍스트 모바일 숨김, 배치 배너 상단 분리, gap 축소
  - 사무실 뷰: `grid-cols-3` → `grid-cols-2 sm:grid-cols-3`, 고정 너비 카드 반응형
  - 보관함: 2단→1단(모바일), `min-w-[280px]` → `sm:min-w-[280px]`
  - 작전계획: 요약 스탯 `grid-cols-4` → `grid-cols-2 sm:grid-cols-4`
  - 에이전트 설정 모달: 5탭 가로 스크롤 가능, 텍스트 축소

## 2026-02-26 추가 완료 (세션 3)
- ✅ `read_knowledge` 도구: knowledge/ on-demand 조회 (LLM 호출 없음, 토큰 절약)
- ✅ `knowledge/leet_master/product_info.md` GitHub 저장소 기반 완전 작성
- ✅ 5개 팀장 allowed_tools에 read_knowledge 추가 (전략/법무/마케팅/금융분석/콘텐츠)
- ✅ **ARGOS↔도구 6중 중복 해결** — 5개 도구에 ARGOS DB 캐시 우선 읽기 추가 (PR#621)
- ✅ **ARGOS 수집 타임아웃 수정** — per-ticker 20s, 7/3일 단축, 순차 수집 (PR#624-625)
- ✅ **R-1**: 대화 비우기 PATCH 응답 확인 + DELETE 폴백 추가
- ✅ **R-4**: 통신국 ".env" 오해 유발 텍스트 → "서버 환경변수" 수정
- ✅ **R-6**: 장기기억 "기억" 버튼 크기 개선 + 안내 텍스트 추가
- ✅ **N-3**: 정보국 드래그앤드롭 파일 업로드 (파일 트리에 드롭 → 자동 업로드)
- ✅ **N-4**: 진화시스템 웹 실시간 로그 (SSE/WebSocket + REST API + 전력분석 탭 패널)
- ✅ **N-5**: 피드백 모드 피그마급 (prompt()→클릭 핀+말풍선+인라인 입력+핀 목록)
- ✅ **CIO→팀장 명칭 35곳 정리** — config/agents.yaml, tools.yaml 등 주석·문자열만

---

## 🔴 전수검사 + 정비 마스터 플랜 (대표님 승인 2026-02-25)

> **원칙**: 새 기능 추가 전에 지금 있는 것부터 제대로 고친다.

### Phase 0 — 즉시 수정

| # | 내용 | 파일 | 상태 |
|---|------|------|------|
| 0-1 | **CIO 보고서 잘림** — max_tokens에 thinking budget 포함 → 응답 384토큰만 남음. `max_tokens = budget + 16384`로 수정 | `web/ai_handler.py` | ✅ |
| 0-2 | **Soul Evolution 자동 승인** — 제안 즉시 auto_approved + 소울 업데이트 + warnings 초기화 | `web/handlers/soul_evolution_handler.py` | ✅ |
| 0-3 | **Soul Gym 24/7 상시 운영** — `_soul_gym_loop()` 5분 간격 상시 루프. 비용: 라운드당 ~$0.012 | `web/arm_server.py` | ✅ |
| 0-4 | **conversation_id 전달 버그** | `web/arm_server.py` | ✅ 빌드#594 |

### Phase 1 — CIO 반려 원인 분석 + 검수 시스템 점검 ✅

**수정 완료**:
- QA 보고서 스니펫 3000→8000자 (잘림 방지)
- QA 판정 키워드: 한국어 "승인/반려" → 영어 PASS/FAIL (파싱 취약점 제거)
- 최근 CIO 분석 로그 없어 실제 반려 사례 미확인 (다음 분석 실행 시 확인)

### Phase 2 — 기능 다이어트 + 코드 전수검사 ✅

**전수검사 결과**:
- 2-1: agents.yaml spawn_agent 4곳 제거 + CIO name 수정 → **-380줄**
- 2-2: 도구 **131개** 전수 매핑 정상 (유령 0개)
- 2-3: SNS 16개 엔드포인트 → 9개 동작, 3개 조건부, 3개 스텁(의도적 설계)
- 2-4: 핸들러 **26개** 전부 마운트됨 (고아 0개)
- 2-5: JS/HTML "처장→팀장", "전문가4명" 레거시 전부 제거
- 2-6: 로그 117건 일관 사용 중 (변경 불필요)
- arm_server.py "처장→팀장" **81건** 일괄 치환 (텔레그램코드 보호)
- 일회성 스크립트 2개 삭제

### Phase 3 — UX/UI 전면 개편 ✅ 완료

**목표**: 대표님 32개 개선 항목 전부 구현.
**상태**: Phase A+B+C+D+E 전체 완료. 기밀문서 전면개편 + 금융분석팀장 이름 통일.

| Phase | 내용 | 상태 |
|-------|------|------|
| **A** | confirm 모달, 대화삭제, tier필터, CTO제거, 전체선택, 교신로그, 매매전략삭제, 기밀문서, 지휘소 이름변경 (9건) | ✅ |
| **B** | 탭순서 변경, 더보기 재구성, AGORA/NEXUS 순서, 뷰모드 순서 (4건) | ✅ |
| **C** | 사이드바 flat, 작전일지 요약, 전력분석 새로고침, 사무실 3열2행, AI모델변경, 로그시간, 통신로그UX, 장기기억(이미존재) (8건) | ✅ |
| **D** | 도구검수(Phase2완료), D-2동시명령, D-3통신국, D-4포트폴리오, **D-5모바일✅**, D-6보고서ID (6건) | ✅ |
| **E** | E-1피드백모드, E-2숨겨진기능, E-3정보국파일업로드 (3건) | ✅ |
| **추가** | 기밀문서 카드 전면개편(팀명\|담당자/날짜\|제목/시간\|용량) + 금융분석팀장 이름 통일 | ✅ |

### Phase 4 — 아키텍처 품질 검토 ✅

**전수검사 결과**:
- 4-1: arm_server.py **9,910줄** 150함수 — D등급 모놀리스. 분리 대상: 배치체인(1,695줄), 텔레그램(702줄), 트레이딩(1,626줄). 리팩토링 14단계 중 Step 1 완료(7%)
- 4-2: 핸들러 26개 전부 마운트됨, 역할 중복 없음
- 4-4: **AI 폴백 강화 완료** — 404 전 프로바이더 확대(Anthropic/Google/OpenAI 체인) + 429 5회 실패 시 자동 크로스 프로바이더 전환
- 4-3: 17-cutting-edge → Phase 5에서 재평가
- 4-5: 노션 연동 → 대표님 CIO 분석 실행 후 검증 예정

### Phase 6 — 매매 엔진 혁신 + 정보국 (2026-02-26 대표님 승인)

> **핵심 통찰**: AI가 "심부름(데이터 수집)+생각(판단)"을 동시에 하고 있었음. 서버가 심부름, AI는 생각만 하는 구조로 전환.

#### 완료 (2026-02-26)
| # | 내용 | 빌드 |
|---|------|------|
| 6-0 | **실거래 버그 3종**: calibration_factor NameError(핵심), use_mock_kis 누락, QA 재분석 로직 추가 | #22426154426 |
| 6-1 | **정량 신뢰도(Quant Score)**: RSI/MACD/볼린저/거래량/추세 → 서버 수식 계산 → AI는 ±20%p 조정만 | #22426738142 |
| 6-10 | **신뢰도 산식 전면 재설계**: 방향/신뢰도 분리 (가중평균→합의투표), ±15%p→±20%p 확대, 구조적 42-52%→3/4합의시 76% | #620 |
| 6-2 | **가격 트리거 자동매매**: 매수 체결 시 손절(-5%)/익절(+10%) 자동 등록, 1분마다 가격 모니터링 → 발동 시 자동 주문 | #22426738142 |
| 6-3 | **도구 전수검사**: 131개 도구 3분류 완료 (`docs/architecture/tool-server-flow.md/.html`) | — |
| 6-4 | **CLAUDE.md 다이어그램 규칙**: .md + .html 뷰어 반드시 함께 생성 | — |
| 6-5 | **ARGOS 수집 레이어**: DB 테이블 5개 + cron_loop 수집 (1분/30분/1시간/1일) | ✅ #609 |
| 6-6 | **도구 서버화 Phase 2**: `/api/argos/price,news,dart,macro` DB 캐시 서빙 | ✅ #609 |
| 6-7 | **신뢰도 완전 서버화**: `/api/argos/confidence/{ticker}` (Quant+Cal+Bayesian+ELO) | ✅ #609 |
| 6-8 | **ARGOS 정보국 탭 + 상단 상태바**: 항상보임 바 + intelligence 탭 전체 | ✅ #609 |
| 6-9 | **강화학습 파이프라인**: 월간 AI 패턴 분석 크론 + 기존 7일 ELO 파이프라인 | ✅ #609 |

#### 아키텍처 원칙 (확정)
- **서버 우위 47개**: pykrx/yfinance/API/수식 → AI 호출 없이 직접
- **서버+AI 51개**: 서버가 수집 → AI가 해석. 역할 분리
- **AI 우위 33개**: 해석/판단/생성만. 배치 처리로 호출 최소화
- **데이터 3계층**: 수집층(ARGOS 상시) → 계산층(지표 서버 계산) → 판단층(AI)
- **플로우차트**: `docs/architecture/intelligence-plan.html` 참조

#### ✅ ARGOS↔에이전트 도구 데이터 중복 — 해결 완료 (PR#621~625)

> 5개 도구에 `_argos_reader.py` 헬퍼 추가. DB에 신선한 데이터 있으면 DB 읽기, 없으면 API 폴백. API 호출 90% 감소.

| 데이터 | 에이전트 도구 | DB 읽기 | 비고 |
|--------|-------------|---------|------|
| 한국 주가 | kr_stock | ✅ | `get_price_dataframe()` |
| 미국 주가 | us_stock | ✅ | `get_price_data()` |
| 네이버 뉴스 | naver_news | ✅ | `get_news_data()` |
| DART 공시 | dart_api | ✅ | `get_dart_filings()` |
| 매크로 지표 | ecos_macro | ✅ | `get_macro_data()` |

추가: ARGOS 수집 타임아웃 수정 (per-ticker 20s), 순차 수집 (DB lock 방지), 진단 엔드포인트 `/api/argos/diag`

### Phase 5 — 새 기능 추가 (Phase 0~4 완료 후)

| # | 내용 | 상세 |
|---|------|------|
| 5-1 | **NEXUS 재설계** — 왼쪽: Mermaid 시스템 플로우차트 (기능이 어떻게 돌아가는지), 오른쪽: Excalidraw SketchVibe 캔버스 (대표님 손그림 → Claude 정식 다이어그램) | 3D→2D 전환 확정 (`knowhow/14`) |
| 5-2 | **Soul Gym 전 팀장 확장** — 6팀장 맞춤 벤치마크 (`docs/architecture/soul-gym-benchmarks.md`) |
| 5-3 | **신기술 도입** — 17번에서 확정된 것들 |
| 5-4 | **arm_server.py 이름 변경** + 추가 리팩토링 |

---

## 🔍 별도 진행 — SketchVibe 특허 조사

- **법무팀장 + 전략팀장 합동 조사** 지시 대기 중
- 법무팀장: 선행기술 재조사 + 청구항 설계 + 출원 절차 상세 + 비용
- 전략팀장: 시장 분석(TAM/SAM/SOM) + 사업 모델 + ROI + 타이밍
- **핵심 결론**: 통합 파이프라인(스케치+말→다이어그램→config→배포)은 전 세계에 없음 (2026-02-25 확인)
- **위험**: tldraw Computer/Agent Starter Kit이 확장되면 위협 가능 → 선점 필요
- **미결**: 변리사 선임 150~300만원, 상표 출원 ~50만원

---

## ✅ 최근 완료

| 날짜 | 내용 | 빌드 |
|------|------|------|
| 02-26 | ARGOS↔도구 중복 해결 + 타임아웃 + 순차수집 + R-1/R-4/R-6 수정 + N-3/N-4/N-5 새기능 + 명칭정리 | 배포 보류 |
| 02-26 | 신뢰도 산식 재설계 (가중평균→합의투표) | #620 |
| 02-26 | read_knowledge 도구 + 리트마스터 지식 주입 | (PR#617) |
| 02-26 | 작전계획 탭 + 즉시분석 목표가 연동 (buy_limit 자동등록) | #614 |
| 02-26 | CIO 목표가 자동설정 + buy_limit 트리거 자동등록 (자동봇) | #613 |
| 02-26 | Notion DB 라우팅 버그 + souls/tools 67개 삭제 + CIO 이름 수정 | #612 |
| 02-26 | Phase 6 전체(6-5~6-9): ARGOS 수집+정보국UI+신뢰도서버화+RL파이프라인 | #609 |
| 02-26 | 정량신뢰도+가격트리거 자동매매+실거래버그3종 수정 | #22426738142 |
| 02-26 | 도구 전수검사 131개 + HTML 뷰어 + CLAUDE.md 규칙 | — |
| 02-26 | UX Phase D(4건)+E-1+기밀문서 개편+CIO 이름 수정 | #22426521917 |
| 02-26 | UX Phase C(8건) + D-5 모바일 + 긴급버그4건 | 배포 대기 |
| 02-26 | UX 전면개편 Phase A(9건)+B(4건) | #598 |
| 02-26 | Anthropic 스트리밍 필수 오류 수정 | #598 |
| 02-26 | Phase 0~4 전수검사 + AI 폴백 강화 | #597 |
| 02-26 | arm_server.py 리네임 | #596 |
| 02-25 | conversation_id 전달 버그 수정 | #594 |
| 02-25 | Soul Gym 경쟁 진화 시스템 | #591 |
| 02-25 | v4 대개편 (6팀장 체제) | #575 |
| 02-25 | AI 크레딧 소진 자동 폴백 | #575 |
| 02-24 | P0 버그 3건 + 로그 버그 6건 | — |

---

## ⬜ 미완료 이관

- **노션 DB 실제 저장 검증** — Phase 4-5에서 처리
- **NEXUS 재설계** — Phase 5-1에서 처리 (3D→2D + Excalidraw)

---

## 🔴 CTO — 동면 상태

> 2026-02-22 대표님 지시. 용도 확정까지 CTO 관련 작업 보류.

---

## 🎉 첫 실매매 (2026-02-21)

NVDA 1주 @ $189.115 — KIS 실계좌 체결 완료

---

## CEO 확정 설계 결정

| 항목 | 결정 |
|------|------|
| 실거래 UI | 2행 2열: 실거래(한국\|미국) / 모의투자(한국\|미국) |
| 사령관실 | SSE 상시 + P2P 실시간 + 뱃지 + 네트워크 다이어그램 |
| 디버그 URL | 버그 시 즉석 생성 → 대표님에게 적극 제공 |
| CIO 목표가 | CIO가 분석 후 직접 산출 |
| order_size: 0 | CIO 비중 자율 (정상! 변경 금지) |
| NEXUS | 2D 전환: 왼쪽 시스템 플로우차트 + 오른쪽 Excalidraw |
| Soul Evolution | 자동 승인 (CEO 승인 불필요) |
| Soul Gym | 24/7 상시 운영 |

---

## 프로젝트 기본 정보

| 항목 | 값 |
|------|-----|
| 저장소 | https://github.com/kodonghui/CORTHEX_HQ |
| 서버 | Oracle Cloud ARM **200GB** (corthex-hq.com) ← 2026-02-26 업그레이드 |
| 버전 | 4.00.000 |
| 에이전트 | 7명 (6팀장 체제) |
| 도구 | 132개 (tools.yaml 기준, 4분류: API 62/LLM 52/LOCAL 18/STUB 5) |
| DB | SQLite (/home/ubuntu/corthex.db) |
| GitHub Secrets | 50+ 전부 등록 완료 |

# CORTHEX HQ - Claude 작업 규칙

> 상세 규칙: `docs/claude-rules/` (코딩_개발 · 서버_배포 · 에이전트_팀)
> API URL/시크릿/모델표: `docs/claude-reference.md`

---

## 🔴 절대 규칙 (위반 시 즉시 수정)
- **처장 = 5번째 분석가**: 독자분석 병렬 구조 깨는 코드 변경 금지 | `_manager_with_delegation()`
- **실시간 모니터링**: "로그 확인해" → `/api/activity-logs` 1분마다 자동 보고
- **메모리 파일 금지**: `~/.claude/` memory 저장 금지. 상태/기록은 git 파일에만
- **서버 로그 접근 가능**: `/api/debug/server-logs` | "안 된다" 말하지 마
- **매매 설정 금지**: `order_size: 0` = 정상. 건드리지 마
- **날짜 KST**: UTC→KST(+9h) 변환 필수

## ⚡ 세션 시작
1. `git worktree list` → 겹치면 전용 worktree
2. `git fetch origin && git status` → 미커밋 있으면 물어볼 것
3. `git checkout main && git pull` → `git checkout -b claude/작업명 origin/main`
4. 탐색: `docs/project-status.md` → `docs/updates/` 최근 → 관련 코드
5. **작업 규칙 읽기**: `docs/claude-rules/` 해당 파일 참조

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ | 도메인: `corthex-hq.com`
- 소유자: kodonghui (고동희 대표님, 법학전공 / 비개발자) | 언어: 한국어

## 소통 규칙
- 호칭: **"대표님"** (CEO님 금지). 존댓말 필수
- **뻔한 질문 금지**: "커밋할까요?" → 바로 실행
- **"논의" → 코딩 금지**: 옵션+추천 제시, 결정 후 실행
- **"align" → 내 이해 먼저 설명** 후 교정받기
- **소신 발언 필수**: B가 더 나으면 먼저 말할 것
- **"로컬에서 확인" 금지** → 항상 `corthex-hq.com`에서
- 논의 꼬리물기 → 매 응답 상단에 "✅ 확정된 것" 섹션

## 🔴 기술 설명 — 대표님은 비개발자!
- 새 용어 첫 등장 시만 비유로 설명. 이미 나온 건 그냥 씀
- "최적화했습니다" ❌ → "8,500줄→6,000줄" ✅ | 표/번호/구분선 사용
- 한국어로. 도구 권한 요청도 한국어 | 작업 과정 먼저 설명 후 실행

## 🔴 5등급 작업 티어 (매 작업 시작 시 판단 필수!)

**세션 시작 = 소네트 기본. 작업 복잡도 먼저 판단 후 모델 추천.**

| 등급 | 모델 | 작업 | 서브에이전트 |
|------|------|------|------------|
| T1 | 하이쿠 | 파일 검색, 단순 정리, 반복 | 불필요 |
| T2 | 소네트 | 버그 수정, 문서, 일반 코딩, 로그 분석 | 불필요 |
| T3 | 소네트 | 여러 파일 수정, 중간 복잡도 | 병렬 서브에이전트 |
| T4 | 오퍼스 | 아키텍처 설계, 원인 불명 버그, 복잡한 판단 | 불필요 |
| T5 | 오퍼스 | 대규모 리팩토링, 전체 시스템 변경 | 병렬 서브에이전트 |

**1M 컨텍스트**: 3,000줄+ 파일 전체 분석, 대규모 리팩토링 시만. 나머지는 200K 충분.

## 🔴 플랜모드 자동 트리거

대표님 메시지에 아래 키워드 포함 시 → **자동으로 플랜모드 진입** (바로 코딩 금지):
> `설계` `계획` `구조` `아키텍처` `리팩토링` `전면 개편` `시스템 변경`

포함 안 되어도 T4/T5 등급이면 → 플랜모드 먼저 제안

---

# 🚨 작업 완료 7단계 — 전부 안 하면 미완성!

| # | 할 것 |
|---|------|
| ① | `docs/updates/날짜_요약.md` 작성 |
| ② | `docs/project-status.md` 업데이트 |
| ③ | `docs/todo/날짜.md` 갱신 |
| ④ | **`docs/todo/BACKLOG.md` 갱신** — 🔴 빼먹으면 미완성 |
| ⑤ | 커밋 `[완료]` → `gh run list --workflow=deploy.yml --limit=1` → 빌드#N 확인 |
| ⑥ | 대표님 보고: `✅ 빌드#N 배포됨 / 바뀐 것 / 확인 URL` |
| ⑦ | compact 대비: ①~⑥ 전부 = compact 후에도 이어갈 수 있음 |

## TODO 관리
- **`BACKLOG.md`** ← 미완료 전부. ⬜ 이관-복붙 금지
- **`YYYY-MM-DD.md`** ← 오늘 완료만 기록. 맥락 필수 (한 줄짜리 금지)
- 배포 = BACKLOG 갱신 필수!

## 참조 문서
- `docs/claude-rules/코딩_개발.md` — Git/UI/성능/새기능 레퍼런스
- `docs/claude-rules/서버_배포.md` — 서버/빌드/시크릿/노션
- `docs/claude-rules/에이전트_팀.md` — 에이전트 구조/소울/매매
- `docs/corthex-vision.md` — CORTHEX 비전
- `docs/ceo-ideas.md` — 대표님 아이디어 로그 (자동 업데이트)
- `docs/과외/` — 개발 용어 설명 + 운용 가이드
- 리트마스터: https://github.com/kodonghui/leet-master

## 기타
- TodoWrite로 진행 표시 (3개+ 작업 시). in_progress 1개만
- gh CLI 없으면 세션 시작 시 설치
- CLAUDE.md: **100줄 이내 유지**. 상세는 `docs/claude-rules/`에

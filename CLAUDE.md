# CORTHEX HQ - Claude 작업 규칙

@docs/claude-rules/코딩_개발.md
@docs/claude-rules/서버_배포.md
@docs/claude-rules/에이전트_팀.md

> API URL/시크릿/모델표: `docs/claude-reference.md`

---

## 🔴 절대 규칙 (위반 시 즉시 수정)
- **🚨 role if/else 금지 (v5.1)**: `if (auth.role === 'sister')` / `x-show="auth.role"` 등 1줄이라도 금지. `workspace.*` 설정 데이터만 사용. 아키텍처: `_bmad-output/planning-artifacts/architecture.md`
- **🚨 탭 숨기기 금지 (v5.3)**: `showSections` / `allowedDivisions` workspaces.yaml에 추가 금지. 탭은 모든 사람 동일. 데이터 격리는 `orgScope`만. 빈 데이터면 빈 상태 표시.
- **워크스페이스**: 네이버 모델(같은 기능, 다른 데이터) + 슬랙 모델(cli_owner 기반 내 직원만)
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
- **소신 발언 필수**: B가 더 나으면 먼저 말할 것 | **"align"** → 내 이해 먼저 설명 후 교정받기
- **"로컬에서 확인" 금지** → 항상 `corthex-hq.com` | 논의 꼬리물기 → 매 응답 상단 "✅ 확정된 것"

## 🔴 기술 설명 — 대표님은 비개발자!
- 새 용어 첫 등장 시만 비유로 설명. 이미 나온 건 그냥 씀
- "최적화했습니다" ❌ → "8,500줄→6,000줄" ✅ | 표/번호/구분선 사용
- 한국어로. 도구 권한 요청도 한국어 | 작업 과정 먼저 설명 후 실행

## 🔴 5등급 작업 티어 (매 작업 시작 시 판단 필수!)

| 등급 | 모델 | 작업 | 서브에이전트 |
|------|------|------|------------|
| T1 | 하이쿠 | 파일 검색, 단순 정리, 반복 | 불필요 |
| T2 | 소네트 | 버그 수정, 문서, 일반 코딩, 로그 분석 | 불필요 |
| T3 | 소네트 | 여러 파일 수정, 중간 복잡도 | 병렬 서브에이전트 |
| T4 | 오퍼스 | 아키텍처 설계, 원인 불명 버그, 복잡한 판단 | 불필요 |
| T5 | 오퍼스 | 대규모 리팩토링, 전체 시스템 변경 | 병렬 서브에이전트 |

**1M 컨텍스트**: 3,000줄+ 파일 전체 분석, 대규모 리팩토링 시만.

## 🔴 플랜모드 자동 트리거
키워드 포함 시 → **자동 플랜모드** (바로 코딩 금지):
> `설계` `계획` `구조` `아키텍처` `리팩토링` `전면 개편` `시스템 변경`

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

## 🔴 팀 에이전트 & 실서버 검증
- **팀 에이전트 의무**: 조사+수정+검증 동시 필요 시 → `TeamCreate+Agent` 병렬 투입
- **실서버 검증 의무** (구현 완료 후 반드시):
  ```
  # 헬스체크
  curl -s https://corthex-hq.com/api/health
  # 서버 로그 (WebFetch 사용)
  https://corthex-hq.com/api/debug/server-logs?lines=20&service=corthex
  ```
- **"됐겠지" 절대 금지**: 코드만 짜고 확인 없이 완료 보고 금지

## 🌙 자율 실행 모드 (대표님 부재 시)
대표님이 자리 없을 때:
1. `docs/todo/BACKLOG.md`에서 T1/T2 작업 식별
2. 각 작업 구현 + 실서버 검증
3. 통과 시 커밋 (`claude/자율-YYYYMMDD` 브랜치)
4. `docs/updates/` 자동 업데이트 + BACKLOG 갱신
5. PR 생성 (대표님 검토용)

## 참조 문서
- `docs/claude-rules/코딩_개발.md` | `docs/claude-rules/서버_배포.md` | `docs/claude-rules/에이전트_팀.md`
- `docs/corthex-vision.md` | `docs/ceo-ideas.md` | `docs/과외/`
- 리트마스터: https://github.com/kodonghui/leet-master

## 기타
- TodoWrite로 진행 표시 (3개+ 작업 시). in_progress 1개만
- gh CLI 없으면 세션 시작 시 설치
- CLAUDE.md: **100줄 이내 유지**. 상세는 `docs/claude-rules/`에

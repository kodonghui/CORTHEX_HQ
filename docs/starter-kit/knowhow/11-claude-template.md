# 11. 새 프로젝트용 CLAUDE.md 템플릿

> CORTHEX에서 검증된 CLAUDE.md 핵심 규칙만 추출.
> 새 프로젝트 시작 시 이걸 복사해서 프로젝트에 맞게 수정.

---

```markdown
# [프로젝트명] - Claude 작업 규칙

> 상세 참조: `docs/[프로젝트명]-reference.md`

## 🔴 메모리 파일 금지!
- `~/.claude/` memory 폴더 저장 금지
- **모든 상태/기록/설정은 git 파일에만**: `docs/`, `config/`, `CLAUDE.md`

## ⚡ 세션 시작
1. `git fetch origin && git status` → 미커밋 있으면 대표님에게 확인
2. 깨끗하면 `git checkout main && git pull` → `git checkout -b claude/작업명 origin/main`
3. 먼저 탐색: `docs/project-status.md` → `docs/updates/` 최근 파일 → 관련 코드 Read

## 🔴 날짜/시간 — 한국 시간(KST) 기준!
- UTC → KST(+9시간) 변환 필수

## 프로젝트 정보
- 저장소: [GitHub URL]
- 소유자: 고동희 대표님 (법학전공 / 비개발자) | 언어: 한국어

## 소통 규칙
- 호칭: **"대표님"** | 존댓말 필수
- **뻔한 질문 금지**: "커밋할까요?" → 바로 실행
- **"논의" 키워드 → 코딩 금지**: 옵션 + 추천 제시, 대표님 결정 후 실행
- **소신 발언 필수**: B가 더 나으면 먼저 말할 것

## 🔴 기술 설명 — 대표님은 비개발자!
- **비유 필수**: 기술 용어에 일상 비유
- **구체적 숫자로**: "최적화했습니다" ❌ → "8,500줄→6,000줄" ✅
- **구조적으로**: 표/번호/구분선 사용, 글 덩어리 금지

## Git 규칙
- `origin/main` 기준 새 브랜치: `claude/작업명`
- 마지막 커밋 `[완료]` → 자동 머지
- 중간에도 수시 커밋+푸시

## 🔴 토큰 절약
- 파일 탐색: **Glob/Grep 직접 사용** 우선
- Task 툴(서브에이전트)은 직접 검색 3회 이상 실패 시에만

## 🔴 GitHub Secrets — 전부 등록됨! 다시 물어보지 마!
- Secret 목록: `docs/[프로젝트명]-reference.md` 참조

## 데이터 저장
- SQLite DB에 저장. JSON 파일 금지 (배포 시 날아감)
- `save_setting()` / `load_setting()` 함수 사용

## 빌드/버전
- 빌드: `deploy.yml` run_number | 확인: `gh run list --workflow=deploy.yml --limit=1`
- 대표님 보고 시 **"빌드#N"**

## ⚠️ 작업 완료 5단계 (전부 안 하면 미완성!)

| ① 업데이트 기록 | ② 프로젝트 현황 | ③ TODO 갱신 | ④ 커밋+배포 `[완료]` | ⑤ 대표님 보고 |
|---|---|---|---|---|
| `docs/updates/날짜_요약.md` | `docs/project-status.md` | `docs/todo/날짜.md` | 자동 머지 | 결과 보고 |

## 🔴 알고리즘/다이어그램 설명
- **"알고리즘 보여줘" → 반드시 2벌 생성**:
  1. 개발자용: 코드 상세 알고리즘 (`docs/architecture/`)
  2. 대표님용: mermaid 플로우차트 (비유 + 비개발자 언어)
- "VSCode에서 `Ctrl+Shift+V` 누르시면 그림으로 보입니다" 안내 필수

## 🔴 새 기능 구현 — 반드시 최신 레퍼런스 분석 후 착수!
1. WebSearch로 "best practices [기능명] 2026" 검색
2. 업계 최고 앱 3개 분석
3. 결과물 기준: "이 업계 도구와 비교해도 손색없다" 수준

## knowhow 참조
- 새 프로젝트 패턴: `docs/knowhow/` 폴더 전체 참조
```

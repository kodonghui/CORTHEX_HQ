# CORTHEX HQ - Claude 작업 규칙

> API URL/시크릿/모델표: `docs/claude-reference.md`

---

## 🚨 절대 금지 (이것만은 무조건. 위반 시 즉시 수정)
1. **role if/else 금지**: `if (auth.role === 'sister')` 등 1줄도 금지. `workspace.*`만 사용
2. **탭 숨기기 금지**: `showSections` / `allowedDivisions` 추가 금지. 데이터 격리는 `orgScope`만
3. **index.html Write 덮어쓰기 금지**: Edit 부분 수정만

---

# 🚨🚨🚨 개발 워크플로우 — 모든 작업에 이 순서!

## STEP 1. 요구사항 & 계획
- 관련 코드 먼저 읽기 (추측 금지)
- 새 기능/다중 파일 → `corthex-pm` 에이전트 투입
- 수정 범위 확정 후 시작

## STEP 2. 구현
- 브랜치: `git checkout -b claude/작업명 origin/main`
- push/배포 금지 — QA 통과 전까지 절대 금지

## STEP 3. E2E 소크라테스 QA (구현 후 반드시!)
```
시나리오: A → B → C = 실제결과
기댓값과 실제결과 비교
다르면 → 버그
```
- 시나리오 6개 이상 (핵심 플로우 전부 + 엣지케이스)
- 버그 발견 시 즉시 커밋 금지 → 전부 목록화 → 일괄 수정 → QA 재실행
- 버그 조사: 혼자 추측 금지 → `investigator` 먼저 → 수정 후 `spec-validator`

## STEP 4. 문서 업데이트 (커밋 전에! 빼먹으면 미완성!)
- `docs/updates/날짜_작업명.md` 작성
- `docs/project-status.md` 업데이트 (빌드#N 또는 커밋해시 포함)
- `docs/todo/BACKLOG.md` 갱신
- `docs/todo/날짜.md` 갱신

## STEP 5. 커밋 & 배포 (코드 + 문서 한번에)
- QA 전부 통과 후에만 커밋
- `git commit -m "내용 [완료]"` → push
- **빠른 배포**: `bash deploy-fast.sh` (SSH 직배포, 30초)
- **일반 배포**: `gh run list --workflow=deploy.yml --limit=1` (새 API 키 추가 시만)

## STEP 6. 보고
```
✅ [커밋해시 또는 빌드#N] 배포됨
바뀐 것: [목록]
확인 URL: https://corthex-hq.com/...
```

---

## 항상 지킬 것 (상태형 — 모든 작업에 항상 적용)
- **워크스페이스**: 네이버 모델(같은 기능, 다른 데이터) + 슬랙 모델(cli_owner 기반 내 직원만)
- **메모리 파일 금지**: `~/.claude/` memory 저장 금지. 상태/기록은 git 파일에만
- **매매 설정 금지**: `order_size: 0` = 정상. 건드리지 마
- **날짜 KST**: UTC+9
- **호칭**: "대표님" | 뻔한 질문 금지 → 바로 실행
- **"논의" → 코딩 금지**: 옵션+추천 제시, 결정 후 실행
- **"로컬에서 확인" 금지** → 항상 `corthex-hq.com`
- 새 용어 첫 등장 시만 비유로 설명 | 한국어로
- TodoWrite로 진행 표시 (3개+ 작업 시). in_progress 1개만

---

## ⚡ 세션 시작
1. `git fetch origin && git status` → 미커밋 있으면 물어볼 것
2. `git checkout main && git pull` → `git checkout -b claude/작업명 origin/main`
3. `docs/project-status.md` → `docs/updates/` 최근 → 관련 코드 읽기

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ | 도메인: `corthex-hq.com`
- 소유자: kodonghui (고동희 대표님, 법학전공 / 비개발자) | 언어: 한국어

## 5등급 작업 티어

| 등급 | 작업 |
|------|------|
| T1 하이쿠 | 파일 검색, 단순 정리 |
| T2 소네트 | 버그 수정, 문서, 일반 코딩 |
| T3 소네트+병렬 | 여러 파일 수정, 중간 복잡도 |
| T4 오퍼스 | 아키텍처, 원인 불명 버그 |
| T5 오퍼스+병렬 | 대규모 리팩토링, 전체 시스템 |

## 플랜모드 자동 트리거
> `설계` `계획` `구조` `아키텍처` `리팩토링` `전면 개편` `시스템 변경`

## 에이전트
- **버그 조사**: `investigator` → 원인 파악 → 수정 → `spec-validator`
- **실서버 검증**: `curl -s https://corthex-hq.com/api/health`
- **에이전트 목록**: `.claude/agents/`

## TODO 관리
- **`BACKLOG.md`** ← 미완료 전부 | **`YYYY-MM-DD.md`** ← 오늘 완료만

## 참조 문서
- `docs/claude-rules/` | `docs/corthex-vision.md` | `docs/ceo-ideas.md`
- **SketchVibe**: `docs/sketchvibe-guide.md`
- 리트마스터: https://github.com/kodonghui/leet-master
- gh CLI 없으면 세션 시작 시 설치

---

## 상세 규칙 (위 규칙의 세부 사항)
@docs/claude-rules/코딩_개발.md
@docs/claude-rules/서버_배포.md
@docs/claude-rules/에이전트_팀.md

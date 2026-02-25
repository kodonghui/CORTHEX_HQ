# Notion DB 환경변수 이름 불일치 수정

## 버전
3.03.001

## 작업 날짜
2026-02-18

## 작업 브랜치
claude/autonomous-system-v3

---

## 문제 원인

CEO가 노션 DB 2개 ID를 제공했고, GitHub Secrets에 등록했지만, `deploy.yml`이 서버에 전달하는 코드에 두 가지 버그가 있었음:

| 항목 | 버그 내용 |
|------|---------|
| `NOTION_DB_SECRETARY` | deploy.yml이 읽는 Secret 이름이 `NOTION_SECRETARY_DB_ID`로 달랐음 (없는 Secret 참조) |
| `NOTION_DB_OUTPUT` | deploy.yml에 아예 없었음 — Secret 등록해도 서버로 전달 안 됨 |
| 서버 저장 이름 | `NOTION_SECRETARY_DB_ID`로 저장 → arm_server.py가 `NOTION_DB_SECRETARY`로 읽음 (이름 불일치) |

## 변경 사항

### 수정된 파일: `.github/workflows/deploy.yml`

1. **env 섹션** (환경변수 선언 부분)
   - 기존: `NOTION_SECRETARY_DB_ID_VAR: ${{ secrets.NOTION_SECRETARY_DB_ID }}` (없는 Secret)
   - 변경: `NOTION_DB_SECRETARY_VAR: ${{ secrets.NOTION_DB_SECRETARY }}` + `NOTION_DB_OUTPUT_VAR: ${{ secrets.NOTION_DB_OUTPUT }}` (실제 Secret 이름과 일치)

2. **envs 목록** (서버로 전달할 변수 목록)
   - `NOTION_SECRETARY_DB_ID_VAR` → `NOTION_DB_SECRETARY_VAR, NOTION_DB_OUTPUT_VAR`

3. **스크립트 섹션** (서버 환경변수 파일에 저장하는 부분)
   - 저장 이름: `NOTION_SECRETARY_DB_ID` (잘못됨) → `NOTION_DB_SECRETARY` (arm_server.py와 일치)
   - `NOTION_DB_OUTPUT` 저장 코드 신규 추가

## 등록된 GitHub Secrets (CEO 제공 실제 ID)

| Secret 이름 | 값 (일부) | 용도 |
|-------------|---------|------|
| `NOTION_DB_SECRETARY` | `30a56b497...` | 비서실 에이전트 보고서 |
| `NOTION_DB_OUTPUT` | `30a56b497...` | 나머지 에이전트 산출물 |

## 현재 상태

- 빌드 #221 배포 완료 ✅
- 이제 서버 재시작 시 올바른 Notion DB ID가 환경변수로 설정됨
- 비서실 에이전트 (division=secretary) → 비서실 DB에 저장
- 나머지 처장/전문가 → 에이전트 산출물 DB에 저장

## 다음에 할 일

1. **[보류] 리트마스터 홈페이지 자동배포 파이프라인 (C안)**
   - github_tool.py에 파일 수정/PR 생성 기능 추가
   - LEET_GITHUB_REPO, LEET_GITHUB_TOKEN 환경변수 추가

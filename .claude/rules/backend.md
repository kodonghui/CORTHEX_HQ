---
paths:
  - "web/**/*.py"
  - "src/**/*.py"
---

# 백엔드 규칙

`web/` 또는 `src/` 하위 Python 파일 수정 시 이 규칙이 자동 적용됩니다.

## 필수 규칙

### 기술 스택
- FastAPI + Python 3.11+
- 외부 API 코드 작성/수정 시 WebSearch로 최신 공식 문서 확인. 기억 의존 금지

### 데이터 저장
- SQLite DB (`settings` 테이블) 사용. JSON 파일 저장 금지 (배포 시 초기화됨)
- `save_setting()` / `load_setting()` 사용 | DB: `/home/ubuntu/corthex.db` (git 밖)

### 인증 & 보안
- 새 엔드포인트: 반드시 `get_auth_org(request)`로 orgScope 필터 적용
- 계좌번호 / API 키 / 개인정보 응답에 포함 금지
- role 하드코딩 금지 — `workspace.*` 설정 데이터만 사용

### 에러 처리
- 버그 발생 시 `/api/debug/xxx` 즉석 생성 → 대표님에게 URL 제공
- 모든 에러: 로그에 KST 시각 기록

### AI 도구
- `ai_handler.py` `ask_ai()` → 3개 프로바이더 도구 자동호출
- 스키마: `config/tools.yaml` | 루프 횟수 제한 없음 (로그 `(23회)` = 정상)

### 에이전트 / 모델 설정
- 모델명 정의: `config/agents.yaml` + `config/models.yaml` 2곳만. 코드에 직접 작성 금지
- 에이전트 목록 배열 하드코딩 금지. `config/agents.yaml` 기준
- `_manager_with_delegation()` 구조 절대 변경 금지 (처장 병렬 분석 아키텍처)

### 매매 설정
- `order_size: 0` = CIO 비중 자율 (정상!). 0을 다른 값으로 절대 변경 금지

## 리팩토링 기준
- `arm_server.py` 또는 핵심 파일이 **3,000줄 초과** 시 → BACKLOG에 핸들러 분리 항목 추가
- 단, 매 작업마다 언급 금지. 줄수 초과 시에만.

## 서버 배포
- `git pull` 금지 → `git fetch + git reset --hard` 사용
- 빌드: `deploy.yml` `run_number` | 확인: `gh run list --workflow=deploy.yml --limit=1`
- GitHub Secrets: 50+ 등록 완료. "키가 없어요" 금지. `docs/claude-reference.md` 참조

## 노션 연동
- API 버전: `2022-06-28` 고정. `2025-09-03` 절대 사용 금지 (DB ID 체계 완전히 다름)
- DB ID / Integration 상세: `docs/claude-reference.md`

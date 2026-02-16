# CORTHEX HQ - Claude 작업 규칙

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ
- 소유자: kodonghui (비개발자 CEO)
- 언어: 한국어로 소통

## 소통 규칙 (최우선 규칙 — 반드시 지킬 것)
- CEO는 비개발자다. 모든 대화에서 아래 규칙을 예외 없이 지킬 것
- **구체적으로**: 추상적인 말 금지. "최적화했습니다" (X) → "페이지 로딩 속도를 3초에서 1초로 줄였습니다" (O)
- **자세하게**: 생략하지 말 것. 뭘 했는지, 왜 했는지, 결과가 어떤지 다 말할 것
- **이해하기 쉽게**: 초등학생도 알아들을 수 있는 수준으로 말할 것. 전문 용어를 쓸 때는 반드시 괄호 안에 쉬운 설명을 붙일 것 (예: "커밋(저장)", "브랜치(작업 공간)")
- **구조적으로**: 장문일 때는 반드시 제목, 번호 매기기, 표, 구분선 등을 써서 정리할 것. 글 덩어리로 주지 말 것
- **한국어로**: 모든 대화, 질문, 도구 사용 권한 요청 메시지는 **한국어**로 할 것. "grep in?"(X) → "이 폴더에서 검색하시겠습니까?"(O)
- 무엇을 왜 하는지 먼저 설명하고, 그다음 실행할 것
- 작업 결과를 보고할 때는 "뭘 했는지 → 왜 했는지 → 현재 상태 → 다음에 할 일" 순서로 정리할 것
- 존댓말로 할것
- **뻔한 질문 금지**: 당연히 해야 하는 것을 CEO에게 물어보지 말 것. "커밋할까요?", "배포할까요?", "푸시할까요?" 같은 질문은 하지 말고 바로 실행할 것. CEO의 시간을 아낄 것
- **"로컬에서 확인" 금지**: 이 프로젝트는 Oracle Cloud 서버에 배포되어 있음 (서버 IP는 GitHub Secrets `SERVER_IP` 참조). "로컬에서 확인해보세요" 같은 말은 절대 하지 말 것. 확인은 항상 서버에서. 작업 완료 = 커밋 + 푸시 + 배포 + 서버에서 확인까지 끝낸 것

## Git 작업 규칙
- 깃허브의 Claude.md를 매번 반드시 참고할것
- 작업 중간에도 수시로 커밋 + 푸시할 것 (중간 저장)
- 작업이 완전히 끝났을 때, 마지막 커밋 메시지에 반드시 [완료] 를 포함할 것
  - 예: "feat: 로그인 기능 추가 [완료]"
  - [완료]가 있어야 자동 머지가 작동함. 없으면 PR만 만들고 머지는 안 함
- 브랜치명은 반드시 claude/ 로 시작할 것 (자동 머지 트리거 조건)
- 브랜치 작업 후 main에 합치는 것까지 완료해야 "작업 끝"으로 간주

## UI/UX 규칙
- **언어**: 모든 UI 텍스트는 **한국어**로 작성
- **시간대**: `Asia/Seoul` (KST, UTC+9) 기준
- **프레임워크**: Tailwind CSS + Alpine.js (CDN)
- **디자인 시스템**: `hq-*` 커스텀 컬러 토큰 사용

## 데이터 저장 규칙 (SQLite DB)
- **웹에서 사용자가 저장/수정/삭제하는 모든 데이터는 반드시 SQLite DB(`settings` 테이블)에 저장할 것**
  - 프리셋, 예약, 워크플로우, 메모리, 피드백, 예산, 에이전트 설정, 품질 검수 기준, 에이전트 소울 등 전부 포함
  - JSON 파일(`data/*.json`)에 저장하면 안 됨 — 배포(`git reset --hard`) 시 날아감
- **저장 방법**: `db.py`의 `save_setting(key, value)` / `load_setting(key, default)` 사용
  - `value`는 자동으로 JSON 직렬화됨 (dict, list, str 등 아무거나 가능)
  - 예: `save_setting("presets", [{"name": "기본", ...}])` → DB에 영구 저장
- **기존 JSON 데이터 자동 마이그레이션**: `_load_data(name)`은 DB를 먼저 확인하고, 없으면 JSON 파일에서 읽어서 DB로 자동 이전함
- **DB 위치**: 서버에서는 `/home/ubuntu/corthex.db` (git 저장소 밖) → 배포해도 데이터 안 날아감
- **config 설정 저장**: `_save_config_file(name, data)` → `config_{name}` 키로 DB에 저장

## 업데이트 기록 규칙
- 모든 작업 내용을 `docs/updates/` 폴더에 기록할 것
- 파일명 형식: `YYYY-MM-DD_작업요약.md` (예: `2026-02-13_홈페이지-디자인.md`)
- 하나의 세션(작업)이 끝날 때마다 반드시 기록 파일을 만들 것
- 노션(Notion)에 바로 복붙할 수 있는 마크다운 형식으로 작성할 것
- 기록 파일에 반드시 포함할 내용:
  1. **작업 제목** — 한 줄로 뭘 했는지 (예: "홈페이지 메인 디자인 구현")
  2. **작업 날짜** — YYYY-MM-DD 형식
  3. **버전** — `X.YY.ZZZ` 형식의 버전 번호 (아래 "버전 번호 규칙" 참고)
  4. **작업 브랜치** — 어떤 브랜치에서 작업했는지 (예: claude/design-homepage-ui-e96Bb)
  5. **변경 사항 요약** — 뭘 바꿨는지 비개발자도 알 수 있게 쉽게 설명
     - 새로 만든 파일, 수정한 파일 목록 포함
     - 각 파일이 뭐 하는 파일인지 괄호로 설명 (예: `index.html (홈페이지 메인 화면)`)
  6. **현재 상태** — 작업이 완료됐는지, 진행 중인지, 문제가 있는지
  7. **다음에 할 일** — 이 작업 이후에 해야 할 것들 (있으면)
- 전문 용어는 절대 그냥 쓰지 말고, 반드시 괄호 안에 쉬운 설명을 붙일 것
- CEO가 읽고 바로 이해할 수 있는 수준으로 작성할 것. 이해 못 하면 의미 없음

## 버전 번호 규칙
- **형식**: `X.YY.ZZZ` (예: `0.01.001`, `0.02.015`, `1.00.000`)
- **각 자리의 의미**:
  - `X` (메이저): 프로젝트의 큰 단계. 0 = 개발 중, 1 = 정식 출시
  - `YY` (마이너): 주요 기능 추가 시 올림 (예: 새 탭 추가, 새 시스템 구현)
  - `ZZZ` (패치): 버그 수정, 소소한 개선, 설정 변경 등 작은 변경 시 올림
- **현재 버전**: `1.00.000` (v1.0 정식 출시 — ARM 24GB 서버, 154개 도구, 배치 체인)
- **버전 올리는 규칙**:
  - 새 탭, 새 시스템, 새 부서 추가 등 **큰 변경** → 마이너(YY) 올리고 패치(ZZZ) 000으로 리셋
  - 버그 수정, UI 개선, 설정 변경 등 **작은 변경** → 패치(ZZZ)만 올림
  - 정식 출시 시 → 메이저(X) 1로 올림
- **작업 파일에 기록**: 모든 `docs/updates/` 파일의 상단에 버전 번호 포함
- **project-status.md에도 현재 버전 기록**: "마지막 업데이트" 섹션에 현재 버전 포함
- **예시**:
  ```
  # 에이전트 스킬 표시 문제 해결

  ## 버전
  0.05.048

  ## 작업 날짜
  2026-02-15
  ```

## 빌드 번호 규칙 (배포 확인용)
- **목적**: 배포가 완료됐는지 확인하기 위해 빌드 번호 시스템 사용
- **빌드 번호란?**: GitHub Actions의 `deploy.yml` 워크플로우 실행 횟수 (예: 빌드 #38)
- **빌드 번호 소스는 오직 하나**: `deploy.yml`의 `${{ github.run_number }}`
  - `mini_server.py`는 빌드 번호를 자체 생성하지 않음 (로컬에서는 "dev"로 표시)
  - Git 커밋 개수(`git rev-list --count HEAD`)는 빌드 번호와 **무관함** (절대 사용하지 말 것)
- **빌드 번호는 사전에 알 수 없음**: 배포가 실행되어야 번호가 매겨짐
- **작업 완료 시 반드시 할 것**:
  1. `gh run list --workflow=deploy.yml --limit=1` 명령으로 최신 배포의 빌드 번호를 확인
  2. CEO에게 아래 형식으로 **확인 체크리스트 표**를 만들어 줄 것:
     - 이번 세션에서 뭘 바꿨는지, 웹 화면 어디서 확인할 수 있는지 한눈에 정리
     - CEO가 대화 위로 스크롤해서 찾아볼 필요 없게, 마지막에 모든 확인 사항을 모아서 보여줄 것
  3. `docs/project-status.md`를 최신 상태로 갱신
  4. 배포 완료 후 웹 화면 좌측 상단에서 빌드 번호 확인 가능 (http://{SERVER_IP})
- **빌드 번호 확인 방법**:
  - 웹 화면: 좌측 상단에 "빌드 #XX" 표시
  - 배포 상태 JSON: `http://{SERVER_IP}/deploy-status.json` 접속
  - GitHub Actions: https://github.com/kodonghui/CORTHEX_HQ/actions 에서 "Deploy to Oracle Cloud Server" 실행 번호 확인
- **예시** (반드시 이 형식으로):
  ```
  ## 빌드 #56 배포 확인 체크리스트

  | # | 확인할 곳 | 확인할 내용 | 이전 | 이후 |
  |---|----------|-----------|------|------|
  | 1 | 좌측 상단 | 빌드 번호 | #55 | #56 |
  | 2 | 설정 > 품질 검수 | 부서별 검수 기준 7개 부서 표시 | 빈 화면 | 7개 부서 목록 |
  | 3 | 설정 > 품질 검수 | "(루브릭)" 텍스트 삭제됨 | "부서별 검수 기준 (루브릭)" | "부서별 검수 기준" |

  확인 방법: http://{SERVER_IP} 접속 후 위 표대로 확인해주세요.
  안 바뀌었으면 Ctrl+Shift+R (강력 새로고침) 해보세요.
  ```

## 기억력 보완 규칙 (대화 맥락 유지)
- **세션 시작 시**:
  1. 반드시 `docs/project-status.md` 파일을 먼저 읽을 것. 이 파일에 프로젝트의 현재 상태가 적혀 있음
  2. `docs/updates/` 폴더의 **최근 파일 2~3개**도 읽을 것. 이 폴더에 매 작업의 상세 기록이 날짜별로 저장되어 있음
     - 파일명 형식: `YYYY-MM-DD_작업요약.md` → 날짜가 최신인 파일부터 읽으면 됨
     - 이 기록에는 뭘 왜 어떻게 했는지, 수정한 파일 목록, 현재 상태, 다음에 할 일이 적혀 있음
     - 이걸 읽으면 "이전 세션에서 무슨 작업을 했는지" 맥락을 바로 파악할 수 있음
- **작업 완료 시**: `docs/project-status.md` 파일을 최신 상태로 업데이트할 것
  - "현재 완료된 주요 기능", "진행 중인 작업", "다음에 할 일" 섹션을 갱신
- **대화가 길어질 때**: 중간중간 핵심 내용을 요약해서 대화에 다시 언급할 것
- **중요한 결정이 내려졌을 때**: `docs/project-status.md`의 "중요한 결정 사항" 섹션에 즉시 기록할 것
- 이 규칙의 목적: CEO와 대화 중에 클로드가 맥락을 잃어버리는 것을 방지하기 위함

## 서버 배포 규칙 (Oracle Cloud — ARM 24GB 서버)
- **서버 스펙**: ARM Ampere A1, 4코어 24GB RAM (Oracle Cloud 춘천 리전, 무료 Always Free)
- **서버 접속 정보**:
  - IP: GitHub Secrets `SERVER_IP_ARM`에 등록
  - SSH 키: GitHub Secrets `SERVER_SSH_KEY_ARM`에 등록
  - 사용자: `ubuntu`
- **이전 서버 (폐기됨)**: `158.179.165.97` (1GB 마이크로 — 더 이상 사용 안 함)
- **자동 배포 흐름** (전체 과정):
  1. claude/ 브랜치에 [완료] 커밋 push
  2. `auto-merge-claude.yml`이 PR 생성 + main에 자동 머지
  3. 머지 성공 후 → `deploy.yml`을 **직접 실행(trigger)**시킴
  4. 새 서버에 SSH 접속 → `git fetch + git reset --hard` → 파일 복사 → 서버 재시작
  - **중요**: GitHub 보안 정책상, 워크플로우가 만든 push는 다른 워크플로우를 자동 실행시키지 않음. 그래서 auto-merge에서 `gh workflow run deploy.yml`로 직접 실행시키는 구조
  - **중요**: 서버에서 `git pull`을 쓰면 안 됨! 반드시 `git fetch + git reset --hard` 사용
- **워크플로우 파일**:
  - `.github/workflows/auto-merge-claude.yml` — 자동 머지 + 배포 트리거
  - `.github/workflows/deploy.yml` — 실제 서버 배포 (SSH로 접속해서 파일 복사)
- **수동 배포**: GitHub → Actions 탭 → "Deploy to Oracle Cloud Server" → "Run workflow" 버튼 클릭
- **주의사항**:
  - 서버 파일을 직접 수정하지 말 것 (GitHub에서 코드 수정 → 자동 배포가 정상 흐름)
  - 배포 실패 시 GitHub Actions 로그를 먼저 확인할 것
  - ARM 아키텍처(aarch64) — 대부분의 Python 패키지 호환됨
- **서버 디렉토리 구조**:
  - `/home/ubuntu/CORTHEX_HQ/` — git 저장소 (전체 코드)
  - `/home/ubuntu/CORTHEX_HQ/web/` — 백엔드 서버 (mini_server.py 실행됨)
  - `/home/ubuntu/CORTHEX_HQ/src/` — 도구 모듈, 에이전트 모듈 (100개+ 도구)
  - `/home/ubuntu/CORTHEX_HQ/config/` — 설정 파일 (agents.yaml, tools.yaml 등)
  - `/home/ubuntu/corthex.db` — SQLite DB (git 저장소 밖 → 배포해도 데이터 안 날아감)
  - `/home/ubuntu/corthex.env` — API 키 등 환경변수 (배포 시 자동 업데이트)
  - `/var/www/html/` — nginx가 서빙하는 정적 파일 (index.html)
- **서버 설정 파일 규칙 (중요!)**:
  - 배포 시 `config/yaml2json.py`가 YAML → JSON 자동 변환
  - **config/agents.yaml 또는 config/tools.yaml을 수정하면 자동 배포 후 JSON이 재생성됨** (별도 작업 불필요)
  - `deploy.yml` 안에 Python 코드를 직접 넣으면 YAML 들여쓰기 문제가 생김 → **반드시 별도 .py 파일로 분리**할 것

## 배포 트러블슈팅 (문제 해결 가이드)

### 배포 안 되는 흔한 원인들

| 증상 | 원인 | 해결 |
|------|------|------|
| 배포 성공인데 화면이 안 바뀜 | **브라우저 캐시** — 브라우저가 옛날 파일을 기억 | `Ctrl+Shift+R` (강력 새로고침) 또는 주소 뒤에 `?v=2` 붙이기 |
| 배포 성공인데 화면이 안 바뀜 (2) | **nginx 캐시** — 서버가 브라우저에 캐시 허용 | deploy.yml이 자동으로 nginx에 `no-cache` 헤더 설정 (2026-02-15 추가) |
| 배포 성공인데 화면이 안 바뀜 (3) | **서버 git pull 실패** — 이전 배포가 서버 파일을 수정해서 git pull이 충돌 에러를 냄 | `git pull` 대신 `git fetch + git reset --hard` 사용 (deploy.yml에 이미 반영됨). **Actions 로그에서 "error: Your local changes would be overwritten" 메시지가 있으면 이 문제** |
| GitHub Actions "success"인데 서버 접속 안됨 | **서버 다운** 또는 **방화벽 차단** | Oracle Cloud 콘솔에서 인스턴스 상태 확인 → Security List에서 포트 80 열려있는지 확인 |
| `pip 설치 실패` 경고 | PyYAML 패키지 설치 실패 | 무시 가능 (yaml 없이도 서버 동작함) |
| 빌드 번호가 `BUILD_NUMBER_PLACEHOLDER`로 표시 | HTML을 로컬에서 직접 열었음 (서버 아님) | 반드시 `http://{SERVER_IP}`으로 접속해야 함. 로컬 파일을 브라우저로 열면 빌드 번호가 주입 안됨 |

### 배포 확인하는 3가지 방법
1. **웹 화면**: `http://{SERVER_IP}` 접속 → 좌측 상단 "빌드 #XX" 확인
2. **배포 상태 JSON**: `http://{SERVER_IP}/deploy-status.json` 직접 접속 → 빌드 번호와 시간 확인
3. **GitHub Actions**: https://github.com/kodonghui/CORTHEX_HQ/actions → "Deploy to Oracle Cloud Server" 워크플로우 확인

### 배포 흐름 상세 (디버깅용)
```
[코드 수정] → [git push] → [auto-merge.yml] → [PR 생성 + main 머지]
    → [deploy.yml 직접 실행] → [서버 SSH 접속]
    → [git fetch + git reset --hard] (⚠️ git pull 아님!)
    → [sed로 빌드번호 주입] → [/var/www/html/index.html 복사]
    → [corthex 서비스 재시작] → [deploy-status.json 생성]
```

### nginx 캐시 방지 (2026-02-15 추가)
- deploy.yml이 첫 배포 시 nginx 설정에 `Cache-Control: no-cache` 헤더를 자동 추가
- 이후 배포부터는 브라우저가 항상 최신 파일을 받아감
- 수동으로 확인: `curl -I http://{SERVER_IP}` → `Cache-Control: no-cache` 헤더 있으면 정상

## 과거 사고 기록 (같은 실수 반복 금지!)

### 사고 1: 서버 배포 안 되는 문제 (2026-02-15)

- **증상**: 코드를 고치고 배포했는데, 서버에 아무 변화가 없음. 빌드 번호는 올라가지만 코드는 옛날 것 그대로
- **원인 (2가지가 겹침)**:
  1. `deploy.yml`이 서버에서 `git pull origin main`을 쓰고 있었음
  2. 그런데 이전 배포에서 `sed` 명령어가 `index.html`에 빌드 번호를 주입하면서 파일을 수정함
  3. 그래서 다음 배포 때 `git pull`이 "로컬 변경사항이 있어서 못 가져온다" 에러를 냄
  4. **git pull이 실패해도** 배포 스크립트가 계속 진행됨 → 옛날 코드로 빌드 번호만 새로 주입 → 겉보기엔 "배포 성공"이지만 실제로는 코드가 안 바뀜
- **해결**: `git pull` 대신 `git fetch origin main` + `git reset --hard origin/main` 사용
  - `git fetch`는 최신 코드를 다운만 받고
  - `git reset --hard`는 로컬 파일을 다운받은 코드로 **강제 덮어씌움** (로컬 변경사항 무시)
- **교훈**:
  - **deploy.yml에서 `git pull`은 절대 쓰지 말 것** → `git fetch + git reset --hard`만 사용
  - GitHub Actions 로그에서 "error" 문자열이 있는지 반드시 확인할 것
  - "배포 성공"이라고 뜨더라도 Actions 로그 전체를 확인해야 함 (중간에 에러가 있어도 최종 결과가 "success"일 수 있음)

### 사고 2: 다크모드에서 화면이 안 보이는 문제 (2026-02-15)

- **증상**: 다크모드에서 모든 글자, 카드, 버튼이 거의 안 보임. 색상을 아무리 바꿔도 안 나음
- **원인**: `.bg-grid` 클래스의 `gridPulse` 애니메이션 때문
  ```css
  /* ❌ 잘못된 코드 — 이렇게 하면 안 됨! */
  @keyframes gridPulse {
    0%, 100% { opacity: 0.03; }  /* 투명도 3% */
    50% { opacity: 0.06; }       /* 투명도 6% */
  }
  .bg-grid {
    background-image: 격자 무늬;
    animation: gridPulse 8s infinite;  /* ← 이게 문제! */
  }
  ```
  - CSS의 `opacity`는 **요소 전체**(배경 + 글자 + 자식 요소 전부)에 적용됨
  - 배경 무늬만 깜빡이게 하려던 의도였지만, 글자/카드/버튼까지 전부 투명도 3%가 되어 안 보임
  - `.bg-grid`가 12개 메인 콘텐츠 영역에 전부 사용되어 모든 탭이 영향받음
- **해결**: 격자 무늬를 `::before` 가상 요소로 분리
  ```css
  /* ✅ 올바른 코드 — 현재 적용된 방식 */
  .bg-grid { position: relative; }
  .bg-grid::before {
    content: ''; position: absolute; inset: 0;
    background-image: 격자 무늬;
    animation: gridPulse 8s infinite;  /* 가상 요소에만 적용 → 콘텐츠 영향 없음 */
    pointer-events: none; z-index: 0;
  }
  .bg-grid > * { position: relative; z-index: 1; }
  ```
- **교훈**:
  - **CSS `opacity` 애니메이션을 콘텐츠가 있는 요소에 직접 걸면 안 됨** → 반드시 `::before`/`::after` 가상 요소로 분리
  - 다크모드 문제가 생기면 색상보다 **투명도(opacity)부터 확인**할 것
  - `index.html`에서 `opacity`가 들어간 애니메이션을 수정할 때는 어떤 요소에 적용되는지 반드시 확인할 것

### 사고 3: 부서별 검수 기준이 안 뜨는 문제 (2026-02-15)

- **증상**: 설정 화면에서 "부서별 검수 기준" 섹션이 빈 칸으로 표시됨. 부서 목록이 하나도 안 나옴
- **원인 (2가지가 겹침)**:
  1. `mini_server.py`의 `/api/quality-rules` API가 빈 데이터(`{"model": "", "rubrics": {}}`)만 반환
  2. `config/yaml2json.py`가 `agents`와 `tools`만 JSON으로 변환하고, `quality_rules`는 변환 안 함
  3. 서버에 PyYAML이 없어서 YAML 파일을 직접 못 읽음 → JSON이 없으니 빈 설정 사용
  4. 프론트엔드는 `qualityRules.known_divisions` 배열로 부서 목록을 그리는데, 이 데이터가 없으니 아무것도 안 뜸
- **해결**:
  1. `mini_server.py`가 `_load_config("quality_rules")`로 설정 파일을 읽어서 `rules`, `rubrics`, `known_divisions`, `division_labels`를 반환하도록 수정
  2. `yaml2json.py`에 `quality_rules`도 변환 대상에 추가
- **교훈**:
  - **새 설정 파일(`.yaml`)을 추가하면 반드시 `yaml2json.py`의 변환 목록에도 추가할 것**
  - **미니서버 API가 빈 데이터를 반환하면 프론트엔드가 작동 안 함** → API 추가/수정 시 실제 데이터를 반환하는지 반드시 확인
  - 프론트엔드가 빈 화면이면 → 브라우저 개발자 도구(F12)에서 API 응답부터 확인할 것

## AI 도구 자동호출 규칙 (Function Calling)
- **ai_handler.py**의 `ask_ai()`가 `tools` + `tool_executor` 파라미터를 받아서 3개 프로바이더 모두 도구 자동호출 지원
- **도구 스키마**: `config/tools.yaml` (또는 `tools.json`)에서 `_load_tool_schemas()`로 로드
- **에이전트별 도구 제한**: `config/agents.yaml`의 `allowed_tools` 필드로 에이전트마다 사용 가능한 도구를 제한
  - CIO(투자분석): 투자 관련 도구만, CTO(기술개발): 기술 도구만
- **프로바이더별 차이**:
  - Anthropic: `tools` 파라미터 → `tool_use` 블록 처리
  - OpenAI: `tools` 파라미터 (function 포맷) → `tool_calls` 응답 처리
  - Google Gemini: `FunctionDeclaration` → `function_call` 파트 처리 (google-genai SDK 사용)
- **도구 실행**: `mini_server.py`의 `_call_agent()`에서 ToolPool을 통해 도구 실행
- **최대 루프**: 도구 호출 루프는 최대 5회 반복 (무한 루프 방지)

## 환경 설정
- gh CLI가 없으면 세션 시작 시 설치: `(type gh > /dev/null 2>&1) || (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install gh -y)`

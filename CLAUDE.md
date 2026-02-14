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
- 무엇을 왜 하는지 먼저 설명하고, 그다음 실행할 것
- 작업 결과를 보고할 때는 "뭘 했는지 → 왜 했는지 → 현재 상태 → 다음에 할 일" 순서로 정리할 것

## Git 작업 규칙
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

## 업데이트 기록 규칙
- 모든 작업 내용을 `docs/updates/` 폴더에 기록할 것
- 파일명 형식: `YYYY-MM-DD_작업요약.md` (예: `2026-02-13_홈페이지-디자인.md`)
- 하나의 세션(작업)이 끝날 때마다 반드시 기록 파일을 만들 것
- 노션(Notion)에 바로 복붙할 수 있는 마크다운 형식으로 작성할 것
- 기록 파일에 반드시 포함할 내용:
  1. **작업 제목** — 한 줄로 뭘 했는지 (예: "홈페이지 메인 디자인 구현")
  2. **작업 날짜** — YYYY-MM-DD 형식
  3. **작업 브랜치** — 어떤 브랜치에서 작업했는지 (예: claude/design-homepage-ui-e96Bb)
  4. **변경 사항 요약** — 뭘 바꿨는지 비개발자도 알 수 있게 쉽게 설명
     - 새로 만든 파일, 수정한 파일 목록 포함
     - 각 파일이 뭐 하는 파일인지 괄호로 설명 (예: `index.html (홈페이지 메인 화면)`)
  5. **현재 상태** — 작업이 완료됐는지, 진행 중인지, 문제가 있는지
  6. **다음에 할 일** — 이 작업 이후에 해야 할 것들 (있으면)
- 전문 용어는 절대 그냥 쓰지 말고, 반드시 괄호 안에 쉬운 설명을 붙일 것
- CEO가 읽고 바로 이해할 수 있는 수준으로 작성할 것. 이해 못 하면 의미 없음

## 기억력 보완 규칙 (대화 맥락 유지)
- **세션 시작 시**: 반드시 `docs/project-status.md` 파일을 먼저 읽을 것. 이 파일에 프로젝트의 현재 상태가 적혀 있음
- **작업 완료 시**: `docs/project-status.md` 파일을 최신 상태로 업데이트할 것
  - "현재 완료된 주요 기능", "진행 중인 작업", "다음에 할 일" 섹션을 갱신
- **대화가 길어질 때**: 중간중간 핵심 내용을 요약해서 대화에 다시 언급할 것
- **중요한 결정이 내려졌을 때**: `docs/project-status.md`의 "중요한 결정 사항" 섹션에 즉시 기록할 것
- 이 규칙의 목적: CEO와 대화 중에 클로드가 맥락을 잃어버리는 것을 방지하기 위함

## 서버 배포 규칙 (Oracle Cloud)
- **서버 주소**: `168.107.28.100` (Oracle Cloud 춘천 리전, 무료 서버)
- **자동 배포 흐름** (전체 과정):
  1. claude/ 브랜치에 [완료] 커밋 push
  2. `auto-merge-claude.yml`이 PR 생성 + main에 자동 머지
  3. 머지 성공 후 → `deploy.yml`을 **직접 실행(trigger)**시킴
  4. 서버에서 `git pull` → 파일 복사 → 미니 서버 재시작
  - **중요**: GitHub 보안 정책상, 워크플로우가 만든 push는 다른 워크플로우를 자동 실행시키지 않음. 그래서 auto-merge에서 `gh workflow run deploy.yml`로 직접 실행시키는 구조
- **워크플로우 파일**:
  - `.github/workflows/auto-merge-claude.yml` — 자동 머지 + 배포 트리거
  - `.github/workflows/deploy.yml` — 실제 서버 배포 (SSH로 접속해서 파일 복사)
- **수동 배포**: GitHub → Actions 탭 → "Deploy to Oracle Cloud Server" → "Run workflow" 버튼 클릭
- **서버 SSH 접속 정보**:
  - 사용자: `ubuntu`
  - SSH 키: GitHub Secrets에 `SERVER_SSH_KEY`로 등록됨
  - 서버 IP: GitHub Secrets에 `SERVER_IP`로 등록됨
- **주의사항**:
  - 서버 파일을 직접 수정하지 말 것 (GitHub에서 코드 수정 → 자동 배포가 정상 흐름)
  - 배포 실패 시 GitHub Actions 로그를 먼저 확인할 것

## 환경 설정
- gh CLI가 없으면 세션 시작 시 설치: `(type gh > /dev/null 2>&1) || (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install gh -y)`

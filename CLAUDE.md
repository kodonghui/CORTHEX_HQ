# CORTHEX HQ - Claude 작업 규칙

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ
- 소유자: kodonghui (비개발자 CEO)
- 언어: 한국어로 소통

## 소통 규칙
- 비개발자도 이해할 수 있도록 구체적이고 자세하고 쉽게 설명할 것
- 전문 용어를 쓸 때는 괄호 안에 쉬운 설명을 붙일 것
- 무엇을 왜 하는지 먼저 설명하고, 그다음 실행할 것

## Git 작업 규칙
- 작업 중간에도 수시로 커밋 + 푸시할 것 (중간 저장)
- 작업이 완전히 끝났을 때, 마지막 커밋 메시지에 반드시 [완료] 를 포함할 것
  - 예: "feat: 로그인 기능 추가 [완료]"
  - [완료]가 있어야 자동 머지가 작동함. 없으면 PR만 만들고 머지는 안 함
- 브랜치명은 반드시 claude/ 로 시작할 것 (자동 머지 트리거 조건)
- 브랜치 작업 후 main에 합치는 것까지 완료해야 "작업 끝"으로 간주

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

## 환경 설정
- gh CLI가 없으면 세션 시작 시 설치: `(type gh > /dev/null 2>&1) || (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install gh -y)`

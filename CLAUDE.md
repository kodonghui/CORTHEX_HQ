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
- 작업 완료 시 자동으로 커밋 + 푸시할 것
- gh CLI가 설치되어 있으면: PR 생성 + 머지까지 자동으로 처리할 것
- gh CLI가 없으면: 세션 시작 시 자동으로 설치할 것
- 브랜치 작업 후 main에 합치는 것까지 완료해야 "작업 끝"으로 간주

## 환경 설정
- gh CLI가 없으면 세션 시작 시 설치: `(type gh > /dev/null 2>&1) || (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install gh -y)`

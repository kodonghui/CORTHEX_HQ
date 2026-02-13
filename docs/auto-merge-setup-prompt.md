# Claude 자동 머지 시스템 설치 프롬프트

아래 내용을 복사해서 새 프로젝트의 Claude에게 붙여넣으세요.

---

## 프롬프트 (여기부터 복사)

```
이 프로젝트에 "Claude 자동 머지 시스템"을 설치해줘.

## 목표
Claude Code가 작업하면서 수시로 push하되,
마지막 커밋 메시지에 [완료]를 넣었을 때만 자동으로 main에 머지되게 만들어줘.

작동 방식:
- push할 때마다 → PR(Pull Request)은 자동 생성
- 커밋 메시지에 [완료]가 없으면 → PR만 만들고 머지는 안 함 (작업 중이니까)
- 커밋 메시지에 [완료]가 있으면 → 자동으로 main에 머지 + 브랜치 삭제

이렇게 하면 작업 중간에 push해도 안전하고, 끝났을 때만 합쳐짐.

## 설치할 파일 2개

### 파일 1: .github/workflows/auto-merge-claude.yml

GitHub Actions 워크플로우 파일이야. 아래 동작을 그대로 구현해줘:

- 트리거 조건: claude/ 로 시작하는 브랜치에 push될 때 자동 실행
- 권한: contents: write, pull-requests: write
- 동작 순서:
  1. 최신 커밋 메시지를 확인
  2. 해당 브랜치로 기존 PR이 있는지 확인
  3. 없으면 새 PR 자동 생성 (base: main, title: "Auto-merge: 브랜치명")
  4. 커밋 메시지에 [완료]가 없으면 → "PR만 생성하고 머지는 건너뜀" 출력 후 exit 0
  5. [완료]가 있으면 → 10초 대기 후 머지 시도 (--merge --delete-branch 옵션)
  6. 머지 실패하면 10초 대기 후 재시도 (최대 3회)
  7. 3회 다 실패하면 에러로 종료
- GH_TOKEN은 ${{ github.token }} 사용 (별도 토큰 설정 불필요)

### 파일 2: CLAUDE.md (프로젝트 루트)

이미 CLAUDE.md가 있으면 아래 내용을 기존 내용 아래에 추가해줘.
없으면 새로 만들어줘.

추가할 내용:

## Git 작업 규칙
- 작업 중간에도 수시로 커밋 + 푸시할 것 (중간 저장)
- 작업이 완전히 끝났을 때, 마지막 커밋 메시지에 반드시 [완료]를 포함할 것
  - 예: "feat: 로그인 기능 추가 [완료]"
  - [완료]가 있어야 자동 머지가 작동함. 없으면 PR만 만들고 머지는 안 함
- 브랜치명은 반드시 claude/ 로 시작할 것 (자동 머지 트리거 조건)
- 브랜치 작업 후 main에 합치는 것까지 완료해야 "작업 끝"으로 간주

## 설치 후 확인사항
1. .github/workflows/auto-merge-claude.yml 파일이 만들어졌는지 확인
2. CLAUDE.md에 Git 작업 규칙이 들어갔는지 확인
3. 두 파일을 커밋하고 main에 push해줘
4. push 완료되면 "설치 완료"라고 알려줘

## 주의사항
- GitHub 저장소 Settings → Actions → General에서 "Allow GitHub Actions to create and approve pull requests" 가 켜져 있어야 해. 이건 사람이 직접 해야 하니까, 설치 끝나면 이 설정을 켜라고 안내해줘.
- protected branch 규칙이 있으면 자동 머지가 안 될 수 있어. 이것도 안내해줘.
```

---

## 설치 후 대표님이 직접 해야 할 것 (1회만)

GitHub 웹사이트에서:
1. 저장소 → **Settings** → **Actions** → **General**
2. 맨 아래 **"Allow GitHub Actions to create and approve pull requests"** 체크
3. **Save** 클릭

이거 한 번만 켜두면 그 다음부터는 전부 자동입니다.

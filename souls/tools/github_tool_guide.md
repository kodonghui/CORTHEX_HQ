# github_tool — GitHub 프로젝트 관리 도구 가이드

## 이 도구는 뭔가요?
GitHub(개발자들이 코드를 저장하고 협업하는 플랫폼)에서
이슈(할일/버그), PR(코드 변경 요청), 커밋(코드 저장 이력), 저장소 통계를 조회하는 도구입니다.
실제로 개발팀장이 "지금 버그가 몇 개야? 이번 주 개발 진행 상황은?" 확인하는 것과 같습니다.

## 어떤 API를 쓰나요?
- **GitHub REST API** (api.github.com)
- 비용: **무료** (시간당 5,000건)
- 필요한 키: `GITHUB_TOKEN`, `GITHUB_REPO` (예: "kodonghui/CORTHEX_HQ")

## 사용법

### action=issues (이슈 목록)
```
action=issues
action=issues, state="open"
action=issues, state="closed"
```
- 저장소의 이슈(할일/버그/기능요청) 목록
- state로 열린 이슈/닫힌 이슈 필터링

### action=prs (PR 목록)
```
action=prs
action=prs, state="open"
```
- Pull Request (코드 변경 요청) 목록
- 코드 리뷰 대기 중인 PR, 머지된 PR 등 확인

### action=commits (최근 커밋)
```
action=commits, count=10
```
- 최근 커밋(코드 저장) 이력
- 누가, 언제, 무엇을 변경했는지 확인
- count로 가져올 개수 지정 (기본 10개)

### action=repo_stats (저장소 통계)
```
action=repo_stats
```
- 저장소 전체 통계: 크기, 브랜치 수, 기여자 수, 언어 비율 등

---

## 이 도구를 쓰는 에이전트들

### 1. CTO 처장 (기술개발처장)
**언제 쓰나?** 전체 개발 현황을 파악할 때
**어떻게 쓰나?**
- `action=issues, state="open"` → 해결 안 된 문제가 몇 개인지
- `action=prs, state="open"` → 코드 리뷰 대기 중인 PR
- `action=repo_stats` → 프로젝트 전체 건강도

**실전 시나리오:**
> CEO가 "개발 진행 상황 보고해" 라고 하면:
> 1. `github_tool action=issues, state="open"` → 열린 이슈 15개
> 2. `github_tool action=prs, state="open"` → 대기중 PR 3개
> 3. `github_tool action=commits, count=20` → 이번 주 커밋 20개
> 4. **보고:** "열린 이슈 15개 (버그 5, 기능 10), PR 3개 리뷰 대기, 이번 주 활발한 개발 진행 중"

### 2. 백엔드/API Specialist
**언제 쓰나?** 자기 담당 이슈 확인, 코드 변경 이력 추적
**어떻게 쓰나?**
- `action=issues` → 백엔드 관련 이슈 확인
- `action=commits, count=10` → 최근 코드 변경 확인
- code_quality(코드 품질)와 함께 → 이슈 파악 + 품질 검사 일괄 진행

### 3. DB/인프라 Specialist
**언제 쓰나?** 배포/인프라 관련 이슈, CI/CD 현황 확인
**어떻게 쓰나?**
- `action=repo_stats` → 저장소 크기, 브랜치 상태
- `action=issues, state="open"` → 인프라 관련 이슈
- code_quality(코드 품질)와 함께 → 배포 전 최종 점검

---

## 주의사항
- `GITHUB_REPO`가 설정되어 있어야 합니다 (예: "kodonghui/CORTHEX_HQ").
- 비공개 저장소는 적절한 권한이 있는 토큰이 필요합니다.
- 이슈/PR이 많은 저장소는 결과가 잘릴 수 있습니다 (최대 30개).

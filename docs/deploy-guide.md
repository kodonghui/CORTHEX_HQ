# 배포 트러블슈팅 + 과거 사고 기록

> CLAUDE.md에서 분리된 상세 문서. 배포 문제 발생 시 이 파일을 Read로 읽고 따를 것.

## 배포 안 되는 흔한 원인들

| 증상 | 원인 | 해결 |
|------|------|------|
| 배포 성공인데 화면이 안 바뀜 | **브라우저 캐시** | `Ctrl+Shift+R` 또는 주소 뒤에 `?v=2` |
| 배포 성공인데 화면이 안 바뀜 (2) | **nginx 캐시** | deploy.yml이 자동으로 `no-cache` 헤더 설정 (2026-02-15) |
| 배포 성공인데 화면이 안 바뀜 (3) | **서버 git pull 실패** (충돌) | `git fetch + git reset --hard` 사용 (deploy.yml에 반영됨) |
| Actions "success"인데 접속 안됨 | **서버 다운/방화벽** | Oracle Cloud 콘솔 → 인스턴스 상태 + Security List 포트 80 확인 |
| `pip 설치 실패` 경고 | PyYAML 설치 실패 | 무시 가능 |
| 빌드 번호가 `PLACEHOLDER` | 로컬에서 직접 열었음 | `http://corthex-hq.com`으로 접속 |
| `https://` 안 됨 | certbot 미실행 | 배포 한 번 더 실행하면 자동 발급 |

## 배포 확인 방법 3가지
1. **웹**: `http://corthex-hq.com` → 좌측 상단 "빌드 #XX"
2. **JSON**: `http://corthex-hq.com/deploy-status.json`
3. **GitHub Actions**: https://github.com/kodonghui/CORTHEX_HQ/actions

## 배포 흐름 상세 (디버깅용)
```
[코드 수정] → [git push] → [auto-merge.yml] → [PR 생성 + main 머지]
    → [deploy.yml 직접 실행] → [서버 SSH 접속]
    → [git fetch + git reset --hard] (⚠️ git pull 아님!)
    → [sed로 빌드번호 주입] → [/var/www/html/index.html 복사]
    → [corthex 서비스 재시작] → [deploy-status.json 생성]
```

## nginx 캐시 방지
- deploy.yml이 첫 배포 시 `Cache-Control: no-cache` 헤더 자동 추가
- 확인: `curl -I http://corthex-hq.com` → `Cache-Control: no-cache` 있으면 정상

## 과거 사고 기록 (같은 실수 반복 금지!)

| # | 날짜 | 분류 | 사고 내용 | 해결/교훈 |
|---|------|------|----------|----------|
| 1 | 2026-02-15 | 배포 | `git pull` 충돌로 코드 안 바뀌는데 "배포 성공" | `git fetch + git reset --hard`. Actions 로그 전체 확인 |
| 2 | 2026-02-15 | 다크모드 | `.bg-grid`에 `opacity` 직접 → 글자/카드 안 보임 | `::before` 가상 요소로 분리 |
| 3 | 2026-02-15 | 부서 목록 | `yaml2json.py` 변환 목록에 새 yaml 미추가 → 빈 화면 | yaml 추가 시 yaml2json.py에도 추가 |
| 4 | 2026-02-19 | 팀 작업 | 서브에이전트 `git checkout` → index.html 수정 6개 유실 | 서브에이전트 git 명령어 절대 금지 |
| 5 | 2026-02-20 | KIS | IS_MOCK 변경 후 캐시 토큰 만료 에러 | IS_MOCK 변경 시 토큰 캐시 무효화 필요 |

# CORTHEX E2E 테스트

실서버(`corthex-hq.com`)에서 핵심 기능을 자동 검증합니다.

## 실행법

```bash
# 기본 실행 (비밀번호 기본값: corthex2026)
pytest tests/e2e/ -v

# 비밀번호가 변경된 경우
E2E_PASSWORD=내비밀번호 pytest tests/e2e/ -v

# 특정 테스트만
pytest tests/e2e/test_core_flows.py::TestFeedbackPin -v
```

## 테스트 시나리오

| # | 클래스 | 검증 내용 |
|---|--------|---------|
| 1 | TestLogin | 로그인 성공/실패, 토큰 유효성 |
| 2 | TestFeedbackPin | 피드백 핀 저장 → 목록에 표시되는지 |
| 3 | TestAgents | 에이전트 목록 존재, 대시보드 응답 |
| 4 | TestFeedbackRating | 좋아요/아쉬워요 전송/취소/통계 |
| 5 | TestHealth | 서버 온라인, 로그 API 접근 |

## 언제 실행하나

- 기능 구현 완료 후 → 배포 전 반드시 실행
- 버그 수정 후 → 재발 방지 확인
- 배포 CI/CD에 통합 예정 (deploy.yml)

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `E2E_BASE_URL` | `https://corthex-hq.com` | 테스트 대상 서버 |
| `E2E_PASSWORD` | `corthex2026` | CEO 로그인 비밀번호 |

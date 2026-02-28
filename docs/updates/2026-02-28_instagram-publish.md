# 2026-02-28 — Instagram 자동 발행 기능 추가

## 요약
Instagram Graph API를 통한 자동 발행 기능을 활성화.
기존 잠금 상태의 `instagram_publisher.py`를 환경변수 토큰 방식으로 전환하여 즉시 사용 가능하도록 함.

## 변경 사항

### instagram_publisher.py (기존 파일 수정)
- OAuth 의존 제거 → `INSTAGRAM_ACCESS_TOKEN` 환경변수 직접 사용
- User ID 자동 조회: `GET /me?fields=id,username` (`INSTAGRAM_USER_ID` 미설정 시)
- httpx 타임아웃 추가 (연결 10s, API 30s)
- 기존 기능 유지: 단일 이미지, 캐러셀(최대 10장), 릴스(동영상)

### sns_manager.py
- Instagram import 활성화 (주석 해제)
- `ALLOWED_PLATFORMS`에 "instagram" 추가 (4→5개)
- `BLOCKED_PLATFORM_MSG`에서 "instagram" 제거
- `_handle_status()`에 Instagram 환경변수 토큰 상태 표시 추가

### agents.yaml — CMO system_prompt
- 지원 플랫폼 4개→5개 (Instagram 추가)
- "❌ 사용 불가: Instagram" 문구 제거

### tools.yaml / tools.json
- sns_manager 도구 설명: 4개→5개 플랫폼, Instagram 추가
- platform 파라미터 설명에 instagram 추가

## 수정 파일
| 파일 | 변경 |
|------|------|
| `src/tools/sns/instagram_publisher.py` | OAuth→환경변수 토큰, User ID 자동 조회 |
| `src/tools/sns/sns_manager.py` | Instagram 잠금 해제 |
| `config/agents.yaml` | CMO 지원 플랫폼 5개로 확장 |
| `config/tools.yaml` | sns_manager 설명 업데이트 |
| `config/tools.json` | sns_manager 설명 업데이트 |

## 사용법 (마케팅팀장이 실행)
```
sns_manager(action="submit", platform="instagram", media_urls=["이미지URL"], body="캡션 텍스트", tags=["태그1"])
```
→ CEO 승인 후 → `sns_manager(action="publish", request_id="xxx")`

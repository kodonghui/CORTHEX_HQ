# SNS + DEVOPS 전수검사 결과 보고서

## 버전
3.01.001

## 작업 날짜
2026-02-18

## 검사 범위
- `src/integrations/__init__.py` (1줄, 빈 파일)
- `src/integrations/sns_publisher.py` (312줄)
- `src/integrations/telegram_bot.py` (153줄)
- `.github/workflows/deploy.yml` (405줄)
- `.github/workflows/auto-merge-claude.yml` (86줄)

---

## 1. SNS 전수검사 결과 (src/integrations/)

### 1-1. 금지 모델명 검사

| 검사 대상 | 결과 |
|----------|------|
| `claude-haiku-4-6` | 0건 — 이상 없음 |
| `gpt-4o`, `gpt-4o-mini` | 0건 — 이상 없음 |
| `gpt-4.1`, `gpt-4.1-mini` | 0건 — 이상 없음 |

**판정: 합격** — SNS 파일에는 모델명 자체가 없음. AI를 직접 호출하지 않는 순수 발행(publish) 모듈이라 모델명 이슈 없음.

---

### 1-2. 환경변수 기반 연결 상태 확인

**InstagramPublisher (sns_publisher.py, 38~112줄)**
- `enabled` 여부를 `config/sns.yaml` → `instagram.enabled`로 읽음 (현재 `false`)
- `access_token`은 `os.getenv("INSTAGRAM_ACCESS_TOKEN", "")` 방식으로 읽음
- `ig_user_id`는 `os.getenv("INSTAGRAM_USER_ID", "")` 방식으로 읽음
- 발행 전 `not self.enabled`, `not self.access_token or not self.ig_user_id` 이중 체크 — 올바름
- **판정: 합격**

**YouTubePublisher (sns_publisher.py, 167~274줄)**
- `enabled` 여부를 `config/sns.yaml` → `youtube.enabled`로 읽음 (현재 `false`)
- `client_id`, `client_secret`, `refresh_token` 3종 모두 환경변수로 읽음
- 발행 전 `not self.enabled`, `not self.client_id or not self.client_secret or not self.refresh_token` 이중 체크 — 올바름
- **판정: 합격**

**SNSPublisher.get_status() (sns_publisher.py, 288~299줄)**
- Instagram: `enabled` + `configured` (access_token AND ig_user_id 둘 다 있어야 configured)
- YouTube: `enabled` + `configured` (client_id AND refresh_token 있어야 configured)
- 환경변수 유무로 연결 상태를 판단하는 구조 — 올바름
- **판정: 합격**

---

### 1-3. Tistory Selenium (KAKAO_ID/PW) 사용 여부 확인

- `sns_publisher.py`에는 Tistory 관련 코드 없음 (Instagram + YouTube만 구현됨)
- `telegram_bot.py`에도 Tistory 없음
- `__init__.py`는 빈 파일
- **판정: 해당 없음** — Tistory는 `src/tools/` 또는 `src/integrations/` 외부에 구현되어 있을 가능성 있음. 이번 전수검사 범위 밖.

---

### 1-4. 에러 처리 검사

**Instagram publish_photo 에러 처리 (39~112줄):**
- 컨테이너 생성 실패 → `PublishResult(success=False, error=...)`로 안전하게 반환
- 상태 폴링 중 ERROR → `PublishResult(success=False, error="미디어 처리 실패")` 반환
- 발행 실패 → error 메시지 포함해서 반환
- **판정: 합격**

**Instagram publish_reel 에러 처리 (114~160줄):**
- 동일 패턴으로 에러 처리됨
- **판정: 합격**

**YouTube upload_video 에러 처리 (200~274줄):**
- 파일 존재 여부 확인 (`video_file.exists()`)
- OAuth 토큰 갱신 실패 시 반환
- 업로드 초기화 실패 (status_code not in 200, 308)
- Upload URL 누락 시 반환
- **판정: 합격**

**telegram_bot.py 에러 처리 (130~144줄):**
- `_execute_command()`에서 `try/except Exception`으로 에러 캐치 후 사용자에게 텔레그램 메시지 전송
- **판정: 합격**

---

### 1-5. SNS 버그 — 발견 없음

SNS 코드에서 발견된 버그 없음. 단, 아래 **누락 항목** 확인:

#### [경고] deploy.yml에 YouTube + Instagram USER_ID 환경변수 누락

- `config/sns.yaml`에서 사용하는 환경변수 목록:
  - `INSTAGRAM_ACCESS_TOKEN` — deploy.yml에 있음 (INSTA_ACCESS_TOKEN)
  - `INSTAGRAM_USER_ID` — **deploy.yml에 없음** (미전달)
  - `YOUTUBE_CLIENT_ID` — **deploy.yml에 없음** (미전달)
  - `YOUTUBE_CLIENT_SECRET` — **deploy.yml에 없음** (미전달)
  - `YOUTUBE_REFRESH_TOKEN` — **deploy.yml에 없음** (미전달)

- 결과: SNS 발행 기능을 활성화(`enabled: true`)해도 서버에 위 4개 환경변수가 전달되지 않아 "자격증명 미설정" 오류로 발행 불가
- 이 문제는 deploy.yml 수정이 필요하므로 DEVOPS 섹션에서 수정 내역 확인

---

## 2. DEVOPS 전수검사 결과 (.github/workflows/)

### 2-1. deploy.yml — git pull vs git fetch+reset 확인

**검사 결과: 올바르게 구현됨**

```bash
# deploy.yml 1단계 코드 (163~167줄)
# ⚠️ 이전 배포에서 sed가 index.html을 수정하므로 로컬 변경사항 발생
# git pull이 실패하지 않도록 로컬 변경사항을 먼저 버림
git fetch origin main
git reset --hard origin/main
```

`git pull` 대신 `git fetch + git reset --hard` 올바르게 사용 중.
CLAUDE.md 사고 1번 교훈이 이미 반영되어 있음.

**판정: 합격 — 수정 불필요**

---

### 2-2. 환경변수 전달 검사

**전달되는 환경변수 목록 (deploy.yml 23~65줄):**

| 카테고리 | Secret 이름 | 서버 env 변수명 |
|---------|------------|----------------|
| AI API | ANTHROPIC_API_KEY | ANTHROPIC_API_KEY |
| AI API | OPENAI_API_KEY | OPENAI_API_KEY |
| AI API | GOOGLE_API_KEY | GOOGLE_API_KEY |
| 텔레그램 | TELEGRAM_BOT_TOKEN | TELEGRAM_BOT_TOKEN |
| 텔레그램 | TELEGRAM_CEO_CHAT_ID | TELEGRAM_CEO_CHAT_ID |
| SNS | INSTAGRAM_APP_ID | INSTAGRAM_APP_ID |
| SNS | INSTAGRAM_APP_SECRET | INSTAGRAM_APP_SECRET |
| SNS | INSTAGRAM_ACCESS_TOKEN | INSTAGRAM_ACCESS_TOKEN |
| SNS | INSTAGRAM_REDIRECT_URI | INSTAGRAM_REDIRECT_URI |
| Google OAuth | GOOGLE_CLIENT_ID | GOOGLE_CLIENT_ID |
| Google OAuth | GOOGLE_CLIENT_SECRET | GOOGLE_CLIENT_SECRET |
| Google OAuth | GOOGLE_REDIRECT_URI | GOOGLE_REDIRECT_URI |
| 카카오 | KAKAO_REST_API_KEY | KAKAO_REST_API_KEY |
| 카카오 | KAKAO_ID | KAKAO_ID |
| 카카오 | KAKAO_PW | KAKAO_PW |
| 네이버 | NAVER_CLIENT_ID, NAVER_ID, NAVER_PW 등 | 동일 |
| 다음 | DAUM_ID, DAUM_PW 등 | 동일 |
| 기타 | DART_API_KEY, ECOS_API_KEY 등 전문가 도구 | 동일 |

**누락 환경변수 (버그):**

| 누락된 Secret | 필요한 이유 |
|--------------|-----------|
| `INSTAGRAM_USER_ID` | sns_publisher.py의 `ig_user_id_env: "INSTAGRAM_USER_ID"` |
| `YOUTUBE_CLIENT_ID` | sns_publisher.py의 `client_id_env: "YOUTUBE_CLIENT_ID"` |
| `YOUTUBE_CLIENT_SECRET` | sns_publisher.py의 `client_secret_env: "YOUTUBE_CLIENT_SECRET"` |
| `YOUTUBE_REFRESH_TOKEN` | sns_publisher.py의 `refresh_token_env: "YOUTUBE_REFRESH_TOKEN"` |

이 4개가 없으면 SNS 발행 기능을 활성화해도 동작하지 않음.

**판정: 결함 발견 — deploy.yml에 4개 환경변수 추가 필요**

---

### 2-3. Selenium / Chrome 설치 여부 확인

- deploy.yml 전체 스크립트에서 `selenium`, `chrome`, `chromedriver` 키워드 0건
- 현재 SNS 발행이 Selenium을 쓰지 않음 (Instagram Graph API + YouTube Data API 방식)
- Tistory가 Selenium을 쓸 경우 해당 도구가 src/tools/에 있을 것으로 예상 — 현재 범위 밖
- **판정: 현재 코드 기준 Selenium 설치 불필요. 이상 없음.**

---

### 2-4. auto-merge-claude.yml 검사

**검사 항목:**
1. `claude/` 브랜치 push 트리거 — 올바름 (`branches: - 'claude/**'`)
2. `[완료]` 키워드 확인 후 머지 — 올바름 (50~56줄)
3. 머지 후 deploy.yml 직접 실행 — 올바름 (`gh workflow run deploy.yml --ref main`)
4. GitHub 보안 정책 우회 주석 포함 — 올바름 (81~82줄)
5. 머지 3회 재시도 로직 — 올바름 (64~73줄)
6. PR 중복 생성 방지 (`EXISTING_PR` 확인) — 올바름 (35~47줄)

**판정: 합격 — 수정 불필요**

---

## 3. 수정 내역

### 수정 1: deploy.yml — YouTube + Instagram USER_ID 환경변수 추가

**수정 위치:** `.github/workflows/deploy.yml`

**추가된 내용:**
- `env:` 섹션에 4개 Secret 변수 추가:
  - `INSTA_USER_ID: ${{ secrets.INSTAGRAM_USER_ID }}`
  - `YOUTUBE_CLIENT_ID_VAR: ${{ secrets.YOUTUBE_CLIENT_ID }}`
  - `YOUTUBE_CLIENT_SECRET_VAR: ${{ secrets.YOUTUBE_CLIENT_SECRET }}`
  - `YOUTUBE_REFRESH_TOKEN_VAR: ${{ secrets.YOUTUBE_REFRESH_TOKEN }}`
- `envs:` 목록에 4개 추가
- `script:` 5.9단계에 YouTube + INSTAGRAM_USER_ID 설정 블록 추가

**수정 이유:** sns_publisher.py가 이 환경변수를 서버에서 읽어야 SNS 발행이 동작함. 없으면 "자격증명 미설정" 오류.

---

## 4. 최종 판정 요약

| 검사 항목 | 판정 | 조치 |
|----------|------|------|
| SNS 금지 모델명 | 합격 | 없음 |
| Instagram 환경변수 기반 연결 상태 | 합격 | 없음 |
| YouTube 환경변수 기반 연결 상태 | 합격 | 없음 |
| SNS 에러 처리 | 합격 | 없음 |
| Tistory Selenium (범위 밖) | 해당 없음 | 없음 |
| deploy.yml git pull 사용 여부 | 합격 (이미 fetch+reset) | 없음 |
| deploy.yml 환경변수 전달 | **결함** | YouTube 3개 + INSTAGRAM_USER_ID 추가 완료 |
| deploy.yml Selenium 설치 | 해당 없음 | 없음 |
| auto-merge-claude.yml | 합격 | 없음 |

**발견된 버그: 1건 (환경변수 4개 누락)**
**수정 완료: 1건**
**추가 조치 필요: GitHub Secrets에 INSTAGRAM_USER_ID, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN 등록 (SNS 발행 기능 사용 시)**

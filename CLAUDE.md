# CORTHEX HQ - Claude 작업 규칙

## ⚡ 세션 시작 (매 세션 반드시)
1. `git fetch origin && git status` 실행
   - 미커밋 있으면 → **작업 중지**, CEO에게 "미커밋 있습니다. 커밋할까요?" 물어볼 것
   - 깨끗하면 → `git checkout main && git pull origin main` 즉시 실행
2. 새 브랜치에서 작업: `git checkout -b claude/작업명 origin/main` (main 직접 작업 금지)
3. CORTHEX 요청 시 먼저 코드 탐색: `docs/project-status.md` → `docs/updates/` 최근 파일 → 관련 코드 Read

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ
- 소유자: kodonghui (비개발자 CEO)
- 언어: 한국어 소통 | 도메인: `corthex-hq.com`

## 소통 규칙 (예외 없이)
- CEO는 비개발자 → 전문 용어에 괄호 설명 필수. 존댓말 사용
- **구체적으로**: "최적화했습니다"(X) → "로딩 3초→1초로 줄었습니다"(O)
- **구조적으로**: 장문 시 제목/번호/표/구분선 사용. 글 덩어리 금지
- **한국어로**: 도구 권한 요청도 한국어. "grep in?"(X) → "이 폴더에서 검색할까요?"(O)
- **뻔한 질문 금지**: "커밋할까요?" "배포할까요?" → 바로 실행
- **"논의" 키워드 → 코딩 금지**: 아이디어/옵션 + 추천 제시. CEO 결정 후 실행
- **소신 발언 필수**: B가 더 나으면 먼저 말할 것. CEO가 최종 결정권자
- **"로컬에서 확인" 금지** → 항상 `http://corthex-hq.com`에서 확인
- 작업 완료 = 커밋 + 푸시 + 배포 + 서버 확인 + CEO에게 빌드번호 체크리스트 보고

## Git 규칙
- 매 작업마다 `origin/main` 기준 새 브랜치: `claude/작업명`
- 마지막 커밋에 `[완료]` 포함 → 자동 머지 트리거
- 작업 중간에도 수시로 커밋 + 푸시 (중간 저장)
- 기존 브랜치에 무관한 작업 추가 금지

## 파일 수정 안전 규칙
- `web/templates/index.html`은 **Write 전체 덮어쓰기 절대 금지** → Edit 부분 수정만

## 외부 API 코딩 시
- KIS, OpenAI, Google 등 외부 API 코드 → **반드시 WebSearch로 최신 공식 문서 먼저 확인**
- 기억에 의존해서 TR_ID, 엔드포인트, 파라미터명 쓰면 안 됨
- KIS 참고: [KIS Developers](https://apiportal.koreainvestment.com), [공식 GitHub](https://github.com/koreainvestment/open-trading-api)

## GitHub Secrets (2026-02-18 전체 등록 완료 — 다시 물어보지 말 것!)
모든 API 키가 등록됨. CEO에게 "API 키 알려주세요" 절대 금지. deploy.yml이 서버 `/home/ubuntu/corthex.env`에 자동 반영.

| 분류 | Secret 이름 |
|------|------------|
| AI | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_GEMINI_API_KEY` |
| 노션 | `NOTION_API_KEY`, `NOTION_DEFAULT_DB_ID` |
| GitHub | `REPO_ACCESS_TOKEN` |
| 텔레그램 | `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CEO_CHAT_ID` |
| 공공/리서치 | `DART_API_KEY`, `ECOS_API_KEY`, `KIPRIS_API_KEY`, `LAW_API_KEY`, `SERPAPI_KEY` |
| 이메일 | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` |
| 인스타그램 | `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_REDIRECT_URI` |
| Google OAuth | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `GOOGLE_CALENDAR_REDIRECT_URI` |
| 카카오 | `KAKAO_REST_API_KEY`, `KAKAO_ID`, `KAKAO_PW` |
| 네이버 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `NAVER_ID`, `NAVER_PW`, `NAVER_BLOG_ID`, `NAVER_REDIRECT_URI` |
| 다음 | `DAUM_CAFE_ID`, `DAUM_CAFE_BOARD_ID`, `DAUM_ID`, `DAUM_PW` |
| 서버 | `SERVER_IP_ARM`, `SERVER_SSH_KEY_ARM` (건드리지 말 것) |
| KIS | `KOREA_INVEST_APP_KEY`, `KOREA_INVEST_APP_SECRET`, `KOREA_INVEST_ACCOUNT`, `KOREA_INVEST_IS_MOCK` |
| KIS 모의 | `KOREA_INVEST_MOCK_APP_KEY`, `KOREA_INVEST_MOCK_APP_SECRET`, `KOREA_INVEST_MOCK_ACCOUNT` |
| 기타 | `SNS_BROWSER_HEADLESS` |

키 재등록: `.venv/Scripts/python set_secrets.py` (실행 후 자동 삭제)

## UI/UX 규칙
- 언어: 한국어 | 시간대: `Asia/Seoul` (KST)
- 프레임워크: Tailwind CSS + Alpine.js (CDN)
- 디자인: `hq-*` 커스텀 컬러 토큰
- **폰트**: Pretendard 단일 통일. `font-mono`는 숫자/코드/종목코드에만. Noto Serif KR는 `.font-title`만
- ❌ 새 Google 폰트 추가, `font-sans` 오버라이드 금지

## 하드코딩 금지 (매우 중요!)
- 모델명 정의는 딱 2곳: `config/agents.yaml` + `config/models.yaml`
- mini_server.py, ai_handler.py, index.html에 모델명 문자열 직접 쓰면 안 됨
- **새 모델 추가/변경 시 10곳 체크리스트**:
  1. `config/agents.yaml` 2. `config/models.yaml` 3. `yaml2json.py` 실행
  4. mini_server.py AGENTS 리스트 5. `get_available_models()` 6. `_TG_MODELS`
  7. ai_handler.py `_PRICING` 8. 기본값/폴백 모델 9. index.html 모델 표시명 10. 추론 레벨 매핑

## 실제 존재하는 모델명 (이 목록이 절대 기준!)
"있을 것 같은" 모델명 지어내기 금지. 아래 목록에 없으면 API 오류 발생.

| 모델 ID | 표시명 | 용도 |
|---------|--------|------|
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | 기본 (대부분 에이전트) |
| `claude-opus-4-6` | Claude Opus 4.6 | 최고급 (CLO, CSO) |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 | 경량 Anthropic |
| `gpt-5.2-pro` | GPT-5.2 Pro | CIO |
| `gpt-5.2` | GPT-5.2 | 투자 분석가들 |
| `gpt-5` | GPT-5 | 일반 OpenAI |
| `gpt-5-mini` | GPT-5 Mini | 경량 OpenAI |
| `gemini-3.1-pro-preview` | Gemini 3.1 Pro | CMO, 콘텐츠 |
| `gemini-2.5-pro` | Gemini 2.5 Pro | Gemini 고급 |
| `gemini-2.5-flash` | Gemini 2.5 Flash | 경량 Gemini |

- ⚠️ `claude-haiku-4-6` 존재하지 않음 | ⚠️ `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` 구버전 금지

## 데이터 저장 (SQLite DB)
- 모든 웹 데이터는 SQLite DB(`settings` 테이블)에 저장. JSON 파일(`data/*.json`) 저장 금지 (배포 시 날아감)
- `save_setting(key, value)` / `load_setting(key, default)` 사용
- DB 위치: `/home/ubuntu/corthex.db` (git 밖 → 배포해도 안 날아감)

## 서버 배포 (Oracle Cloud ARM 24GB)
- **스펙**: ARM Ampere A1, 4코어 24GB RAM (Oracle Cloud 춘천, Always Free)
- **접속**: `SERVER_IP_ARM` + `SERVER_SSH_KEY_ARM` (GitHub Secrets)
- **도메인**: `corthex-hq.com` (Cloudflare) | HTTPS: Let's Encrypt 자동
- **자동 배포 흐름**: claude/ 브랜치 [완료] push → auto-merge → deploy.yml 직접 실행 → 서버 SSH → git fetch + reset --hard → 재시작
- **중요**: 서버에서 `git pull` 금지! 반드시 `git fetch + git reset --hard`
- **수동 배포**: GitHub → Actions → "Deploy to Oracle Cloud Server" → Run workflow
- **서버 구조**: `/home/ubuntu/CORTHEX_HQ/` (코드) | `/home/ubuntu/corthex.db` (DB) | `/home/ubuntu/corthex.env` (환경변수) | `/var/www/html/` (nginx 정적파일)
- **배포 문제 시** → `docs/deploy-guide.md` 참조

## 빌드 번호
- 소스: `deploy.yml`의 `${{ github.run_number }}`만. 커밋 개수와 무관
- 작업 완료 시: `gh run list --workflow=deploy.yml --limit=1`로 확인 → CEO에게 체크리스트 표 제공
- CEO 보고 시 **"빌드#N"** 사용 (PR#N 아님!)

## 버전 번호
- 형식: `X.YY.ZZZ` | 현재: `3.01.000`
- 큰 변경 → YY 올림 + ZZZ 리셋 | 작은 변경 → ZZZ만 올림

## 디버그 URL
- 버그 시 `/api/debug/xxx` 엔드포인트 즉석 생성 → CEO에게 URL 제공
- 보안: 계좌번호 마스킹, API 키 노출 금지

## AI 도구 자동호출 (Function Calling)
- `ai_handler.py`의 `ask_ai()`가 3개 프로바이더 도구 자동호출 지원
- 도구 스키마: `config/tools.yaml` | 에이전트별 제한: `config/agents.yaml`의 `allowed_tools`
- 도구 호출 루프 최대 5회 (무한 루프 방지)

## ⚠️⚠️⚠️ 업데이트 기록 + 버그리포트 (절대 빠뜨리지 말 것!!!) ⚠️⚠️⚠️

**이 규칙은 모든 세션, 모든 Claude 인스턴스, 모든 팀원에게 적용됩니다.**
**업데이트 기록을 안 쓰면 CEO가 뭐가 바뀌었는지 모릅니다. 반드시 쓰세요.**
**팀원(서브에이전트 포함)도 자기 작업이 끝나면 반드시 기록을 남겨야 합니다.**

### 1. 작업 완료 시 반드시 할 것 (빠뜨리면 미완성 취급)

| 순서 | 해야 할 일 | 파일 |
|------|----------|------|
| ① | **업데이트 기록 작성** | `docs/updates/YYYY-MM-DD_작업요약.md` |
| ② | **프로젝트 현황 갱신** | `docs/project-status.md` |
| ③ | **커밋 + 푸시 + 배포** | `[완료]` 태그 포함 |
| ④ | **CEO에게 빌드번호 체크리스트 보고** | 채팅으로 직접 |

**① ~ ④를 전부 하지 않으면 "작업 완료"가 아닙니다.**

### 2. 업데이트 기록 파일 형식 (`docs/updates/YYYY-MM-DD_작업요약.md`)

```markdown
# [작업 제목] — YYYY-MM-DD

## 기본 정보
- **날짜**: 2026-02-21
- **버전**: 3.01.001
- **브랜치**: claude/fix-something
- **빌드**: #384

## 변경 사항

### 🔧 수정한 것
| 파일 | 수정 내용 (CEO가 이해할 수 있게 쉽게) |
|------|-------------------------------------|
| `web/mini_server.py` | 자동매매 버튼 누르면 실제 주문이 나가도록 수정 |
| `web/kis_client.py` | KIS 토큰 만료되어도 잔고 ₩0이 아닌 캐시된 값 표시 |

### 🐛 발견한 버그 (수정 여부 무관하게 전부 기록!)
| 버그 | 원인 | 상태 |
|------|------|------|
| 비서실 태그 잘못 표시 | AI가 가짜 에이전트 ID 생성 | ✅ 수정 완료 |
| 환율 1450원 고정 | 실시간 환율 미연동 | 🔴 미수정 (다음 세션) |

### 📊 현재 상태
- 자동매매: KIS 실계좌 연결됨, 실매매 가능
- 활동 로그: 전체 API 요청 자동 기록 추가

### 📋 다음에 할 일
- 환율 실시간 반영
- CIO 분석 정확도 개선
```

### 3. 버그리포트 규칙 (발견 즉시 기록!)

**버그를 발견하면 수정 여부와 관계없이 반드시 기록하세요.**
수정했으면 "✅ 수정 완료", 못 했으면 "🔴 미수정" 표시.

- **어디에 기록?**: 업데이트 기록 파일의 "발견한 버그" 섹션
- **수정 못 한 버그**: `docs/TODO.md`에도 추가
- **심각한 버그** (데이터 유실, 보안, 실매매 오류): CEO에게 즉시 보고 + 업데이트 기록에 🚨 표시

### 4. 팀 작업 시 기록 규칙

- **팀장**: 최종 업데이트 기록 작성 책임
- **팀원**: 자기 작업 완료 시 SendMessage로 팀장에게 "뭘 수정했는지, 버그 발견했는지" 보고
- **팀장이 팀원 보고를 취합하여 업데이트 기록 작성**
- 팀원이 기록을 안 남기면 팀장이 추적할 수 없음 → **팀원도 반드시 보고할 것**

### 5. 안 지키면 어떻게 되나

- CEO가 "뭐 바뀐 거야?" 물어볼 때 답을 못 함
- 다음 세션 Claude가 이전 작업 맥락을 모름 → 중복 작업 or 충돌
- 과거에 실제로 업데이트 기록 안 써서 빌드#224 기준으로 응답한 사건 있었음 (실제는 #238)

**요약: 코드 수정 → 업데이트 기록 → 배포. 이 순서를 빠뜨리지 마세요.**

## 팀 에이전트 (기본 규칙만 — 상세는 `docs/team-rules.md`)
- 평소 팀 없이 작업. CEO가 "팀으로 해줘" 하면 기본팀(FE+BE+QA) 구성
- 같은 파일 두 팀원 동시 수정 금지 | 서브에이전트 git 명령어 금지
- 전수검사 시 → `docs/inspection-protocol.md` 참조

## CEO 문서 (논의/기록용)
- `docs/ceo-ideas.md` — CEO 아이디어 & 기여 로그 (대화체 + 카드형). **CEO 아이디어/버그 발견 시 자동 업데이트 필수**
- `docs/monetization.md` — 수익화 논의
- `docs/defining-age.md` — "Defining Age" 패러다임 + 대화체 콘텐츠

## 환경 설정
- gh CLI 없으면 세션 시작 시 설치

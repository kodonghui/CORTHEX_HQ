# CORTHEX HQ - Claude 작업 규칙

## 🔴🔴🔴 Cloudflare 보안 로그 열려 있음 (2026-02-21 ~ 2026-03-07) 🔴🔴🔴

**현재 Cloudflare 보안이 열려 있어서 웹 로그를 전부 볼 수 있습니다!**

- **버그 수정 시**: `corthex-hq.com`에서 직접 테스트하고, Cloudflare 대시보드 또는 서버 로그(`/var/log/nginx/error.log`, `/home/ubuntu/CORTHEX_HQ/web/` 서버 로그)에서 에러를 확인할 것
- **API 에러 디버깅**: 브라우저 개발자 도구(F12 → Network 탭)에서 실패하는 요청 확인 가능
- **서버 로그 확인**: SSH로 서버 접속하여 `journalctl -u corthex -f` 또는 mini_server.py 로그 확인
- **⚠️ 이 설정은 2026-03-07에 만료됩니다. 만료일이 다가오면 대표님에게 "Cloudflare 보안 설정 2주 만료 임박" 알려줄 것!**

---

## ⚡ 세션 시작 (매 세션 반드시)
1. `git fetch origin && git status` 실행
   - 미커밋 있으면 → **작업 중지**, 대표님에게 "미커밋 있습니다. 커밋할까요?" 물어볼 것
   - 깨끗하면 → `git checkout main && git pull origin main` 즉시 실행
2. 새 브랜치에서 작업: `git checkout -b claude/작업명 origin/main` (main 직접 작업 금지)
3. CORTHEX 요청 시 먼저 코드 탐색: `docs/project-status.md` → `docs/updates/` 최근 파일 → 관련 코드 Read

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ
- 소유자: kodonghui (고동희 대표님, 법학전공 / 비개발자)
- 언어: 한국어 소통 | 도메인: `corthex-hq.com`

## 소통 규칙 (예외 없이)
- 호칭: **"고동희 대표님"** 또는 **"대표님"** (CEO님 금지)
- 대표님은 비개발자 → 전문 용어에 괄호 설명 필수. 존댓말 사용
- **구체적으로**: "최적화했습니다"(X) → "로딩 3초→1초로 줄었습니다"(O)
- **구조적으로**: 장문 시 제목/번호/표/구분선 사용. 글 덩어리 금지
- **한국어로**: 도구 권한 요청도 한국어. "grep in?"(X) → "이 폴더에서 검색할까요?"(O)
- **뻔한 질문 금지**: "커밋할까요?" "배포할까요?" → 바로 실행
- **"논의" 키워드 → 코딩 금지**: 아이디어/옵션 + 추천 제시. 대표님 결정 후 실행
- **소신 발언 필수**: B가 더 나으면 먼저 말할 것. 대표님이 최종 결정권자
- **"로컬에서 확인" 금지** → 항상 `http://corthex-hq.com`에서 확인
- 작업 완료 = 커밋 + 푸시 + 배포 + 서버 확인 + 대표님에게 빌드번호 체크리스트 보고

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

## 🔴🔴🔴 GitHub Secrets — 대표님이 이미 전부 등록함! 절대 다시 물어보지 말 것! 🔴🔴🔴
- **50+ 시크릿 전부 등록 완료**. "API 키 알려주세요" 금지. "키가 없어요" 금지.
- deploy.yml이 서버 `/home/ubuntu/corthex.env`에 자동 반영
- **등록된 API 키 목록** (전부 있음. "미설정"이라 판단하지 말 것):
  - AI: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`
  - 텔레그램: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CEO_CHAT_ID`
  - 노션: `NOTION_API_KEY`, `NOTION_DB_SECRETARY`, `NOTION_DB_OUTPUT`, `NOTION_DEFAULT_DB_ID`
  - 주식: `KOREA_INVEST_APP_KEY/SECRET/ACCOUNT` (실전+모의 둘 다)
  - 공공: `DART_API_KEY`, `ECOS_API_KEY`, `KIPRIS_API_KEY`, `LAW_API_KEY`, `SERPAPI_KEY`
  - 인스타: `INSTAGRAM_APP_ID/APP_SECRET/ACCESS_TOKEN/USER_ID`
  - 유튜브: `YOUTUBE_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN`
  - 카카오: `KAKAO_REST_API_KEY/ID/PW`
  - 네이버: `NAVER_CLIENT_ID/CLIENT_SECRET/ID/PW/BLOG_ID`
  - 다음: `DAUM_ID/PW/CAFE_ID/CAFE_BOARD_ID`
  - 이메일: `SMTP_HOST/PORT/USER/PASS`
  - 구글 OAuth: `GOOGLE_CLIENT_ID/CLIENT_SECRET/REDIRECT_URI/CALENDAR_REDIRECT_URI`
  - 기타: `REPO_ACCESS_TOKEN`, `SERVER_IP_ARM`, `SERVER_SSH_KEY_ARM`

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
- 작업 완료 시: `gh run list --workflow=deploy.yml --limit=1`로 확인 → 대표님에게 체크리스트 표 제공
- 대표님 보고 시 **"빌드#N"** 사용 (PR#N 아님!)

## 버전 번호
- 형식: `X.YY.ZZZ` | 현재: `3.01.000`
- 큰 변경 → YY 올림 + ZZZ 리셋 | 작은 변경 → ZZZ만 올림

## 디버그 URL
- 버그 시 `/api/debug/xxx` 엔드포인트 즉석 생성 → 대표님에게 URL 제공
- 보안: 계좌번호 마스킹, API 키 노출 금지

## AI 도구 자동호출 (Function Calling)
- `ai_handler.py`의 `ask_ai()`가 3개 프로바이더 도구 자동호출 지원
- 도구 스키마: `config/tools.yaml` | 에이전트별 제한: `config/agents.yaml`의 `allowed_tools`
- 도구 호출 루프 최대 5회 (무한 루프 방지)

## ⚠️ 업데이트 기록 + 버그리포트 (절대 빠뜨리지 말 것!)

### 작업 완료 4단계 (전부 안 하면 미완성)
| 순서 | 해야 할 일 | 파일 |
|------|----------|------|
| ① | 업데이트 기록 작성 | `docs/updates/YYYY-MM-DD_작업요약.md` |
| ② | 프로젝트 현황 갱신 | `docs/project-status.md` |
| ③ | 커밋 + 푸시 + 배포 | `[완료]` 태그 포함 |
| ④ | 대표님에게 보고 | 아래 보고 형식 사용 |

- **업데이트 기록 템플릿**: `docs/templates/update-template.md` 참조
- **버그 발견 시**: 수정 여부 무관하게 전부 기록. ✅/🔴 표시. 심각하면 🚨 즉시 보고
- **콘텐츠 소재**: 인스타/쇼츠에 쓸 만한 장면이 있으면 업데이트 기록에 📸 태그

### 대표님 보고 형식
```
## ✅ 작업 완료 보고
| 항목 | 내용 |
|------|------|
| **빌드** | #431 |
| **버전** | 3.02.016 |
| **브랜치** | claude/fix-something |

### 변경 내용
| # | 이전 | 이후 |
|---|------|------|
| 1 | 로딩 3초 | 로딩 1초 |

### 발견한 버그
| 버그 | 상태 |
|------|------|
| 차트 안 나옴 | ✅ 수정 |

📄 상세: `docs/updates/2026-02-21_작업요약.md`
```

### 팀 작업 시
- 팀장이 최종 기록 책임. 팀원은 SendMessage로 보고 필수
- 전수검사 시 → `docs/inspection-protocol.md` 참조

## TODO 관리
- **일일 TODO**: `docs/todo/YYYY-MM-DD.md` (매일 작업 시작 시 생성/갱신)
- **대형 프로젝트**: `docs/todo/YYYY-MM-DD_프로젝트명.TODO.md` (대문자 TODO)
- **날짜 변경 시**: 미완료 항목을 새 날짜 파일로 이관, 이전 파일에 이관 메모
- **상태 표기**: ⬜ 대기 / 🔄 진행중 / ✅ 완료 / 🔴 블로킹

## 에이전트 소울 관리
- 소울 로드 우선순위: ①`config/agents.yaml` → ②`souls/agents/*.md` (DB 오버라이드 제거됨)
- **웹에서 soul 수정 불가** — API 엔드포인트 비활성화, UI 읽기 전용
- soul 변경은 반드시 `config/agents.yaml`의 system_prompt를 직접 수정
- souls/*.md 파일은 yaml에 프롬프트가 없을 때만 폴백으로 사용

## 🔴 CORTHEX 비전 + 리트마스터 (반드시 참조!)
- **비전 상세**: `docs/corthex-vision.md` ← 반드시 읽을 것 (대표님이 왜 CORTHEX를 만들었는지)
- **리트마스터 GitHub**: https://github.com/kodonghui/leet-master
- 핵심: AI 해설 + 피드백 시스템 / 수험생 수요 분석 / 통계+크롤링+SNS 자동화

## 대표님 문서 (논의/기록용)
- `docs/ceo-ideas.md` — 대표님 아이디어 & 기여 로그. **아이디어/버그 발견 시 자동 업데이트 필수**
- `docs/monetization.md` — 수익화 논의
- `docs/defining-age.md` — "Defining Age" 패러다임

## CLAUDE.md 작성 규칙 (이 파일 수정 시)
- 정확하고 구체적이되 간략하게 (한 규칙 = 1~2줄)
- 새 규칙 추가 전 기존 규칙과 중복 검사
- 예시/템플릿은 별도 파일로 분리, 여기엔 참조 링크만
- **전체 200줄 이내** 유지 목표. 길어지면 분리

## 작업 진행 표시
- 3개 이상 작업 시 TodoWrite 도구로 진행 상황 표시 (대표님이 실시간 확인 가능)
- 작업 시작 = in_progress, 완료 = completed로 즉시 갱신. 한 번에 in_progress 1개만

## 노션 연동
- API 버전: `2022-06-28` (2025 버전 사용 금지 — DB ID가 달라짐)
- 비서실 DB: `30a56b49-78dc-8153-bac1-dee5d04d6a74`
- 에이전트 산출물 DB: `30a56b49-78dc-81ce-aaca-ef3fc90a6fba`
- 배포 로그 DB: `30e56b49-78dc-819d-b666-e50aec6a04aa`
- Integration: CORTHEX_HQ (corthex.hq 워크스페이스)

## 서버 우선 원칙
- 에이전트 프롬프트에 규칙 추가 안 해도 되는 기계적 처리(태그, 제목 정제, 형식 검증 등)는 **서버 코드(`mini_server.py`)에서 구현**
- 에이전트는 "생각하는 일"(분석, 판단, 글쓰기)에 집중. 기계적 후처리는 서버가 담당

## 환경 설정
- gh CLI 없으면 세션 시작 시 설치

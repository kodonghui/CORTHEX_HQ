# Claude 작업 상세 참조 (CLAUDE.md에서 분리)

> CLAUDE.md는 핵심 규칙만. 상세 예시/목록/API URL은 이 파일 참조.

---

## 서버 로그 API 상세

### 에이전트 활동 로그 (분석 모니터링 시 필수!)
```
GET https://corthex-hq.com/api/activity-logs?division=cio_manager&limit=50    ← CIO팀 활동 (위임/보고/QA/도구/주문)
GET https://corthex-hq.com/api/activity-logs?limit=50                         ← 전체 에이전트 활동
GET https://corthex-hq.com/api/comms/messages?division=cio_manager&limit=50   ← CIO팀 교신(위임/보고) 로그
GET https://corthex-hq.com/api/quality-reviews?limit=10                       ← QA 품질검수 결과
```

### 서버 시스템 로그 (HTTP 접속 기록, nginx)
```
GET https://corthex-hq.com/api/debug/server-logs?lines=50&service=corthex      ← 앱 로그
GET https://corthex-hq.com/api/debug/server-logs?lines=50&service=nginx-error   ← nginx 에러
GET https://corthex-hq.com/api/debug/server-logs?lines=50&service=nginx-access  ← nginx 접근
```

### 언제 뭘 확인하는가
| 상황 | API |
|------|-----|
| 분석 모니터링 | `/api/activity-logs` |
| 배포 후 | `/api/debug/server-logs` |
| 버그 디버깅 | 둘 다 |
| API 테스트 | WebFetch 직접 호출 |

### Cloudflare 설정
- WAF Skip: `/api/*` 경로 보안 우회 (2026-02-22)
- ⚠️ 만료일 2026-03-07. 임박 시 대표님에게 알릴 것

---

## 기술 설명 비유 사전

대표님에게 기술 용어 설명 시 반드시 비유를 붙일 것:

| 기술 용어 | 비유 |
|----------|------|
| WebSocket | 카카오톡처럼 실시간 양방향 통신 |
| 리팩토링 | 기능은 그대로, 코드 정리 (방 청소) |
| 브로드캐스트 | 모든 접속자에게 동시 전송 (방송) |
| API | 프로그램끼리 대화하는 약속된 창구 |
| 모듈 | 기능별로 나눈 코드 파일 (부서별 사무실) |
| SSE | 서버→클라이언트 일방향 실시간 전송 (라디오) |
| 폴백 | 1순위 실패 시 2순위로 자동 전환 (비상 출구) |
| 환경변수 | 서버에 저장된 비밀 설정값 (금고 속 열쇠) |
| 파일 트리 | 폴더/파일 계층 구조를 나무 모양으로 표현. arm_server.py 아래로 가지처럼 모듈들이 뻗어있는 그림 |
| 요청 흐름도 (플로우차트) | 버튼 클릭 → 어느 파일 → 어느 파일 → 결과까지 순서를 화살표로 그린 그림 |
| 의존성 그래프 = **연결도** | 어떤 파일이 어떤 파일을 사용하는지 연결 관계를 화살표로 그린 그림 |
| 아키텍처 다이어그램 | 시스템 전체 구조를 큰 그림으로 표현. 위 3가지를 통칭하기도 함 |

### 대표님 다이어그램 요청 키워드
- **"흐름도"** → 버튼 클릭 → 어느 파일 → 결과까지 순서도
- **"연결도"** → 파일들이 서로 어떻게 연결됐는지 관계도

---

## GitHub Secrets 등록 목록

50+ 시크릿 전부 등록 완료. 아래 목록 전부 있음:

| 분류 | 키 |
|------|-----|
| AI | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_API_KEY_2`, `GOOGLE_API_KEY_3`, `GOOGLE_API_KEY_4` |
| 텔레그램 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CEO_CHAT_ID` |
| 노션 | `NOTION_API_KEY`, `NOTION_DB_SECRETARY`, `NOTION_DB_OUTPUT`, `NOTION_DEFAULT_DB_ID` |
| 주식 | `KOREA_INVEST_APP_KEY/SECRET/ACCOUNT` (실전+모의) |
| 검색 | `SERPAPI_KEY`, `SERPER_API_KEY` |
| 공공 | `DART_API_KEY`, `ECOS_API_KEY`, `KIPRIS_API_KEY`, `LAW_API_KEY` |
| 인스타 | `INSTAGRAM_APP_ID/APP_SECRET/ACCESS_TOKEN/USER_ID` |
| 유튜브 | `YOUTUBE_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN` |
| 카카오 | `KAKAO_REST_API_KEY/ID/PW` |
| 네이버 | `NAVER_CLIENT_ID/CLIENT_SECRET/ID/PW/BLOG_ID` |
| 다음 | `DAUM_ID/PW/CAFE_ID/CAFE_BOARD_ID` |
| 이메일 | `SMTP_HOST/PORT/USER/PASS` |
| 구글 OAuth | `GOOGLE_CLIENT_ID/CLIENT_SECRET/REDIRECT_URI/CALENDAR_REDIRECT_URI` |
| Replicate | `REPLICATE_API_TOKEN` |
| 서버 | `REPO_ACCESS_TOKEN`, `SERVER_IP_ARM`, `SERVER_SSH_KEY_ARM` |

---

## 실제 존재하는 모델명 (절대 기준!)

"있을 것 같은" 모델명 지어내기 금지. 이 목록에 없으면 API 오류.

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

- ⚠️ `claude-haiku-4-6` 존재하지 않음
- ⚠️ `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` 구버전 금지

### 새 모델 추가/변경 시 10곳 체크리스트
1. `config/agents.yaml`
2. `config/models.yaml`
3. `yaml2json.py` 실행
4. arm_server.py AGENTS 리스트
5. `get_available_models()`
6. `_TG_MODELS`
7. ai_handler.py `_PRICING`
8. 기본값/폴백 모델
9. index.html 모델 표시명
10. 추론 레벨 매핑

---

## 대표님 보고 형식 (템플릿)

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

---

## 서버 배포 상세

- **스펙**: ARM Ampere A1, 4코어 24GB RAM (Oracle Cloud 춘천, Always Free)
- **접속**: `SERVER_IP_ARM` + `SERVER_SSH_KEY_ARM` (GitHub Secrets)
- **도메인**: `corthex-hq.com` (Cloudflare) | HTTPS: Let's Encrypt 자동
- **자동 배포**: claude/ 브랜치 `[완료]` push → auto-merge → deploy.yml → SSH → git fetch + reset --hard → 재시작
- **수동 배포**: GitHub → Actions → "Deploy to Oracle Cloud Server" → Run workflow
- **서버 구조**: `/home/ubuntu/CORTHEX_HQ/` (코드) | `/home/ubuntu/corthex.db` (DB) | `/home/ubuntu/corthex.env` (환경변수)
- **중요**: 서버에서 `git pull` 금지! 반드시 `git fetch + git reset --hard`
- **문제 시**: `docs/deploy-guide.md` 참조

---

## 노션 연동 상세

- API 버전: `2022-06-28` (2025 버전 금지 — DB ID 달라짐)
- Integration 이름: **CORTHEX_HQ** (KoDongHui 워크스페이스)
- API Key: GitHub Secrets `NOTION_API_KEY` (같은 토큰이 MCP에도 사용됨)

| DB | 용도 | ID |
|-----|------|-----|
| 비서실 | 비서실장→CEO 보고서만 | `30a56b49-78dc-8153-bac1-dee5d04d6a74` |
| 에이전트 산출물 | 팀장 6명 작업물 | `30a56b49-78dc-81ce-aaca-ef3fc90a6fba` |
| 아카이브 | v3 데이터·구버전 이관 | `31256b49-78dc-81c9-9ad2-e31a076d0d97` |
| 배포 로그 | CI/CD 빌드 기록 | `30e56b49-78dc-819d-b666-e50aec6a04aa` |

- 아카이브 이전 API: `POST /api/debug/notion-archive-migrate` (1회성)
- MCP 설정: `.mcp.json` (NOTION_API_KEY 환경변수 사용)

# 13. API 레지스트리 — 등록된 외부 API 목록

> CORTHEX HQ에서 연동 완료한 외부 API 목록.
> 새 프로젝트 시작 시 어떤 API가 이미 검증됐는지 참고.

---

## 🤖 AI 프로바이더

| 서비스 | 용도 | Secret 이름 | 비고 |
|--------|------|------------|------|
| Anthropic Claude | 에이전트 주력 모델 | `ANTHROPIC` | 크레딧 소진 시 폴백 |
| OpenAI GPT | 에이전트 대안 모델 | `OPENAI` | Strict 스키마 |
| Google Gemini | 비용 최적화 | `GOOGLE`, `GEMINI` | reasoning 레벨 설정 |

**폴백 패턴**: Anthropic 400 에러 → Google/OpenAI 자동 전환
→ `mark_provider_exhausted()` / `/api/debug/reset-exhausted-providers`

---

## 📈 금융 API

| 서비스 | 용도 | Secret 이름 |
|--------|------|------------|
| KIS (한국투자증권) 실거래 | 국내/해외 주식 매매 | `APP_KEY`, `APP_SECRET`, `ACCOUNT` |
| KIS 모의투자 | 페이퍼 트레이딩 | `MOCK_APP_KEY`, `MOCK_APP_SECRET`, `MOCK_ACCOUNT` |
| ECOS (한국은행) | 거시경제 데이터 | `ECOS_API_KEY` |
| DART (전자공시) | 기업 공시 정보 | `DART_API_KEY` |

**KIS 주의사항**: TR_ID 신버전 사용 (TTTC0012U). 구버전(TTTC0802U) 금지.

---

## 📰 콘텐츠/뉴스

| 서비스 | 용도 | Secret 이름 |
|--------|------|------------|
| Naver 뉴스 | 국내 뉴스 검색 | (API 없이 크롤링) |
| 네이버 블로그 | 콘텐츠 배포 | `NAVER_*` |
| 인스타그램 | SNS 발행 | `INSTAGRAM_*` |

---

## 📋 협업/저장

| 서비스 | 용도 | Secret 이름 | 비고 |
|--------|------|------------|------|
| Notion | AI 보고서 자동 저장 | `NOTION_TOKEN`, `NOTION_DATABASE_ID` | API 버전: 2022-06-28 |
| Google Calendar | 일정 관리 | `GOOGLE_CALENDAR_*` | OAuth 방식 |
| Telegram | 알림/명령 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | |

---

## 🔧 인프라

| 서비스 | 용도 | 비고 |
|--------|------|------|
| Oracle Cloud ARM | 서버 (항상 무료) | 4코어 24GB, corthex-hq.com |
| Cloudflare | CDN + WAF + Tunnel | WAF Skip 규칙 만료일 확인 |
| GitHub Actions | 자동 배포 | `[완료]` 커밋 → auto-merge → 배포 |

---

## 새 프로젝트 GitHub Secrets 체크리스트

```
# AI
ANTHROPIC=
OPENAI=
GOOGLE=
GEMINI=

# 금융 (필요 시)
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT=

# 알림
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# 저장
NOTION_TOKEN=
NOTION_DATABASE_ID=

# 서버
SERVER_HOST=
SERVER_USER=
SERVER_SSH_KEY=
```

> 상세 전체 목록: `docs/claude-reference.md` 참조 (CORTHEX 전용)

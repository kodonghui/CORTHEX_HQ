# CORTHEX HQ v1.2.0 업데이트 로그

> 날짜: 2026-02-12 | 버전: v1.2.0 | 커밋: `b7db37a`

---

## 이번 업데이트 요약

**아카이브 전용 탭 + Instagram/YouTube 자동 발행 + GPT-4 레거시 삭제 + 모델별 추론 수준 동적화 + 버그 수정 5건**

이번 업데이트는 v0.7.0 ~ v1.2.0까지 3개 버전의 변경사항을 포함합니다.

---

## 주요 변경사항

### 1. 부서별 아카이브 전용 탭 (v1.2.0)

관제실의 **5번째 탭**으로 아카이브가 추가되었습니다.

이전에는 작업 상세 화면 하단에 접혀 있어서 찾기 힘들었던 중간 보고서를, 독립 탭으로 분리하여 **부서별 필터링 + 날짜순 정렬 + 전문 보기**가 가능해졌습니다.

**기능:**
- 좌측 사이드바에서 7개 부서 중 선택 (기술/전략/법무/마케팅/투자/비서실/출판)
- 각 부서별 보고서 건수 표시
- 보고서 클릭 시 우측에서 마크다운 렌더링된 전체 내용 열람
- 새로고침 버튼으로 최신 보고서 즉시 반영

---

### 2. SNS 자동 발행 — Instagram + YouTube (v1.2.0)

마케팅처 콘텐츠 Specialist가 만든 콘텐츠를 **API 한 번으로 SNS에 자동 게시**할 수 있습니다.

#### Instagram (Graph API v21.0)
| 기능 | API | 설명 |
|------|-----|------|
| 사진 게시 | `POST /api/sns/instagram/photo` | URL 기반 이미지 업로드 |
| 릴스 게시 | `POST /api/sns/instagram/reel` | URL 기반 동영상 업로드 |

- 3단계 프로세스: 컨테이너 생성 → 상태 확인 (5초 폴링) → 발행
- 일일 게시 상한: 20건

#### YouTube (Data API v3)
| 기능 | API | 설명 |
|------|-----|------|
| 동영상 업로드 | `POST /api/sns/youtube/upload` | Resumable upload 방식 |

- OAuth2 refresh token으로 자동 토큰 갱신
- 제목, 설명, 태그, 공개 범위 설정 가능
- 일일 업로드 상한: 5건

#### 설정 방법

`config/sns.yaml`에서 각 플랫폼을 설정합니다:

```yaml
instagram:
  enabled: true
  access_token_env: "INSTAGRAM_ACCESS_TOKEN"   # Meta 개발자 콘솔에서 발급
  ig_user_id_env: "INSTAGRAM_USER_ID"          # Business Account ID

youtube:
  enabled: true
  client_id_env: "YOUTUBE_CLIENT_ID"           # Google Cloud Console
  client_secret_env: "YOUTUBE_CLIENT_SECRET"
  refresh_token_env: "YOUTUBE_REFRESH_TOKEN"
```

환경변수에 실제 키 값을 설정하면 관제실 사이드바에 "연결됨"으로 표시됩니다.

---

### 3. GPT-4.x 레거시 모델 삭제 (v1.2.0)

GPT-5 시리즈가 추가되면서 불필요해진 GPT-4 계열 모델을 완전히 제거했습니다.

| 삭제된 모델 | 대체 모델 |
|-------------|-----------|
| gpt-4o | gpt-5 |
| gpt-4o-mini | gpt-5-mini |
| gpt-4.1-nano | gpt-5-mini |

사무실 탭 모델 드롭다운에 **GPT-5 시리즈 4종 + Claude 3종**만 표시됩니다.

---

### 4. 모델별 추론 수준 동적 UI (v1.2.0)

각 모델이 지원하는 추론 수준이 다르므로, 모델 변경 시 드롭다운 옵션이 자동으로 갱신됩니다.

| 모델 | 지원 추론 수준 |
|------|---------------|
| gpt-5-mini | 낮음, 중간, 높음 |
| gpt-5 | 낮음, 중간, 높음 |
| gpt-5-2 | 낮음, 중간, 높음 |
| gpt-5-2-pro | 낮음, 중간, 높음 |
| claude-opus-4-6 | 낮음, 중간, 높음 |
| claude-sonnet-4-5 | 낮음, 중간, 높음 |
| claude-haiku-4-5 | **(비활성화)** — 비용 효율 모델이라 추론 off |

Haiku 선택 시 추론 드롭다운이 회색 처리되고, 모델 변경 시 현재 설정이 새 모델에서 미지원이면 자동으로 "기본"으로 리셋됩니다.

---

### 5. 버그 수정 3건 (v1.2.0)

#### 채팅 메시지 표시 버그
관제실에서 메시지를 보내면 내 메시지가 채팅창에 표시되지 않던 버그 수정.
- 원인: Alpine.js가 `push()` 배열 변경을 감지 못하는 경우 발생
- 수정: 새 배열 참조 할당 (`this.messages = [...this.messages, msg]`)

#### Batch API async for 에러
Anthropic Batch API 결과 수집 시 `async for` 에러 발생.
- 원인: `messages.batches.results()`가 코루틴을 반환하는데 `await` 없이 사용
- 수정: `async for result in await ...results(batch.id):`

#### 텔레그램 봇 /start 무응답
`/start` 명령 시 아무 응답이 없던 문제.
- 수정: 에러 로깅 강화 + chat_id 자동 안내 메시지 추가

---

### 6. 출판·기록 본부 신설 (v0.7.0)

새로운 부서가 추가되었습니다:

| 에이전트 | 역할 |
|----------|------|
| CPO (출판·기록처장) | 출판·기록 총괄 |
| Chronicle Specialist | 연대기/이력 기록 |
| Editor Specialist | 문서 편집/교정 |
| Archive Specialist | 문서 보관/분류/검색 |

에이전트 총원: 25명 → **29명**

---

### 7. Batch API 50% 할인 모드 (v1.1.0)

입력창 옆에 "실시간" / "절약 (-50%)" 선택기가 추가되었습니다.

- OpenAI/Anthropic 모두 Batch API 사용 시 **토큰 비용 50% 할인**
- 0.5초 디바운스로 동시 요청을 모아서 일괄 제출
- 결과는 수분 후 도착 (비급한 작업에 적합)

---

### 8. 텔레그램 봇 — 모바일 접근 (v1.1.0)

외출 중에도 스마트폰 텔레그램으로 CEO 명령을 내릴 수 있습니다.

- Long polling 방식 (웹훅 불필요)
- CEO 전용 인증 (`TELEGRAM_ALLOWED_CHAT_ID`)
- 배치 모드 지원: `/batch 삼성전자 분석`
- 깊이 설정 가능

---

### 9. 비서실장 중복 보고 버그 수정 (v1.1.0)

비서실장이 같은 보고서를 2번 보내던 버그 수정:
1. WebSocket 좀비 연결 정리 (재연결 시 기존 연결 해제)
2. 단일 결과 바이패스 (부서 1곳만 응답 시 종합 보고서 생략)

---

## 현재 사용 가능한 모델

| 모델 | 티어 | 입력 (/1M) | 출력 (/1M) |
|------|------|-----------|-----------|
| gpt-5-mini | worker | $0.25 | $2.00 |
| gpt-5 | manager | $1.25 | $10.00 |
| gpt-5-2 | manager | $1.75 | $14.00 |
| gpt-5-2-pro | executive | $21.00 | $168.00 |
| claude-opus-4-6 | executive | $5.00 | $25.00 |
| claude-sonnet-4-5 | manager | $3.00 | $15.00 |
| claude-haiku-4-5 | specialist | $0.80 | $4.00 |

---

## 전체 API 엔드포인트 (신규)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/archive` | 부서별 아카이브 목록 |
| GET | `/api/archive/{div}/{file}` | 보고서 본문 |
| GET | `/api/sns/status` | SNS 연동 상태 |
| POST | `/api/sns/instagram/photo` | Instagram 사진 게시 |
| POST | `/api/sns/instagram/reel` | Instagram 릴스 게시 |
| POST | `/api/sns/youtube/upload` | YouTube 동영상 업로드 |
| PUT | `/api/agents/{id}/reasoning` | 추론 깊이 변경 |
| POST | `/api/command` | REST 명령 (외부 연동용) |

---

## 수정된 파일 목록

### v1.2.0 (10개 파일, +651줄 / -47줄)
| 파일 | 작업 | 내용 |
|------|------|------|
| `config/models.yaml` | 수정 | GPT-4.x 삭제, reasoning_levels 추가 |
| `config/sns.yaml` | **신규** | Instagram/YouTube 연동 설정 |
| `config/tools.yaml` | 수정 | sns_publish 도구 등록 |
| `config/agents.yaml` | 수정 | content_specialist SNS 도구 추가 |
| `src/integrations/sns_publisher.py` | **신규** | Instagram + YouTube API (311줄) |
| `src/integrations/telegram_bot.py` | 수정 | /start 에러 로깅 + chat_id 안내 |
| `src/llm/batch_collector.py` | 수정 | await 추가 |
| `src/llm/openai_provider.py` | 수정 | GPT-4.x 가격표 삭제 |
| `web/app.py` | 수정 | 아카이브 + SNS API |
| `web/templates/index.html` | 수정 | 아카이브 탭 + 동적 추론 + 채팅 수정 |

### v1.1.0 (14개 파일, +1,355줄 / -31줄)
| 파일 | 작업 | 내용 |
|------|------|------|
| `config/models.yaml` | 수정 | GPT-5 + Claude 4.6 추가 |
| `src/core/agent.py` | 수정 | 단일 결과 바이패스 |
| `src/core/message.py` | 수정 | reasoning_effort 필드 |
| `src/integrations/telegram_bot.py` | **신규** | 텔레그램 봇 (142줄) |
| `src/llm/batch_collector.py` | **신규** | Batch API (276줄) |
| `src/llm/anthropic_provider.py` | 수정 | Extended thinking + Batch |
| `src/llm/openai_provider.py` | 수정 | reasoning_effort + Batch |
| `src/llm/router.py` | 수정 | 배치 모드 분기 |
| `web/app.py` | 수정 | 아카이브 + 추론 + REST API |
| `web/templates/index.html` | 수정 | 배치 모드 + 추론 + 아카이브 뷰 |

### v0.7.0 (2개 파일)
| 파일 | 내용 |
|------|------|
| `config/agents.yaml` | CPO + 전문가 3명 추가 |
| `web/templates/index.html` | 출판·기록 본부 섹션 |

---

## 다음 단계

- [ ] Instagram API 키 발급 및 환경변수 설정
- [ ] YouTube OAuth2 자격증명 발급 및 환경변수 설정
- [ ] SNS 자동 발행 실제 테스트
- [ ] 텔레그램 봇 실사용 테스트

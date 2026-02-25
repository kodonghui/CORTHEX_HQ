# TODO: 다음 작업 프롬프트 모음

> **사용법**: 각 작업의 프롬프트를 **다른 Claude Code 세션**에 그대로 복사해서 붙여넣으면 됩니다.
> 한 세션에서 하나씩 처리하세요.

---

## 작업 목록

| # | 작업 | 상태 | 프롬프트 위치 |
|---|------|------|-------------|
| 1 | 29명 에이전트 소울(성격) 업그레이드 | ✅ 프롬프트 완료 | `docs/PROMPT-에이전트-소울-업그레이드.md` |
| 2 | 노션 보고 시스템 구현 | ⬜ 미완료 | [아래 2번](#2-노션-보고-시스템-구현) |
| 3 | SNS 실제 발행 연동 | ⬜ 미완료 | [아래 3번](#3-sns-실제-발행-연동) |
| 4 | 도메인 연결 (corthex.com) | ⬜ 미완료 | [아래 4번](#4-도메인-연결) |
| 5 | HTTPS 설정 (SSL 인증서) | ⬜ 미완료 | [아래 5번](#5-https-설정) |
| 6 | 서버 업그레이드 (ARM 4코어 24GB) | ⬜ 미완료 | [아래 6번](#6-서버-업그레이드) |

---

---

## 2. 노션 보고 시스템 구현

> 아래 프롬프트를 새 Claude Code 세션에 그대로 붙여넣으세요.

### 프롬프트 시작 ▼

```
## 작업: 노션 보고 시스템 구현

### 배경
CORTHEX HQ는 29명의 AI 에이전트로 구성된 가상 회사다.
에이전트가 작업을 완료하면, 그 결과를 **노션(Notion) 데이터베이스에 자동으로 보고**하는 시스템을 만들어야 한다.
현재는 노션 API 키가 서버에 등록되어 있지만, 실제로 노션과 통신하는 코드가 없다.

### 현재 상태
- ✅ NOTION_API_KEY가 서버 환경변수에 등록됨 (GitHub Secrets → deploy.yml → /home/ubuntu/corthex.env)
- ✅ config/tools.yaml에 `notion_api` 도구가 등록됨
- ✅ 각 에이전트의 소울 파일(souls/agents/*.md)에 노션 보고 의무 섹션이 있음
- ❌ 실제 노션 API를 호출하는 코드가 없음 (구현해야 할 것)

### 노션 DB 정보
- data_source_id: `ee0527e4-697b-4cb6-8df0-6dca3f59ad4e`
- 에이전트 산출물 DB에 보고서를 등록하는 구조

### 보고서 속성값 구조
| 속성 | 타입 | 설명 |
|------|------|------|
| Name | title | 보고서 제목 (예: "삼성전자 종목분석 보고서") |
| Agent | select | 에이전트 이름 (예: "CTO", "비서실장") |
| Division | select | 소속 부서 (예: "LEET MASTER", "투자분석") |
| Type | select | 문서 유형 (보고서/분석/회의록/기타) |
| Status | select | 상태 (완료/진행중/검토중) |
| date | date | 작성일 (KST 기준, YYYY-MM-DD) |

### 구현해야 할 것

1. **`web/notion_client.py` 파일 새로 만들기**
   - Notion API (https://api.notion.com/v1/) 를 호출하는 클라이언트
   - 페이지 생성: `create_page(db_id, properties, content)` 함수
   - DB 조회: `query_database(db_id, filter)` 함수
   - 페이지 업데이트: `update_page(page_id, properties, content)` 함수
   - httpx 또는 aiohttp 사용 (비동기)
   - Notion API 버전: 2022-06-28

2. **`web/arm_server.py`에 노션 API 엔드포인트 추가**
   - `POST /api/notion/report` — 에이전트가 보고서를 노션에 제출
     - body: `{ agent_id, title, content, type, status }`
     - 에이전트별 Agent/Division 값은 소울 파일에 정의되어 있음
   - `GET /api/notion/reports` — 최근 보고서 목록 조회
   - `GET /api/notion/reports/{page_id}` — 보고서 상세 조회

3. **에이전트 AI 응답 시 자동 보고 연동**
   - `_process_ai_command()` 함수에서 AI 응답이 돌아오면,
     결과를 자동으로 노션 DB에 보고하는 옵션 추가
   - 모든 응답을 보고하면 비용이 크니, 특정 조건에서만:
     - 길이가 500자 이상인 응답
     - 또는 에이전트가 명시적으로 보고 요청한 경우

4. **대시보드(index.html)에 노션 연동 상태 표시**
   - 설정 탭에 "노션 연동 상태" 카드 추가
   - 최근 보고서 5건 목록 표시

### 참고 파일
- `souls/agents/chief_of_staff.md` — 비서실장의 노션 보고 규칙 예시 (다른 에이전트도 동일 구조)
- `docs/TODO-에이전트-설정.md` — 에이전트별 보고 대상 노션 DB 매핑표
- `config/tools.yaml` — notion_api 도구 설정 (161번 줄)
- `web/arm_server.py` — 메인 서버 (노션 키 존재 확인: os.getenv("NOTION_API_KEY"))
- `web/ai_handler.py` — AI 호출 모듈

### Notion API 사용법 요약
- Base URL: https://api.notion.com/v1/
- 인증: `Authorization: Bearer {NOTION_API_KEY}`, `Notion-Version: 2022-06-28`
- 페이지 생성: POST /pages
- DB 쿼리: POST /databases/{db_id}/query
- 페이지 업데이트: PATCH /pages/{page_id}

### Git 규칙
- CLAUDE.md 반드시 읽을 것
- 브랜치: `claude/`로 시작
- 마지막 커밋에 `[완료]` 포함
- docs/updates/ 에 작업 기록 파일 생성
- docs/project-status.md 업데이트
```

### 프롬프트 끝 ▲

---

---

## 3. SNS 실제 발행 연동

> 아래 프롬프트를 새 Claude Code 세션에 그대로 붙여넣으세요.

### 프롬프트 시작 ▼

```
## 작업: SNS 실제 발행 연동 (인스타그램, 유튜브 등)

### 배경
CORTHEX HQ에는 SNS 매니저 시스템이 이미 구현되어 있다:
- ✅ 콘텐츠 Specialist가 글을 작성해서 승인 큐에 등록 (action=submit)
- ✅ CEO가 텔레그램으로 승인/거절 알림을 받음
- ✅ 승인 후 CMO가 실제 퍼블리싱 실행 (action=publish)
- ❌ 하지만 실제로 인스타그램/유튜브에 글이 올라가지는 않음 (API 키 미등록, OAuth 미설정)

### 현재 SNS 관련 엔드포인트 (arm_server.py)
| 경로 | 메서드 | 설명 |
|------|--------|------|
| /api/sns/status | GET | SNS 상태 조회 |
| /api/sns/oauth/status | GET | OAuth 연동 상태 |
| /api/sns/auth/{platform} | GET | 플랫폼별 인증 URL |
| /api/sns/instagram/photo | POST | 인스타그램 사진 게시 |
| /api/sns/instagram/reel | POST | 인스타그램 릴스 게시 |
| /api/sns/youtube/upload | POST | 유튜브 영상 업로드 |
| /api/sns/queue | GET | SNS 승인 대기 큐 조회 |
| /api/sns/approve/{item_id} | POST | 게시물 승인 |
| /api/sns/reject/{item_id} | POST | 게시물 거절 |

### 해야 할 일

1. **Instagram Graph API 연동**
   - Meta Developer 앱 생성 필요 (CEO가 해야 할 수 있음)
   - 필요한 환경변수: INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID
   - 사진/릴스 게시 API 연결
   - /api/sns/instagram/photo, /api/sns/instagram/reel 엔드포인트를 실제 동작하게

2. **YouTube Data API v3 연동**
   - Google Cloud Console에서 API 키/OAuth 설정 필요
   - 필요한 환경변수: YOUTUBE_API_KEY, YOUTUBE_OAUTH_TOKEN
   - 영상 업로드, 메타데이터 설정
   - /api/sns/youtube/upload 엔드포인트를 실제 동작하게

3. **Tistory 자동 발행**
   - 이미 tools.yaml에 "Selenium 기반, KAKAO_ID/PW 필요"로 되어 있음
   - KAKAO_ID, KAKAO_PW, TISTORY_BLOG_NAME 환경변수 필요
   - Selenium 드라이버가 서버에 설치되어 있어야 함

4. **대시보드 연동**
   - 설정 탭에 각 플랫폼별 연동 상태 표시 (연결됨/미연결)
   - OAuth 인증 버튼 (인스타, 유튜브)

5. **deploy.yml 업데이트**
   - 새로운 API 키들을 GitHub Secrets에서 서버 환경변수로 전달

### 주의
- CEO에게 "어떤 SNS 플랫폼부터 연동할지" 먼저 물어볼 것
- OAuth 설정은 CEO가 직접 해야 하는 부분이 있을 수 있음 (Meta Developer 앱, Google Console 등)
- 이 작업은 CEO와의 대화가 필요한 부분이 많음

### 참고 파일
- web/arm_server.py — SNS 엔드포인트 (751~803줄)
- config/tools.yaml — sns_manager 도구 설정 (51번 줄)
- config/agents.yaml — CMO/콘텐츠 Specialist의 SNS 관련 설정

### Git 규칙
- CLAUDE.md 반드시 읽을 것
- 브랜치: `claude/`로 시작
- 마지막 커밋에 `[완료]` 포함
```

### 프롬프트 끝 ▲

---

---

## 4. 도메인 연결

> 아래 프롬프트를 새 Claude Code 세션에 그대로 붙여넣으세요.

### 프롬프트 시작 ▼

```
## 작업: corthex.com 도메인을 서버에 연결

### 배경
CORTHEX HQ 웹 대시보드가 Oracle Cloud 서버(168.107.28.100)에서 운영되고 있다.
현재는 IP 주소로만 접속 가능하다: http://168.107.28.100
이것을 도메인(corthex.com)으로 접속할 수 있게 연결해야 한다.

### 서버 정보
- 서버 IP: 168.107.28.100
- 클라우드: Oracle Cloud (춘천 리전, 무료 인스턴스)
- OS: Ubuntu
- 웹 서버: nginx (80포트에서 index.html 서빙)
- 미니 서버: FastAPI (8000포트, systemd 서비스 "corthex")
- SSH 접속: ubuntu@168.107.28.100 (SSH 키는 GitHub Secrets에 저장)

### 해야 할 일

1. **DNS 설정 안내 문서 작성**
   - CEO가 도메인 등록 업체(가비아, 후이즈 등)에서 DNS를 설정해야 함
   - A 레코드: corthex.com → 168.107.28.100
   - A 레코드: www.corthex.com → 168.107.28.100
   - CEO에게 스크린샷 포함한 단계별 가이드 작성

2. **nginx 설정 업데이트**
   - 현재 nginx는 IP로 접속 받고 있음
   - server_name에 corthex.com, www.corthex.com 추가
   - deploy.yml에서 nginx 설정을 자동으로 업데이트하도록 수정

3. **Oracle Cloud 방화벽 확인**
   - Security List에 80, 443 포트가 열려있는지 확인
   - iptables도 확인

### 주의
- 도메인 구매/DNS 설정은 CEO가 직접 해야 하는 부분
- CEO에게 "도메인이 어디서 구매했는지" 물어볼 것
- DNS 전파에 최대 48시간 걸릴 수 있음
- 이 작업은 CEO와 대화하면서 진행해야 함

### 참고 파일
- .github/workflows/deploy.yml — 배포 워크플로우 (nginx 설정 관련 부분 포함)

### Git 규칙
- CLAUDE.md 반드시 읽을 것
- 브랜치: `claude/`로 시작
- 마지막 커밋에 `[완료]` 포함
```

### 프롬프트 끝 ▲

---

---

## 5. HTTPS 설정

> 아래 프롬프트를 새 Claude Code 세션에 그대로 붙여넣으세요.
> ⚠️ **4번(도메인 연결)이 완료된 후에 진행하세요!** 도메인 없이는 SSL 인증서를 발급받을 수 없습니다.

### 프롬프트 시작 ▼

```
## 작업: HTTPS 설정 (Let's Encrypt SSL 인증서)

### 배경
CORTHEX HQ 웹 대시보드에 HTTPS(보안 연결)를 설정해야 한다.
현재는 http://corthex.com (도메인 연결 완료 상태 전제)으로 접속되는데,
이것을 https://corthex.com 으로 자동 리다이렉트되게 만들어야 한다.

### 전제 조건
- ✅ 도메인(corthex.com)이 서버(168.107.28.100)에 연결되어 있어야 함
- ✅ DNS A 레코드가 설정되어 있어야 함
- ✅ 80포트, 443포트 방화벽 열려있어야 함

### 서버 정보
- 서버 IP: 168.107.28.100
- 클라우드: Oracle Cloud (춘천 리전, 무료 인스턴스)
- OS: Ubuntu
- 웹 서버: nginx
- SSH 접속: ubuntu@168.107.28.100

### 해야 할 일

1. **Certbot 설치 + SSL 인증서 발급**
   - deploy.yml에 certbot 설치 단계 추가 (첫 배포 시)
   - `sudo certbot --nginx -d corthex.com -d www.corthex.com --non-interactive --agree-tos --email CEO이메일`
   - 인증서 자동 갱신 크론 확인: `sudo certbot renew --dry-run`

2. **nginx 설정 업데이트**
   - 80 → 443 자동 리다이렉트
   - SSL 인증서 경로 설정
   - HSTS 헤더 추가

3. **deploy.yml 업데이트**
   - 첫 배포: certbot 설치 + 인증서 발급
   - 이후 배포: 인증서가 이미 있으면 스킵
   - nginx 설정에 SSL 부분 추가

4. **Oracle Cloud 방화벽**
   - Security List에 443 포트 (HTTPS) 열려있는지 확인
   - iptables에도 443 허용

### 주의
- Let's Encrypt 인증서는 90일마다 갱신 필요 (certbot이 자동으로 해줌)
- 도메인이 서버를 가리키고 있어야 인증서 발급 가능
- CEO에게 이메일 주소를 물어봐야 함 (certbot 등록용)

### 참고 파일
- .github/workflows/deploy.yml — 배포 워크플로우

### Git 규칙
- CLAUDE.md 반드시 읽을 것
- 브랜치: `claude/`로 시작
- 마지막 커밋에 `[완료]` 포함
```

### 프롬프트 끝 ▲

---

---

## 6. 서버 업그레이드

> 아래 프롬프트를 새 Claude Code 세션에 그대로 붙여넣으세요.
> ⚠️ **이 작업은 대부분 CEO가 Oracle Cloud 콘솔에서 직접 해야 합니다.** 가이드 문서를 작성하는 게 핵심입니다.

### 프롬프트 시작 ▼

```
## 작업: Oracle Cloud 서버 업그레이드 가이드 작성

### 배경
현재 CORTHEX HQ 서버는 Oracle Cloud의 무료 인스턴스를 사용하고 있다.
AI 에이전트 29명이 동시에 작동하려면 더 강력한 서버가 필요하다.
Oracle Cloud는 **ARM 기반 Ampere A1 인스턴스를 무료로 제공**한다 (4 OCPU, 24GB RAM).

### 현재 서버 사양 (추정)
- AMD 또는 ARM 1 OCPU
- 1GB RAM (무료 인스턴스 기본)
- Ubuntu

### 업그레이드 목표
- ARM Ampere A1: 4 OCPU, 24GB RAM (Oracle Cloud 무료 제공)
- Always Free 한도 내에서 최대 사양

### 해야 할 일

1. **CEO용 가이드 문서 작성** (docs/GUIDE-서버-업그레이드.md)
   - Oracle Cloud 콘솔 접속 방법
   - 현재 인스턴스 백업 방법
   - 새 ARM 인스턴스 생성 절차 (스크린샷 설명)
   - 보안 그룹/네트워크 설정
   - 고정 IP(Reserved Public IP) 할당
   - SSH 키 설정

2. **서버 초기 설정 스크립트 작성** (scripts/server-setup.sh)
   - Python 3.11+ 설치
   - pip 패키지 설치 (anthropic, httpx, fastapi, uvicorn 등)
   - nginx 설치 + 기본 설정
   - systemd 서비스 파일(corthex.service) 설정
   - 방화벽 설정 (80, 443, 8000 포트)
   - git 설정 + 저장소 클론

3. **deploy.yml 업데이트** (필요한 경우)
   - 새 서버 IP로 GitHub Secrets 업데이트 안내
   - ARM 아키텍처 호환성 확인

4. **마이그레이션 체크리스트**
   - SQLite DB 백업 + 새 서버로 이동
   - 환경변수(.env) 이동
   - SSL 인증서 이동 (있으면)
   - nginx 설정 이동
   - systemd 서비스 파일 이동
   - DNS 변경 (새 IP로)

### 주의
- 이 작업은 가이드 문서 작성이 핵심. 실제 서버 작업은 CEO가 해야 함
- Oracle Cloud 콘솔은 코드로 접근할 수 없음
- 기존 서버의 데이터(SQLite DB, 환경변수)를 반드시 백업해야 함
- 서버 IP가 바뀌면 GitHub Secrets의 SERVER_IP를 업데이트해야 함
- ARM 아키텍처에서 Python 패키지 호환성 확인 필요

### 참고 파일
- .github/workflows/deploy.yml — 현재 배포 워크플로우
- web/ — 서버에 복사되는 파일들

### Git 규칙
- CLAUDE.md 반드시 읽을 것
- 브랜치: `claude/`로 시작
- 마지막 커밋에 `[완료]` 포함
```

### 프롬프트 끝 ▲

---

---

## 작업 순서 권장

```
1. 에이전트 소울 업그레이드 ← 별도 프롬프트 파일 있음
   ↓ (독립 — 언제든 가능)
2. 노션 보고 시스템 ← 소울 완료 후 하면 좋음 (소울에 노션 보고 규칙이 있으니)
   ↓ (독립 — 언제든 가능)
3. SNS 실제 발행 ← CEO와 대화 필요 (OAuth 설정 등)
   ↓ (순서 있음 — 아래는 4→5→6 순서대로)
4. 도메인 연결 ← CEO가 DNS 설정 필요
   ↓ (의존)
5. HTTPS 설정 ← 도메인 연결 후에만 가능
   ↓ (독립)
6. 서버 업그레이드 ← 가이드 작성은 언제든, 실제 작업은 CEO가
```

1, 2, 3, 6은 **순서 상관없이 동시에 진행 가능**.
4 → 5는 **반드시 순서대로** (도메인 먼저, HTTPS 나중).

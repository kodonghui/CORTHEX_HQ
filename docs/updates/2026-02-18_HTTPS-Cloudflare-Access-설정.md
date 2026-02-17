# HTTPS 자물쇠 설정 + Cloudflare Access 로그인 보안

## 버전
1.00.002

## 작업 날짜
2026-02-18

## 작업 브랜치
claude/agent-collab-overhaul

---

## 변경 사항 요약

### 1. HTTPS 자물쇠 설정 (Let's Encrypt + Certbot)

**무엇인가?**
- HTTPS = 주소창에 자물쇠 달린 안전한 연결. 없으면 브라우저가 "안전하지 않음" 경고 표시
- Let's Encrypt = 전 세계 무료 HTTPS 인증서 발급 기관
- Certbot = Let's Encrypt 인증서를 자동으로 발급·갱신해주는 도구

**어떻게 했나?**
- `deploy.yml`(자동 배포 파일)에 Certbot 자동 설치 단계 추가
- 배포할 때마다 인증서가 없으면 자동 발급, 있으면 자동 갱신 확인
- `CERTBOT_EMAIL` 환경변수를 GitHub Secrets에 추가해서 이메일로 인증서 등록

**결과:**
- `https://corthex-hq.com` 주소로 자물쇠 달린 안전한 접속 가능
- 인증서는 90일짜리, Certbot이 자동으로 갱신해줌 (수동 작업 불필요)

---

### 2. Cloudflare Access 로그인 보안

**무엇인가?**
- Cloudflare Access = 사이트 앞에 로그인 문을 세우는 보안 서비스
- 허용된 이메일로만 접속 가능 (그 외는 차단)
- 이메일 OTP(일회용 번호) 방식 — 비밀번호 없이 이메일로 받은 번호로 로그인

**어떻게 설정했나?**
1. Cloudflare Zero Trust 접속
2. "CORTHEX HQ" 애플리케이션 생성 (보호할 도메인: `corthex-hq.com`)
3. "CEO Only" 정책 생성:
   - 허용 이메일: `corthex.hq@gmail.com`
   - 그 외 모든 접속: 차단
4. 애플리케이션에 CEO Only 정책 연결

**결과:**
- `https://corthex-hq.com` 접속 시 Cloudflare 로그인 화면이 먼저 뜸
- `corthex.hq@gmail.com`으로 이메일 인증 후 접속 가능
- 다른 이메일로는 절대 접속 불가

---

### 트러블슈팅 (겪었던 문제들)

| 문제 | 원인 | 해결 |
|------|------|------|
| ERR_QUIC_PROTOCOL_ERROR | Cloudflare 주황 구름 전환 후 HTTPS 시도, 서버는 HTTP만 지원 | Cloudflare SSL 모드를 Flexible로 변경 |
| ERR_TOO_MANY_REDIRECTS | nginx HTTP→HTTPS 리다이렉트 + Cloudflare Flexible 충돌 → 무한 루프 | Cloudflare SSL 모드를 Full로 변경 |
| 로그인 화면이 안 뜸 | 크롬에 Cloudflare 세션 쿠키가 남아있어서 자동 통과 | 엣지 브라우저로 테스트 → 정상 확인 |

---

### 수정된 파일

| 파일 | 무슨 파일인가? | 뭘 바꿨나? |
|------|-------------|-----------|
| `.github/workflows/deploy.yml` (자동 배포 파일) | 서버에 코드를 자동 올려주는 파일 | Certbot 자동 설치 + HTTPS 인증서 발급 단계 추가 |

---

## 현재 상태

- ✅ `https://corthex-hq.com` 자물쇠 달린 주소로 접속 가능
- ✅ Cloudflare Access 로그인 보안 적용 완료
- ✅ `corthex.hq@gmail.com` 이메일 OTP로만 로그인 가능
- ✅ SSL Full 모드 (Cloudflare ↔ 서버 구간도 암호화)

---

## 다음에 할 일

1. **API 키 발급 및 서버 등록** (주요 작업)
   - GitHub Secrets에 등록 필요한 키들:
     - DART_API_KEY (금감원 기업재무)
     - ECOS_API_KEY (한국은행 경제통계)
     - PUBLIC_DATA_API_KEY (공공데이터포털)
     - KIPRIS_API_KEY (특허/상표)
     - LAW_API_KEY (국가법령정보)
     - SERPAPI_KEY (실시간 웹 검색)
     - SMTP_PASS (Gmail 앱 비밀번호)
     - KAKAO_REST_API_KEY (카카오 검색)
     - NAVER_CLIENT_ID / NAVER_CLIENT_SECRET
     - INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET
     - LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET
     - GITHUB_TOKEN

2. **각 SNS 개발자 콘솔에서 Redirect URI 업데이트**
   - Google Cloud Console, Meta(Instagram), LinkedIn, 네이버 개발자센터
   - 기존 localhost → `https://corthex-hq.com` (또는 `http://corthex-hq.com`)으로 변경

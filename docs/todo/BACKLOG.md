# CORTHEX HQ — BACKLOG

> **규칙**: 미완료 항목은 전부 여기만. 날짜 파일에 ⬜ 절대 금지.
> **수시 업데이트**: 완료되면 즉시 ✅ 표시 or 삭제. 새 항목 발견 시 즉시 추가.
> 🔴 **매 배포 시 반드시 갱신!** — 배포하고 BACKLOG 안 건드리면 미완성!
> 마지막 업데이트: 2026-02-28 (인스타 발행 성공 + SNS 콘텐츠 파이프라인 계획)

---

## 🟠 재확인 필요 (코드 완료, 실제 검증 안 됨)

- ⬜ **R-2: 작전일지 제목만 표시** — `_extract_title_summary()` 구현 완료. 실제 화면에서 제목 보이는지 확인 필요
- ⬜ **노션 실제 저장 검증** — 대표님이 금융분석팀장 분석 실행 후 노션 양쪽 DB(비서/출력) 확인
- ⬜ **Soul Gym 6팀장 Dry Run** — 서버에서 수동 실행 → soul_gym_rounds 테이블에 6팀장 전부 채워지는지 확인
- ⬜ **즉시분석 재테스트** — 스트리밍 수정(#598) + thinking adaptive→enabled 이후 전체 흐름 미검증

---

## 🔴 긴급 (데드라인 있음)

- ✅ ~~**나노바나나 v2 교체**~~ — `gemini-3-pro-image-preview` → `gemini-3.1-flash-image-preview` 교체 완료 (Flash 티어, Pro 대비 ~50% 비용 절감)

---

## 🟡 버그 (발견됐지만 미수정)

- ✅ ~~**한미반도체(042700) KIS 주문 실패**~~ — `EXCG_ID_DVSN_CD` "" → "KRX" 수정 (빌드 #655 예정)

---

## 🟡 코드 개선

- ✅ ~~**4-3: arm_server.py 리팩토링 P9**~~ — P9 완료 (1,843→1,075줄, 9개 모듈 10,562줄 분리, 91%). 리팩토링 종료
- ✅ ~~**도구 합병: pricing**~~ — pricing_sensitivity 삭제, Gabor-Granger+수익최적화를 pricing_optimizer에 이식 (빌드 #655 예정)
- ✅ ~~**도구 합병: 고객분석**~~ — customer_cohort_analyzer 삭제, RFM+CAC 회수를 customer_ltv_model에 이식 (빌드 #655 예정)

---

## 🟢 대표님이 직접 해야 하는 것

- ✅ ~~**Instagram Meta 앱 설정**~~ — 토큰 발급 + GitHub Secrets 등록 + 코드 연동 완료
- ✅ ~~**Instagram 실제 발행 테스트**~~ — 대표님이 직접 발행 성공 확인 (2026-02-28)

---

## 🟡 SNS 자동 발행

- ✅ ~~**티스토리 자동 발행**~~ — 공개 발행 성공! ActionChains label 클릭으로 React 라디오 전환. `tistory_publisher.py` 전면 수정
- ✅ ~~**다음카페(서로연) 자동 발행**~~ — 발행 성공! `logins.daum.net` → 카카오 OAuth → `united_write` → TinyMCE. `daum_cafe_publisher.py` 전면 수정
- ⬜ **SNS 콘텐츠 파이프라인 구축** — 마케팅팀장이 콘텐츠(글/이미지/카드뉴스/동영상) 생성 → 대표님 텔레그램 승인 → 자동 발행. 백엔드(sns_manager.py 승인 큐 + notifier.py 텔레그램 알림)는 이미 구현됨. 남은 작업: ① end-to-end 연결 테스트 ② 카드뉴스 생성기 ③ 웹 UI 승인 화면(선택)
  - 이미 있는 도구: gemini_image_generator(이미지), gemini_video_generator(동영상), lipsync_video_generator(립싱크), sns_manager(승인큐), notifier(텔레그램 승인 버튼)
  - 빠진 것: 카드뉴스 생성기(인스타용 텍스트+디자인 조합), 마케팅팀장→승인큐→발행 end-to-end 흐름 검증
- ⬜ **페이스북 자동 발행 검토** — Graph API로 페이지/그룹 게시 가능 여부 조사. Meta 개발자 계정 필요. 티스토리/다음카페 완료 후 착수
- ⬜ **X(트위터) 자동 발행 검토** — X API v2 게시 가능 여부 조사. 유료 플랜(Basic $100/월) 필요할 수 있음. 티스토리/다음카페 완료 후 착수
- 🔴 **네이버 블로그 자동 발행 — 보류** (2026-02-28 판정)
  - 시도: Selenium + ActionChains 글자별 타이핑 / JS injection + 이벤트 디스패치 / undetected-chromedriver / chromedriver cdc_ 패치 / 쿠키 기반 로그인
  - 결과: 전부 실패. 네이버가 헤드리스 브라우저 자체를 CAPTCHA로 차단. 쿠키 로드 후 naver.com은 로그인되나 blog.naver.com 글쓰기 접속 시 재로그인 요구 (세션 불일치)
  - 원인: 네이버 2025년 이후 봇 탐지 대폭 강화. snap chromedriver(ARM)는 패치 불가(GLIBC 호환 문제)
  - 재도전 조건: ① 대표님 PC(데스크톱)에서 실행하거나 ② Naver 내부 API 역공학 또는 ③ Playwright stealth 모드 시도

---

## 🔵 장기 / 보류

- ✅ ~~**스케치바이브 MVP 개발**~~ — Phase 1 완료. Nexus 캔버스 → Claude → Mermaid 변환 + 확인 + .html 뷰어 저장
- ✅ ~~**스케치바이브 Phase 2**~~ — MCP 서버(FastMCP) + 정확도 향상(_parse_drawflow 강화) + "맞아" 후 구현 브리지(confirmed API + MCP 도구)
- ✅ ~~**스케치바이브 Phase 3**~~ — 아키텍처 재설계: 서버 변환 제거 + MCP 양방향(update_canvas/request_approval) + SSE 실시간 캔버스 + 팔레트 버그 수정
- ⬜ **스케치바이브 이름/특허** (나중에) — 상표 충돌(getsketchvibe.com) 재검토 + 특허 출원 범위 확정 (법무팀장 논의)
- ⬜ **NEXUS MCP 연동** — Claude가 NEXUS 캔버스 JSON 읽어서 시스템 이해 + 대표님 시각적 논의
- ⬜ **DB soul 오버라이드 정리** — souls/*.md만 쓰도록 통일 (중복 오버라이드 제거)
- ⬜ **이미지 스타일 개선** — 대표님 AI 인플루언서 스타일 확정 후 적용 (보류 중)
- ⬜ **Phase 7~12 대형 로드맵**
  - Phase 7: 풀 백엔드 전환 (arm_server → app.py)
  - Phase 8: 기능 자동 활성화 (orchestrator, scheduler)
  - Phase 9: 외부 연동 (SNS, 텔레그램 업그레이드)
  - Phase 10: 전문 도구 검증
  - Phase 11: 에이전트 소울 고도화
  - Phase 12: 프로덕션 마무리

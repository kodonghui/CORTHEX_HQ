# CORTHEX HQ — BACKLOG

> **규칙**: 미완료 항목은 전부 여기만. 날짜 파일에 ⬜ 절대 금지.
> **수시 업데이트**: 완료되면 즉시 ✅ 표시 or 삭제. 새 항목 발견 시 즉시 추가.
> 🔴 **매 배포 시 반드시 갱신!** — 배포하고 BACKLOG 안 건드리면 미완성!
> 마지막 업데이트: 2026-03-01 빌드#745 (PR#721 인디고 B 팔레트 #171730 + violet-500)

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
- ⬜ **deploy.yml에 selenium 추가 필요** — PAT에 workflow 스코프 없어서 push 불가. 대표님이 GitHub에서 직접 수정하거나 토큰 스코프 추가 필요. 현재는 수동 설치로 동작 중
- ✅ ~~**4건 동시 승인 시 3건 멈춤**~~ — asyncio.Lock(_publish_lock) 추가로 순차 처리 (빌드#717)

---

## 🟡 코드 개선

- ✅ ~~**에이전트 CLI 전환**~~ — 모든 Claude 호출을 CLI(Max 구독)로 전환. 에이전트 비용 $0. 빌드 #708~#710
- ✅ ~~**4-3: arm_server.py 리팩토링 P9**~~ — P9 완료 (1,843→1,075줄, 9개 모듈 10,562줄 분리, 91%). 리팩토링 종료
- ✅ ~~**도구 합병: pricing**~~ — pricing_sensitivity 삭제, Gabor-Granger+수익최적화를 pricing_optimizer에 이식 (빌드 #655 예정)
- ✅ ~~**도구 합병: 고객분석**~~ — customer_cohort_analyzer 삭제, RFM+CAC 회수를 customer_ltv_model에 이식 (빌드 #655 예정)

---

## 🟢 대표님이 직접 해야 하는 것

- ✅ ~~**Instagram Meta 앱 설정**~~ — 토큰 발급 + GitHub Secrets 등록 + 코드 연동 완료
- ✅ ~~**Instagram 실제 발행 테스트**~~ — 대표님이 직접 발행 성공 확인 (2026-02-28)

---

## 🟡 대개편 Phase 1 후속 (빌드 #722~#725 배포 완료)

> 기획: product-brief + ux-design-spec + prd 완료 (2026-03-01)
> 구현: 빌드 #722~#725 — CSS 디자인시스템 + 수직탭바 + 에메랄드 팔레트 + 배경 밝기
> 다음: 대표님 실사용 후 버그/개선 수정

- ⬜ **대개편 Phase 1 피드백 반영** — 대표님이 corthex-hq.com 실사용 후 버그/개선 사항 수정
- ⬜ **다크/라이트 모드 경고창** — 런타임 재현 후 원인 파악 (코드에서 원인 불명)
- ⬜ **AgentStatusBar** — FR-12: 에이전트 온라인/작업중/오류 상태 표시 (PRD 미구현)
- ⬜ **ReportCard 리스트뷰** — FR-32~40: 유형 배지 + 제목 1줄 + 날짜 (PRD 미구현)
- ⬜ **대개편 Phase 2 착수 조건** — Phase 1 KPI 달성 확인 (7일 연속 "열고 싶다") 후 아고라/넥서스 재설계

---

## 🟡 SNS 자동 발행

- ✅ ~~**티스토리 자동 발행**~~ — 공개 발행 성공! ActionChains label 클릭으로 React 라디오 전환. `tistory_publisher.py` 전면 수정
- ✅ ~~**다음카페(서로연) 자동 발행**~~ — 발행 성공! `logins.daum.net` → 카카오 OAuth → `united_write` → TinyMCE. `daum_cafe_publisher.py` 전면 수정
- ✅ ~~**SNS 웹 승인+자동발행**~~ — 웹에서 "승인+발행" 1클릭 → approve 후 asyncio.create_task로 자동 발행. _get_publisher() 헬퍼 추출
- ✅ ~~**SNS 텔레그램 승인+자동발행**~~ — bot.py handle_callback에 _auto_publish_after_approve 트리거 추가 (빌드#717)
- ✅ ~~**SNS submit 즉시 알림**~~ — sns_manager._handle_submit() 완료 시 즉시 notify_sns_approval() 트리거 (빌드#717)
- ✅ ~~**카드뉴스 시리즈 생성기**~~ — `card_news_series` action 추가 (빌드#701). 5~10장 한 번에 생성, 시리즈 일관성 프롬프트, SNS media_urls 자동 출력
  - V2 고려: 디자인 품질 부족 시 HTML 템플릿 + Playwright 방식 검토
- ⬜ **페이스북 자동 발행 검토** — Graph API로 페이지/그룹 게시 가능 여부 조사. Meta 개발자 계정 필요. 티스토리/다음카페 완료 후 착수
- ⬜ **X(트위터) 자동 발행 검토** — X API v2 게시 가능 여부 조사. 유료 플랜(Basic $100/월) 필요할 수 있음. 티스토리/다음카페 완료 후 착수
- 🔴 **네이버 블로그 자동 발행 — 보류** (2026-02-28 판정)
  - 시도: Selenium + ActionChains 글자별 타이핑 / JS injection + 이벤트 디스패치 / undetected-chromedriver / chromedriver cdc_ 패치 / 쿠키 기반 로그인
  - 결과: 전부 실패. 네이버가 헤드리스 브라우저 자체를 CAPTCHA로 차단. 쿠키 로드 후 naver.com은 로그인되나 blog.naver.com 글쓰기 접속 시 재로그인 요구 (세션 불일치)
  - 원인: 네이버 2025년 이후 봇 탐지 대폭 강화. snap chromedriver(ARM)는 패치 불가(GLIBC 호환 문제)
  - 재도전 조건: ① 대표님 PC(데스크톱)에서 실행하거나 ② Naver 내부 API 역공학 또는 ③ Playwright stealth 모드 시도

---

## 🔵 장기 / 보류

- ⬜ **bmad soul 행동패턴 CORTHEX 직원 흡수** — bmad `pm/analyst/tech-writer` 역할의 행동 패턴을 CORTHEX 직원 soul에 흡수. 대상: 전략팀장(pm), 콘텐츠팀장(tech-writer), 금융분석팀장(analyst). **조건**: v5 직원 구성 확정 후 착수. 상세 방향: `docs/claude-rules/에이전트_팀.md`

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

---

## 🟡 UX 대개편 후속 (빌드 #733~#741)

> Phase 1+2+밝기+v5+피드백버그+인디고팔레트+로그인화면 전부 배포 완료 (빌드 #741).

- ✅ ~~**Phase 1: 팔레트 교체**~~ — 네온→SaaS (violet #8b5cf6, 배경 #121216) 빌드 #733
- ✅ ~~**confirmModal 글리치 수정**~~ — x-show+transition → x-if 교체 빌드 #734
- ✅ ~~**다크모드 밝기 상향**~~ — #121216 → #1e1e26 빌드 #736
- ✅ ~~**Phase 2: 탭바 pill + 사이드바 팀카드**~~ — 빌드 #735
- ✅ ~~**PR #712 배포**~~ — v5 로그인/3본부/기밀문서탭/CLI 라우팅 — 빌드 #737
- ✅ ~~**피드백 핀 버그 수정**~~ — loadFeedbackPins() data.feedbacks→data.items 키 불일치 수정 + E2E 13개 — 빌드 #739
- ✅ ~~**인디고 팔레트**~~ — 다크모드 bg #1e1e40 + violet-400 강조 — 빌드 #740
- ✅ ~~**로그인 화면 풀스크린**~~ — bootstrap mode 우회 버그 수정 + 풀스크린 재설계 — 빌드 #741
- ⬜ **Phase 3** — 채팅버블 리디자인, 홈 대시보드 카드, 사무실 뷰 팀원 카드 (선택)
- ⬜ **누나 비밀번호 변경** — 설정에서 `sister2026` → 원하는 값
- ⬜ **CLAUDE_API_KEY_SISTER 등록** — 누나 Claude 계정 생기면 GitHub Secrets 추가

## 🔵 v5 추후 작업

- ⬜ **사주 본부 에이전트 추가** — 누나 합류 시 `org: saju, cli_owner: sister` 에이전트 생성
- ⬜ **스케치바이브 임시 특허 출원** — CORTHEX CLO에게 위임 (임시 출원 150~300만원)
- ⬜ **리트마스터 예창패 계획서** — CORTHEX CSO에게 위임

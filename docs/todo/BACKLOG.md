# CORTHEX HQ — BACKLOG

> **규칙**: 미완료 항목은 전부 여기만. 날짜 파일에 ⬜ 절대 금지.
> **수시 업데이트**: 완료되면 즉시 ✅ 표시 or 삭제. 새 항목 발견 시 즉시 추가.
> 🔴 **매 배포 시 반드시 갱신!** — 배포하고 BACKLOG 안 건드리면 미완성!
> 마지막 업데이트: 2026-02-28 빌드#675 (릴스 파이프라인 + output 경로 통일)

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
- ⬜ **Instagram 실제 발행 테스트** — corthex-hq.com에서 이미지 URL + 캡션으로 발행 테스트 필요 (개발 모드)

---

## 🔵 장기 / 보류

- ✅ ~~**스케치바이브 MVP 개발**~~ — Phase 1 완료. Nexus 캔버스 → Claude → Mermaid 변환 + 확인 + .html 뷰어 저장. REST API로 캔버스 상태 노출
- ⬜ **스케치바이브 Phase 2** — MCP 서버 별도 프로세스 + 복잡한 스케치 정확도 향상 + "맞아" 후 자동 구현 착수
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

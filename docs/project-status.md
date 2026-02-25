# CORTHEX HQ - 프로젝트 현재 상태

> **목적**: 새 세션 시작 시 현재 상태 즉시 파악용. 매 작업 완료 시 업데이트.
> **아카이브**: `docs/archive/project-status-archive.md` (2/20~2/23 기록)

---

## 마지막 업데이트

- **날짜**: 2026-02-25
- **버전**: `4.00.000`
- **빌드**: 배포 대기 중
- **서버**: https://corthex-hq.com

## ✅ 완료 — Soul Gym 경쟁 진화 시스템 (2026-02-25)

- **새 파일**: `web/soul_gym_engine.py` (~300줄), `web/handlers/soul_gym_handler.py` (~100줄)
- **DB 추가**: `soul_gym_rounds` 테이블 + CRUD 함수 3개
- **크론**: 매주 월요일 03:00 KST 자동 실행
- **웹 UI**: 전력분석 탭에 SOUL GYM 섹션 (기록 테이블 + Dry Run + 전체 진화 버튼)
- **이원화**: Gym=flash2.5(모의투자) / 실사용=기존 모델
- **자동 채택**: +3점 이상 개선 시 자동 소울 교체 (EvoPrompt/OPRO/DGM 논문 기반)
- **설계 문서**: `docs/architecture/soul-gym-algorithm.md`

## ✅ 완료 — 노션 DB 매핑 수정 (2026-02-25, 빌드#575)

- 비서실장만 비서실 DB, 팀장 6명→에이전트 산출물 DB 분리
- 에이전트 산출물 DB 컬럼명 수정: 에이전트/보고유형/부서
- 상세: `docs/updates/2026-02-25_v4대개편-노션수정.md`

## ⬜ Bash 도구 이슈 메모 (2.1.55 현재는 괜찮음)

- 패치 스크립트 위치: `C:\Users\elddl\.claude\patch-claude-extension.ps1`
- 업데이트 후 재발 시: PowerShell 관리자로 setup-auto-patch.ps1 실행
- 주의: extension.js 직접 Edit 패치는 역효과날 수 있음 (데스크탑앱이 복구함)

---

## ✅ 완료 — CORTHEX v4 대개편 (2026-02-25)

**6팀장 체제로 전면 개편:**
- 전문가급 22명 전원 해고, 팀장 6명 체제 확립
- 처장→팀장 리브랜딩: 투자팀장/법무팀장/전략팀장/마케팅팀장/콘텐츠팀장
- 팀장 Soul 강화: 전문가 지식 전부 흡수 (FILM, 6시그마, Lean Canvas, IPR Landscaping 등)
- agents.yaml 22개 specialist 삭제, UI agentNames 정리
- 상세: `docs/archive/2026-02-25_구조조정-고별사.md`

---

## ✅ 완료 — AI 크레딧 소진 자동 폴백 (2026-02-25)

- Anthropic 400 에러 → Google/OpenAI 자동 전환
- 리셋: `/api/debug/reset-exhausted-providers`
- 상세: `docs/updates/2026-02-25_크레딧소진-자동폴백.md`

## ✅ 완료 — 긴급 버그 4건 + 사유 특정 재검수 (2026-02-25)

- CIO 타임아웃 300→600초
- CSO 무단 스폰 차단 (CSO→CIO 기본 크론 변경)
- QA D1 기준 "도구사용→논리연결"로 변경
- 크론 삭제 → deleted_schedules DB 기록
- 사유 특정 재검수: `targeted_hybrid_review()` — 반려 항목만 재채점

## ✅ 완료 — NEXUS 대개편 (2026-02-25)

- 3D 시스템 맵: 70노드 (7카테고리), 풀스크린 오버레이
- 헤더 4번째 버튼 (채팅/사무실/대시보드/NEXUS), ESC 닫기
- 조직도 탭 삭제 (NEXUS 3D 대체)
- 설계 문서: `docs/architecture/nexus-design.md`

## ✅ 완료 — 블라인드 채점 품질 개선 13 Phase (2026-02-25)

- Phase 0~13 전체 완료, 테스트 25건 통과
- 상세: `docs/updates/2026-02-25_블라인드채점-품질개선.md`

## ✅ 완료 — P0 버그 3건 + 로그 버그 6건 (2026-02-24)

- P0: GPT 전문가 즉사 / QA 허위합격 / CIO 할루시네이션
- 로그 버그 6건: 중복표시, 실시간 미반영, 개수 불일치 등

---

## ⬜ 미완료 이관

- **노션 DB 실제 저장 검증** — CIO 분석 실행 후 노션 확인 필요
- **NEXUS MCP 연동** — Claude가 캔버스 JSON 읽어서 시스템 이해

---

## 🔴 CTO — 동면 상태

> 2026-02-22 대표님 지시. 용도 확정까지 CTO 관련 작업 보류.

---

## 🎉 첫 실매매 (2026-02-21)

NVDA 1주 @ $189.115 — KIS 실계좌 체결 완료

---

## CEO 확정 설계 결정

| 항목 | 결정 |
|------|------|
| 실거래 UI | 2행 2열: 실거래(한국\|미국) / 모의투자(한국\|미국) |
| 사령관실 | SSE 상시 + P2P 실시간 + 뱃지 + 네트워크 다이어그램 |
| 디버그 URL | 버그 시 즉석 생성 → 대표님에게 적극 제공 |
| CIO 목표가 | CIO가 분석 후 직접 산출 |
| order_size: 0 | CIO 비중 자율 (정상! 변경 금지) |

---

## ✅ 팀장 단독 분석 + QA 게이트 (2026-02-25 저녁)

- 전문가 위임 제거 → `_call_agent()` 직접 호출 (동면 전문가 무한대기 해결)
- `_chief_qa_review()` — 비서실장 5항목 QA (결론/근거/리스크/형식/논리)
- 시그널에 qa_passed/qa_reason 추가, QA 반려 시 매매 자동 중단
- `thinking.type: enabled → adaptive` (Claude API deprecation 대응)
- Soul Gym 벤치마크 설계: `docs/architecture/soul-gym-benchmarks.md` (6팀장 맞춤)

---

## 프로젝트 기본 정보

| 항목 | 값 |
|------|-----|
| 저장소 | https://github.com/kodonghui/CORTHEX_HQ |
| 서버 | Oracle Cloud ARM 24GB (corthex-hq.com) |
| 버전 | 4.00.000 |
| 에이전트 | 7명 (6팀장 체제) |
| 도구 | 89개 (tools.yaml 기준) |
| DB | SQLite (/home/ubuntu/corthex.db) |
| GitHub Secrets | 50+ 전부 등록 완료 |

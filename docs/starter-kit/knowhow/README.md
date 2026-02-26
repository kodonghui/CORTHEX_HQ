# CORTHEX 노하우 허브 (Knowhow Hub)

> **목적**: CORTHEX HQ를 만들면서 검증된 설계 패턴, 방법론, 아이디어를 한 곳에 모은 것.
> 새 프로젝트 시작 시 이 폴더 전체를 복사해서 CLAUDE.md에 "knowhow 참조해서 진행해" 하면 됨.
>
> **구 위치**: `docs/starter-kit/` (이동됨)

---

## 📦 이 폴더에 있는 것 (전부 CORTHEX에서 검증)

| # | 파일 | 한 줄 요약 |
|---|------|-----------|
| 01 | `01-architecture.md` | 코드가 커졌을 때 구조적으로 다시 짜는 방법 |
| 02 | `02-nexus.md` | 3D/캔버스로 시스템을 시각화하는 패턴 |
| 03 | `03-web-performance.md` | 웹이 빠르게 뜨도록 만드는 규칙 7가지 |
| 04 | `04-design-system.md` | 색상/폰트/컴포넌트/인터랙션 디자인 패턴 |
| 05 | `05-quality-rubric.md` | AI 에이전트 품질 검수 (D1/ID/블라인드 채점) |
| 06 | `06-workflow-prediction.md` | 배포 전 예측 → 선제 보강 방법론 (대표님 발명) |
| 07 | `07-inspection-protocol.md` | 코드 전수검사 프로토콜 + 팀 편성 기준 |
| 08 | `08-ceo-ideas.md` | 대표님 아이디어 #001~#009 전체 기록 |
| 09 | `09-corthex-vision.md` | CORTHEX 비전 + 리트마스터 컨텍스트 |
| 10 | `10-telegram.md` | 텔레그램 봇 패턴 (알림/명령/자동보고) |
| 11 | `11-claude-template.md` | 새 프로젝트용 CLAUDE.md 템플릿 |

---

## 🔴 핵심 원칙 (모든 프로젝트에 적용)

1. **메모리 파일 금지** — 모든 정보는 git 파일에만 (`docs/`, `config/`, `CLAUDE.md`)
2. **구조로 해결, 프롬프트에 의존 금지** — "도구 써라" 프롬프트 ❌ → 코드 구조로 강제 ✅
3. **비개발자 설명 필수** — 모든 기술 문서에 비유 + 구체적 숫자 포함
4. **작업 완료 5단계** — 업데이트 기록 → 현황 갱신 → TODO → 커밋/배포 → 보고
5. **토큰 절약** — Glob/Grep 직접 사용, 서브에이전트는 3회 실패 후에만

---

## 🚀 새 프로젝트 시작 체크리스트

- [ ] 이 폴더 복사
- [ ] `11-claude-template.md`로 CLAUDE.md 작성
- [ ] `docs/project-status.md` 생성
- [ ] `docs/updates/` 폴더 생성
- [ ] `docs/todo/` 폴더 생성
- [ ] GitHub Secrets 등록
- [ ] 자동 배포 설정 (deploy.yml)

---

## 🔗 CORTHEX HQ 원본 위치

| 파일 | 경로 |
|------|------|
| CEO 아이디어 (최신) | `docs/ceo-ideas.md` |
| 비전 (최신) | `docs/corthex-vision.md` |
| 운영 레퍼런스 | `docs/claude-reference.md` |
| 배포 가이드 | `docs/deploy-guide.md` |
| 전수검사 원본 | `docs/inspection-protocol.md` |
| 워크플로우 예측 원본 | `docs/methodology/workflow-prediction.md` |

# CORTHEX HQ - 프로젝트 현재 상태

> **이 파일의 목적**: 클로드가 새 세션을 시작하거나 대화 기억이 리셋될 때, 이 파일을 읽으면 "프로젝트가 지금 어디까지 진행됐는지"를 바로 파악할 수 있도록 하는 파일입니다.
>
> **규칙**: 매 작업이 끝날 때마다 이 파일을 업데이트할 것.

---

## 마지막 업데이트

- **날짜**: 2026-02-15
- **버전**: `0.05.050`
- **작업 브랜치**: claude/design-neutral-dark-overhaul
- **작업 내용**: 대시보드 디자인 전면 리뉴얼 — 남색→뉴트럴 다크, CSS 변수 기반 자동 테마 전환, 라이트모드 완전 수정
- **빌드 번호**: 배포 후 확인 (GitHub Actions `deploy.yml` 실행 번호 = 빌드 번호)

---

## 프로젝트 개요

- **프로젝트명**: CORTHEX HQ (AI 에이전트 법인 시스템)
- **핵심 구조**: 25~29명의 AI 에이전트가 실제 회사처럼 부서별로 일하는 시스템
- **기술 스택**: Python (백엔드) + Tailwind CSS + Alpine.js (프론트엔드, CDN)
- **저장소**: https://github.com/kodonghui/CORTHEX_HQ

---

## 현재 완료된 주요 기능

1. **웹 대시보드** (`web/` 폴더) - AI 에이전트들의 상태를 보여주는 화면
2. **텔레그램 모바일 지휘 시스템** - 텔레그램으로 AI 에이전트를 제어하는 기능
3. **부서별 전문가 도구** - CTO, CSO, CLO, CIO, CMO 등 각 부서별 AI 도구 구현
4. **프론트엔드 UX/UI 전수 검사 및 수정** - 디자인 시스템(hq-* 컬러 토큰) 적용
5. **테마(다크/라이트) 가시성 전면 수정** - CSS 변수 기반 자동 테마 전환, 하드코딩 색상 30곳+ 교체, 대비 개선, 색상 밸런스 조정 (2026-02-15)
   - **최종 해결** (2026-02-15): 순수 CSS 색상 시스템 구축 — 194개+ hq-* 클래스를 Tailwind CDN 없이 직접 정의. text/bg/border/hover/focus/gradient/ring/shadow 전부 하드코딩. Tailwind CDN은 레이아웃(flex, grid, padding)만 담당
6. **줄바꿈 자동 통일 설정** (`.gitattributes`) - 윈도우에서 작업해도 줄바꿈 충돌 안 생기게 설정
7. **외부 접속 기능** (`CORTHEX_외부접속_시작.bat`) - Cloudflare Tunnel로 어디서든 웹 접속 가능 (회사컴 켜져 있어야 함)
8. **Oracle Cloud 24시간 서버** - 무료 서버(VM.Standard.E2.1.Micro)에 웹사이트 배포 완료
   - 서버 IP: `168.107.28.100`
   - 운영체제: Ubuntu 24.04
   - 웹서버: nginx + 경량 미니 백엔드(FastAPI)
   - 회사 컴퓨터 꺼져도 대시보드 화면 접속 가능
9. **GitHub Actions 자동 배포** - main에 코드 합쳐지면 서버에 자동 반영
   - `.github/workflows/deploy.yml` 워크플로우
   - **main에 push되면 무조건 실행** (paths 필터 제거됨)
   - GitHub Secrets에 SSH 키, 서버 IP 등록 완료
10. **노션 보고 의무 섹션 추가** - 29개 에이전트 Soul 파일에 작업 완료 시 노션 DB에 보고서 자동 제출 규칙 추가
11. **비서실 보좌관 이름 변경** - 브리핑→총괄, 작전→진행, 부서→소통으로 이름 변경 완료
12. **웹 세션 환경변수 자동 설정** (`.claude/scripts/setup-env.sh`) - GitHub Codespaces Secrets에서 API 키를 읽어 `.env.local` 자동 생성
13. **AI 모델 설정 개선** (2026-02-15) - Claude 4.5/4.6 + GPT-5 이상 8개 모델 제공, Codex 제거, Provider별 그룹화(Anthropic/OpenAI)로 UI 가독성 향상
14. **빌드 번호 시스템** (2026-02-15) - GitHub Actions run number를 빌드 번호로 사용, 웹 화면에 자동 표시, 배포 확인 즉시 가능
15. **my-skills-plugin 88개 스킬 도구 등록** (2026-02-15) - 마케팅(22개), 개발프로세스(20개), 코딩패턴(25개), 유틸리티(16개), 메타(5개) 스킬을 도구로 등록하고, 29개 에이전트에게 역할별 할당 완료
16. **빌드 번호 통일** (2026-02-15) - mini_server.py가 git 커밋 개수(#399)를 빌드 번호로 쓰던 문제 제거. 이제 deploy.yml의 GitHub Actions 실행 번호 하나만 사용
17. **에이전트 설정 파일 로드 문제 해결** (2026-02-15) - 서버에서 agents.yaml/tools.yaml을 못 읽던 문제 완전 해결. 원인: 서버가 git 저장소에서 직접 실행되는데 JSON 파일이 다른 경로에 생성됨 + 서버 Python에 PyYAML 미설치. 해결: 배포 시 시스템 Python으로 YAML→JSON 변환, 양쪽 경로 모두에 생성
18. **백엔드 vs 프론트엔드 전수검사** (2026-02-15) - 미니서버(경량 서버)가 프론트엔드가 요구하는 75개 API 중 20개만 지원하는 것 확인. 나머지 55개 미지원으로 예약/워크플로우/지식/아카이브/SNS 탭이 빈 화면. 버전 번호 규칙(X.YY.ZZZ) 도입

---

## 진행 중인 작업

- **미니서버 기능 확장 필요**: 설정 파일(presets/schedules/workflows/budget/quality_rules)을 읽어서 빈 화면 해소 필요
- **노션 보고 시스템 환경 설정 필요**: `.env.local`에 실제 `NOTION_API_KEY`와 `NOTION_DEFAULT_DB_ID` 값을 입력해야 에이전트들의 노션 보고가 실제로 작동함
- **노션 DB data_source_id**: `ee0527e4-697b-4cb6-8df0-6dca3f59ad4e`

---

## 알려진 문제점

- **미니서버 기능 부족 (핵심 문제)**: Oracle Cloud 서버의 `mini_server.py`는 GET 20개만 지원. 프론트엔드가 요구하는 75개 API 중 55개가 누락되어 대부분의 탭이 빈 화면으로 표시됨 (2026-02-15 전수검사로 확인)
  - 빈 화면인 탭: 예약, 워크플로우, 지식, 아카이브, SNS
  - 데이터 없는 탭: 성능, 작업내역
  - 설정 파일(presets.yaml, schedules.yaml, workflows.yaml)을 미니서버가 안 읽음
  - POST/PUT/DELETE API가 하나도 없어서 저장/수정/삭제 기능 전부 불가
- ~~에이전트 스킬 탭에서 모든 에이전트가 "모든 도구 사용 가능"으로 표시~~ → 수정 완료 (2026-02-14)
- ~~다크모드 텍스트 안 보이는 문제~~ → 순수 CSS 색상 시스템 + gridPulse 분리로 완전 해결 (2026-02-15)
- ~~빌드 번호 불일치 (#399 vs #37)~~ → deploy.yml 번호로 통일 (2026-02-15)
- ~~에이전트 스킬 탭에서 모든 에이전트가 "도구 없음"으로 표시~~ → JSON 폴백 추가로 완전 해결 (2026-02-15)

---

## 다음에 할 일 (우선순위 순)

1. **미니서버 기능 확장** — 설정 파일(presets/schedules/workflows/budget/quality_rules)을 읽어서 빈 화면 해소
2. **미니서버 /api/health 추가** — 시스템 건강상태 API 추가
3. **미니서버 SNS 상태 API 추가** — sns.yaml을 읽어 연동 상태 표시
4. GitHub Codespaces Secrets에 `NOTION_API_KEY` 등 실제 API 키 등록
5. 도메인(corthex.com 등) 연결 → IP 주소 대신 이름으로 접속
4. HTTPS(보안 연결) 설정 → Let's Encrypt 무료 인증서

---

## Oracle Cloud 서버 정보

| 항목 | 값 |
|------|-----|
| 서버 IP | `168.107.28.100` |
| 서버 타입 | VM.Standard.E2.1.Micro (무료) |
| 리전 | ap-chuncheon-1 (춘천) |
| 운영체제 | Ubuntu 24.04 LTS |
| SSH 키 | Cloud Shell의 `~/.ssh/corthex_key` |
| SSH 접속 | `ssh -i ~/.ssh/corthex_key ubuntu@168.107.28.100` |
| 웹서버 | nginx |
| 웹사이트 경로 | `/var/www/html/` |
| 인스턴스 OCID | `ocid1.instance.oc1.ap-chuncheon-1.an4w4ljrg3nos2achny2lnq7cpozjvdgay7k4abi44e5alnnmuvh2qf43deq` |

## 중요한 결정 사항 (변경하면 안 되는 것들)

- 모든 UI 텍스트는 **한국어**
- 시간대는 **Asia/Seoul (KST, UTC+9)**
- 디자인은 **hq-* 커스텀 컬러 토큰** 사용 (순수 CSS 하드코딩 + CSS 변수 병용, Tailwind CDN은 레이아웃만 담당)
- Git 브랜치명은 **claude/** 로 시작
- 작업 완료 시 커밋 메시지에 **[완료]** 포함 필수
- **빌드 번호는 오직 `deploy.yml`의 `github.run_number`만 사용** (git 커밋 개수 사용 금지)
- 에이전트 산출물 DB data_source_id: **`ee0527e4-697b-4cb6-8df0-6dca3f59ad4e`**
- 환경변수 파일은 **.env.local** 사용 권장 (`.env`는 AnySign4PC 등이 잠글 수 있음)

# CORTHEX HQ - 프로젝트 현재 상태

> **이 파일의 목적**: 클로드가 새 세션을 시작하거나 대화 기억이 리셋될 때, 이 파일을 읽으면 "프로젝트가 지금 어디까지 진행됐는지"를 바로 파악할 수 있도록 하는 파일입니다.
>
> **규칙**: 매 작업이 끝날 때마다 이 파일을 업데이트할 것.

---

## 마지막 업데이트

- **날짜**: 2026-02-14
- **작업 브랜치**: claude/sync-multiple-computers-Nz8IR
- **작업 내용**: Oracle Cloud 서버 구축 + 미니 백엔드 배포 + GitHub Actions 자동 배포 설정

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
5. **줄바꿈 자동 통일 설정** (`.gitattributes`) - 윈도우에서 작업해도 줄바꿈 충돌 안 생기게 설정
6. **외부 접속 기능** (`CORTHEX_외부접속_시작.bat`) - Cloudflare Tunnel로 어디서든 웹 접속 가능 (회사컴 켜져 있어야 함)
7. **Oracle Cloud 24시간 서버** - 무료 서버(VM.Standard.E2.1.Micro)에 웹사이트 배포 완료
   - 서버 IP: `168.107.28.100`
   - 운영체제: Ubuntu 24.04
   - 웹서버: nginx + 경량 미니 백엔드(FastAPI)
   - 회사 컴퓨터 꺼져도 대시보드 화면 접속 가능
8. **GitHub Actions 자동 배포** - main에 코드 합쳐지면 서버에 자동 반영
   - `.github/workflows/deploy.yml` 워크플로우
   - web/ 폴더 변경 시에만 실행
   - GitHub Secrets에 SSH 키, 서버 IP 등록 완료

---

## 진행 중인 작업

- 없음 (서버 구축 및 배포 완료!)

---

## 알려진 문제점

- 현재 경량 모드로 운영 중 (AI 에이전트 실제 동작은 안 함, 대시보드 표시만 정상)

---

## 다음에 할 일 (우선순위 순)

1. 도메인(corthex.com 등) 연결 → IP 주소 대신 이름으로 접속
2. HTTPS(보안 연결) 설정 → Let's Encrypt 무료 인증서

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
- 디자인은 **hq-* 커스텀 컬러 토큰** 사용
- Git 브랜치명은 **claude/** 로 시작
- 작업 완료 시 커밋 메시지에 **[완료]** 포함 필수

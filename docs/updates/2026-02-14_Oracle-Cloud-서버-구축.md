# Oracle Cloud 무료 서버 구축 및 웹사이트 배포

## 작업 날짜
2026-02-14

## 작업 브랜치
claude/sync-multiple-computers-Nz8IR

## 변경 사항 요약

### 뭘 했는지
Oracle Cloud에 **24시간 무료 서버**를 만들고, CORTHEX HQ 대시보드 웹사이트를 배포했습니다.

### 왜 했는지
기존에는 Cloudflare Tunnel 방식으로 외부 접속을 했는데, **회사 컴퓨터가 켜져 있어야만** 접속이 가능했습니다.
Oracle Cloud 서버를 사용하면 **회사 컴퓨터가 꺼져 있어도** 언제 어디서든 대시보드에 접속할 수 있습니다.

### 상세 작업 내역

1. **Oracle Cloud 계정 설정**
   - 리전(지역): 춘천 (ap-chuncheon-1)
   - Cloud Shell(웹 터미널)에서 작업

2. **무료 서버 생성**
   - 서버 타입: VM.Standard.E2.1.Micro (영구 무료)
   - CPU: 1개 (2코어), 메모리: 1GB
   - 운영체제: Ubuntu 24.04 LTS
   - 공개 IP: `168.107.28.100`

3. **방화벽 설정** (2단계 모두 완료)
   - Oracle Cloud 보안 목록: 포트 80(HTTP), 443(HTTPS) 열기
   - 서버 내부 iptables: 포트 80, 443 열기 (REJECT 규칙 앞에 배치)

4. **웹서버 설치 및 배포**
   - nginx 웹서버 설치
   - CORTHEX HQ 대시보드 `index.html` 배포
   - 접속 주소: http://168.107.28.100

### 새로 만든/수정한 파일
- `docs/project-status.md` (프로젝트 현재 상태) — Oracle Cloud 서버 정보 추가
- `docs/updates/2026-02-14_Oracle-Cloud-서버-구축.md` (이 파일) — 작업 기록

## 현재 상태

- ✅ 서버 생성 완료
- ✅ 방화벽 설정 완료
- ✅ nginx 설치 완료
- ✅ 대시보드 UI 표시 정상
- ⚠️ "서버 연결이 끊어졌습니다" 메시지 표시 — Python 백엔드가 아직 서버에 설치되지 않았기 때문

## 서버 접속 정보

| 항목 | 값 |
|------|-----|
| 서버 IP | `168.107.28.100` |
| 웹사이트 주소 | http://168.107.28.100 |
| SSH 접속 (Cloud Shell에서) | `ssh -i ~/.ssh/corthex_key ubuntu@168.107.28.100` |
| 서버 타입 | VM.Standard.E2.1.Micro (무료) |
| 리전 | ap-chuncheon-1 (춘천) |

## 다음에 할 일

1. **Python 백엔드(FastAPI) 설치** — "서버 연결 끊어짐" 메시지 해결
2. **자동 배포 설정** — GitHub에 코드 올리면 서버에 자동 반영되게 만들기
3. **도메인 연결** — IP 주소 대신 도메인(예: corthex.com)으로 접속하게 만들기

# 외부 접속 기능 추가 (Cloudflare Tunnel)

## 작업 날짜
2026-02-14

## 작업 브랜치
claude/sync-multiple-computers-Nz8IR

## 작업 요약
어떤 컴퓨터/핸드폰에서든 CORTHEX HQ에 접속할 수 있도록 **외부 접속 기능**을 추가했습니다.

### 원리
- 회사컴에서 CORTHEX 서버를 실행하면, **Cloudflare Tunnel**이 인터넷을 통해 안전한 통로를 만들어줌
- 그 통로를 통해 외부(집, 카페, 핸드폰 등)에서 접속 가능
- 무료이고, 회사 네트워크 설정을 건드릴 필요 없음

### 조건
- 회사컴이 **켜져 있어야** 함 (모니터만 끄는 건 OK, 절전모드는 꺼야 함)
- bat 파일이 **실행 중**이어야 함

## 변경 사항

### 새로 만든 파일
| 파일 | 설명 |
|------|------|
| `CORTHEX_외부접속_시작.bat` | 더블클릭하면 CORTHEX + 외부접속 통로가 동시에 열리는 파일 |
| `docs/updates/2026-02-14_외부접속-Cloudflare-Tunnel-설정.md` | 이 기록 파일 |

### 수정한 파일
| 파일 | 설명 |
|------|------|
| `docs/project-status.md` | 프로젝트 현재 상태에 외부접속 기능 추가됨 기록 |

## 사전 설치 필요 (1번만)
- **cloudflared** 프로그램 설치
- 다운로드 주소: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi

## 사용 방법
1. `CORTHEX_외부접속_시작.bat` 더블클릭
2. 화면에 `https://xxxxx.trycloudflare.com` 형태의 주소가 나옴
3. 그 주소를 아무 브라우저에 붙여넣으면 CORTHEX 접속 완료

## 현재 상태
- 완료 (bat 파일 작성 완료, cloudflared 설치 후 바로 사용 가능)

## 다음에 할 일
- 회사컴에서 cloudflared 설치 후 테스트
- 필요하면 고정 주소(매번 같은 주소) 설정 가능 (Cloudflare 무료 계정 필요)

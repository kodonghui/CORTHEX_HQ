# 로그 분석기 DB 활동 로그 접근 기능 추가 — 2026-02-20

## 기본 정보
- **날짜**: 2026-02-20
- **버전**: 3.02.003
- **브랜치**: claude/enable-log-access-hpiHx

## 변경 사항

### 🔧 수정한 것
| 파일 | 수정 내용 (CEO가 이해할 수 있게 쉽게) |
|------|-------------------------------------|
| `src/tools/log_analyzer.py` | CTO(기술개발처)가 DB에 저장된 활동 로그를 읽을 수 있게 2가지 기능 추가: ① `activity` — 에이전트별/키워드별 활동 로그 조회, ② `trading` — 자동매매 흐름 추적 (버튼 클릭→분석→시그널→주문까지 어디서 실패했는지 자동 진단) |
| `config/tools.yaml` | log_analyzer 도구 설명에 새 액션(activity, trading)과 파라미터(agent_id, level, keyword, hours, limit) 추가 |
| `config/tools.json` | yaml2json으로 자동 생성 |

### 배경
- CEO가 전략실에서 "즉시분석/매매결정" 버튼을 눌러도 자동매매가 안 되는 문제 발생
- 원인을 파악하려 해도 매매 로그가 DB(activity_logs 테이블)에만 있어서, 기존 log_analyzer로는 볼 수 없었음
- 기존 log_analyzer는 텍스트 파일(logs/corthex.log)만 읽었음

### 해결
- CTO 에이전트(기술개발처)는 이미 log_analyzer 도구 권한이 있으므로, 도구 자체를 보강
- `action="trading"` 사용 시: CIO 에이전트의 매매 로그를 자동 수집 → 에러/경고/건너뜀/주문 시도를 분류 → AI가 "왜 매매가 안 됐는지" 자동 진단

### 🐛 발견한 버그
| 버그 | 원인 | 상태 |
|------|------|------|
| log_analyzer가 매매 로그를 못 읽음 | 매매 로그는 DB에 저장되는데, 도구는 텍스트 파일만 읽었음 | ✅ 수정 완료 |

### 📊 현재 상태
- CTO 에이전트가 `log_analyzer(action="trading")` 호출 시 자동매매 전체 흐름 진단 가능
- CTO 에이전트가 `log_analyzer(action="activity", agent_id="cio_manager")` 로 CIO 활동 로그 조회 가능

### 📋 다음에 할 일
- CTO에게 자동매매 문제 디버깅 지시 (이 도구로 원인 파악)
- 자동매매 안 되는 근본 원인 수정

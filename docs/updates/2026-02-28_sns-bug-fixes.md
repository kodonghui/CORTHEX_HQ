# 2026-02-28 — SNS 버그 4개 수정 (빌드 #717)

> 야간 자율 수행 — 대표님이 수면 중 분석·수정·배포 완료

---

## 문제 분석 (3개 병렬 에이전트)

코드베이스 전체를 3개 영역으로 나눠 분석:
1. **코어 버그** (ai_handler, agent_router, app.py)
2. **인프라/배포** (deploy.yml, SNS 퍼블리셔, requirements)
3. **아키텍처/보안** (에이전트 시스템, 에러 처리, 성능)

---

## 수정 내용 (4개)

### 1. SNS 4건 동시 승인 시 3건 멈춤 [긴급]
- **원인**: `_auto_publish_after_approve()` 4개가 동시 실행 → SQLite DB `sns_publish_queue` 읽기/쓰기 경합
- **수정**: `web/handlers/sns_handler.py`에 `_publish_lock = asyncio.Lock()` 모듈 레벨 추가
- **효과**: 4건 동시 승인 → 1건씩 순차 처리 (DB 경합 없음)

### 2. 텔레그램 승인 시 자동발행 연결
- **원인**: 텔레그램 인라인 버튼으로 승인 시 `sns_manager._handle_approve()`만 호출 → status="approved"로만 변경, 실제 발행 없음
- **수정**: `src/telegram/bot.py` `handle_callback`에 승인 성공 후 `asyncio.create_task(_auto_publish_after_approve(request_id))` 추가
- **효과**: 텔레그램 승인 = 웹 승인과 완전 동일 동작

### 3. SNS submit 즉시 텔레그램 알림
- **원인**: 마케팅팀장이 `sns_manager(action=submit)` 실행 시 30분 폴러(`_periodic_pending_checker`) 대기 필요
- **수정**: `src/tools/sns/sns_manager.py` `_handle_submit()` 완료 직후 `notifier.notify_sns_approval()` 즉시 호출
- **효과**: submit → 즉시 CEO 텔레그램 알림 (30분 → 수초)

### 4. 프로덕션 디버그 로그 제거
- **원인**: 이전 디버그 세션에서 추가한 `import traceback` + `/tmp/api_calls.log` 파일 쓰기 코드가 프로덕션에 남아있음
- **수정**: `web/ai_handler.py` `_call_anthropic()` 내 4줄 제거
- **효과**: Claude 호출마다 파일 I/O 없음, 로그 오염 없음

---

## 미완료 (PAT 스코프 문제)

- **deploy.yml rsync 수정**: `cp -r src /home/ubuntu/CORTHEX_HQ/src` → `rsync -a src/ /home/ubuntu/CORTHEX_HQ/src/`
  - 현상: 서버에 `src/src/` 18MB 중첩 디렉토리 생성 (배포 때마다)
  - 원인: `cp -r src DEST/src`는 DEST/src가 이미 존재하면 내부에 src를 복사 → `DEST/src/src/`
  - 수정 코드는 준비됨, PAT에 `workflow` 스코프 없어서 push 불가
  - **대표님 액션 필요**: GitHub Settings > Developer Settings > PAT > workflow 스코프 추가, 또는 GitHub Actions에서 직접 수정

---

## 발견된 추가 이슈 (향후 수정 권장)

- `web/state.py`: `app_state.bg_results` dict 무한 성장 (1시간마다 정리, 오래된 결과 누적 가능)
- `web/db.py`: 동적 ALTER TABLE 쿼리에 SQL 인젝션 가능성 (내부 코드지만 개선 권장)
- SNS 퍼블리셔 50+ `except Exception: pass` 패턴 (오류 묵살, 디버깅 어려움)

---

## 배포

- **PR**: #705 (claude/overnight-fixes → main)
- **빌드**: #717 (workflow_dispatch, 성공)
- **커밋**: `db2398f`

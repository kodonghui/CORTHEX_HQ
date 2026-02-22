"""CORTHEX HQ 핸들러 모듈 — API 엔드포인트를 기능별로 분리.

현재 핸들러 목록:
  - media_handler:        /api/media/* (이미지·영상 파일 관리)
  - task_handler:         /api/tasks/* (작업 CRUD)
  - knowledge_handler:    /api/knowledge/* (지식 파일 관리)
  - memory_handler:       /api/memory/* (메모리 관리)
  - feedback_handler:     /api/feedback/* (피드백 관리)
  - conversation_handler: /api/conversations/* (대화 기록)
  - archive_handler:      /api/archives/* (아카이브)
  - auth_handler:         /api/auth/* (인증·로그인·비밀번호)
  - preset_handler:       /api/presets/* (프리셋 관리)
  - schedule_handler:     /api/schedules/*, /api/workflows/* CRUD (실행 제외)
  - health_handler:       /api/health (헬스체크)
  - notion_handler:       /api/notion-log (노션 로그)
  - activity_handler:     /api/activity-logs, /api/delegation-log, /api/comms/* (활동·내부통신)
  - quality_handler:      /api/quality, /api/quality-rules/* (품질검수)
  - sns_handler:          /api/sns/*, /api/debug/instagram-token (SNS 연동·발행)
  - trading_handler:      /api/trading/*, /api/cio/* (트레이딩 CRUD·잔고·시그널)
"""

# 12. 웹 모니터링 — Claude가 서버를 직접 본다

> CORTHEX HQ에서 검증된 핵심 노하우.
> Claude Code가 WebFetch 도구로 서버 API를 직접 호출해서 실시간 모니터링 가능.

---

## 핵심 개념

비유: Claude가 "사내 CCTV를 직접 보는 것"
→ 대표님이 화면 캡처해서 보내줄 필요 없이, Claude가 직접 서버에 접속해서 로그 읽음.

---

## 모니터링 API 패턴

```python
# arm_server.py에 이 엔드포인트들 구현
@app.get("/api/activity-logs")
@app.get("/api/debug/server-logs")
@app.get("/api/debug/ai-providers")
```

Claude가 WebFetch로 직접 호출:
```
GET https://your-domain.com/api/activity-logs?limit=50
GET https://your-domain.com/api/debug/server-logs?lines=100&service=app
```

---

## 분석 모니터링 (1분마다 보고)

"로그 확인해" 또는 "분석 모니터링" 요청 시:
1. `/api/activity-logs?division=cio_manager&limit=50` 호출
2. 에이전트별 도구 호출 횟수 + 비용 + QA 결과 표 정리
3. 1분마다 반복, 완료까지 중단 없이

---

## 즉석 디버그 URL 패턴

버그 발생 시 바로 만들어서 대표님에게 제공:
```python
@app.get("/api/debug/ai-providers")
async def debug_ai_providers():
    return {
        "anthropic": {"status": "exhausted" if exhausted else "ok"},
        "openai": {"status": "ok"},
        "google": {"status": "ok"}
    }
```

→ 대표님이 브라우저에서 직접 확인 가능.

---

## 새 프로젝트 적용 체크리스트

- [ ] `/api/activity-logs` — 에이전트 활동 로그
- [ ] `/api/debug/server-logs` — 서버 시스템 로그
- [ ] `/api/debug/[버그명]` — 즉석 디버그 엔드포인트
- [ ] Cloudflare WAF에서 Claude IP 허용 (또는 WAF Skip 규칙)
- [ ] 계좌번호/API 키 응답에 절대 포함 금지

---

## CORTHEX 설정 (참고)

- 외부 접근: Cloudflare WAF Skip 규칙 (만료일 확인 필수)
- 상세 URL: `docs/claude-reference.md` 참조

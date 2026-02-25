# 10. 텔레그램 봇 패턴

> CORTHEX HQ에서 검증된 텔레그램 연동 패턴.
> AI 시스템의 "외부 알림 + 원격 명령" 채널로 활용.

---

## 핵심 활용 패턴 3가지

### 1. 알림 (Push Notification)
```python
# 중요 이벤트 발생 시 즉시 텔레그램으로 전송
async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    await httpx.post(url, json={
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    })

# 활용 예
await send_telegram("🧬 Soul 진화 제안 도착 — 승인 필요")
await send_telegram("📈 NVDA 매수 체결 @ $189.11 (신뢰도 74%)")
await send_telegram("🚨 Anthropic 크레딧 소진 → Google로 전환")
```

### 2. 뉴스 브리핑 크론
```python
# 매일 09:00 KST 자동 발송
async def daily_news_briefing():
    # 1. 뉴스 검색 (키워드별)
    # 2. AI 요약
    # 3. 텔레그램 발송
    news = await search_news("예비창업자패키지")
    summary = await ai_summarize(news)
    await send_telegram(f"📰 오늘의 뉴스\n\n{summary}")
```

### 3. 웹 채팅 응답 자동 전달
```python
# AI 에이전트 응답 → 텔레그램 자동 미러링
async def on_ai_response(response: str, agent_name: str):
    await send_telegram(f"[{agent_name}]\n{response[:500]}")
```

---

## 명령어 처리 패턴

```python
@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    text = message.get("text", "")
    chat_id = message["chat"]["id"]

    if text == "/start":
        await send_telegram("CORTHEX HQ 봇 시작!")
    elif text.startswith("/분석"):
        # CIO 분석 트리거
        asyncio.create_task(run_market_analysis())
        await send_telegram("분석 시작합니다...")
    elif text.startswith("/상태"):
        status = await get_system_status()
        await send_telegram(status)
```

---

## 크론 스케줄러 연동

```python
# 텔레그램으로 크론 CRUD
# /크론목록, /크론추가 HH:MM 작업명, /크론삭제 ID
```

---

## 주의사항

- Bot Token, Chat ID → 반드시 환경변수 (GitHub Secrets)
- 메시지 길이 4096자 제한 → 긴 내용은 분할 전송
- 계좌번호/API 키 텔레그램 전송 금지
- `/start` 무반응 버그 → webhook 등록 확인 (`setWebhook`)

---

## GitHub Secret 이름 (CORTHEX 기준)

```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

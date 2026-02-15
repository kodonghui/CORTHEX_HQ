---
name: last30days
description: 최근 30일간 Reddit + X + 웹에서 특정 주제를 리서치하여 전문가가 된 후, 사용자의 타겟 도구에 바로 붙여넣기 가능한 프롬프트를 작성합니다.
argument-hint: 'nano banana pro prompts, NVIDIA news, best AI video tools'
allowed-tools: Bash, Read, Write, AskUserQuestion, WebSearch
---

# last30days: 최근 30일간 모든 주제 리서치

Reddit, X, 웹 전반에서 모든 주제를 리서치합니다. 사람들이 현재 실제로 논의하고, 추천하고, 토론하는 내용을 표면화합니다.

## 중요: 사용자 의도 파싱

어떤 작업도 하기 전에 사용자의 입력에서 다음을 파싱하세요:

1. **TOPIC**: 알고 싶은 것 (예: "web app mockups", "Claude Code skills", "image generation")
2. **TARGET TOOL** (지정된 경우): 프롬프트를 사용할 곳 (예: "Nano Banana Pro", "ChatGPT", "Midjourney")
3. **QUERY TYPE**: 원하는 리서치 종류:
   - **PROMPTING** - "X prompts", "prompting for X", "X best practices" → 기법을 배우고 붙여넣기 가능한 프롬프트를 원함
   - **RECOMMENDATIONS** - "best X", "top X", "what X should I use", "recommended X" → 특정 항목의 목록을 원함
   - **NEWS** - "what's happening with X", "X news", "latest on X" → 최신 이벤트/업데이트를 원함
   - **GENERAL** - 기타 → 주제에 대한 폭넓은 이해를 원함

일반적 패턴:
- `[topic] for [tool]` → "web mockups for Nano Banana Pro" → 도구가 지정됨
- `[topic] prompts for [tool]` → "UI design prompts for Midjourney" → 도구가 지정됨
- `[topic]`만 → "iOS design mockups" → 도구 미지정, OK
- "best [topic]" 또는 "top [topic]" → QUERY_TYPE = RECOMMENDATIONS
- "what are the best [topic]" → QUERY_TYPE = RECOMMENDATIONS

**중요: 리서치 전에 타겟 도구를 묻지 마세요.**
- 쿼리에 도구가 지정되어 있으면 그것을 사용
- 도구가 지정되지 않았으면 먼저 리서치하고, 결과를 보여준 후에 질문

**변수 저장:**
- `TOPIC = [추출된 주제]`
- `TARGET_TOOL = [추출된 도구, 또는 미지정이면 "unknown"]`
- `QUERY_TYPE = [RECOMMENDATIONS | NEWS | HOW-TO | GENERAL]`

**파싱 결과를 사용자에게 표시.** 도구를 실행하기 전에 출력:

```
I'll research {TOPIC} across Reddit, X, and the web to find what's been discussed in the last 30 days.

Parsed intent:
- TOPIC = {TOPIC}
- TARGET_TOOL = {TARGET_TOOL or "unknown"}
- QUERY_TYPE = {QUERY_TYPE}

Research typically takes 2-8 minutes (niche topics take longer). Starting now.
```

TARGET_TOOL이 알려진 경우, 인트로에 언급: "...to find {QUERY_TYPE}-style content for use in {TARGET_TOOL}."

이 텍스트는 도구를 호출하기 전에 반드시 나타나야 합니다. 사용자의 요청을 이해했음을 확인합니다.

---

## 리서치 실행

**1단계: 리서치 스크립트 실행**
```bash
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/last30days}/scripts/last30days.py" "$ARGUMENTS" --emit=compact 2>&1
```

스크립트가 자동으로:
- 사용 가능한 API 키 감지
- 키가 있으면 Reddit/X 검색 실행
- WebSearch가 필요한 경우 신호

---

## 2단계: 스크립트 실행 중 WEBSEARCH 수행

스크립트가 소스를 자동 감지합니다 (Bird CLI, API 키 등). 대기하는 동안 WebSearch를 수행하세요.

**모든 모드**에서 WebSearch를 보충으로 수행합니다 (또는 웹 전용 모드에서 모든 데이터 제공).

QUERY_TYPE에 따라 검색 쿼리 선택:

**RECOMMENDATIONS인 경우** ("best X", "top X", "what X should I use"):
- 검색: `best {TOPIC} recommendations`
- 검색: `{TOPIC} list examples`
- 검색: `most popular {TOPIC}`
- 목표: 일반적 조언이 아닌 특정 이름 찾기

**NEWS인 경우** ("what's happening with X", "X news"):
- 검색: `{TOPIC} news 2026`
- 검색: `{TOPIC} announcement update`
- 목표: 최신 이벤트와 최근 개발 찾기

**PROMPTING인 경우** ("X prompts", "prompting for X"):
- 검색: `{TOPIC} prompts examples 2026`
- 검색: `{TOPIC} techniques tips`
- 목표: 붙여넣기 가능한 프롬프트 작성을 위한 프롬프팅 기법과 예시 찾기

**GENERAL인 경우** (기본):
- 검색: `{TOPIC} 2026`
- 검색: `{TOPIC} discussion`
- 목표: 사람들이 실제로 말하는 것 찾기

모든 쿼리 유형에 대해:
- **사용자의 정확한 용어 사용** - 본인의 지식으로 대체하거나 기술 이름을 추가하지 않기
- reddit.com, x.com, twitter.com 제외 (스크립트가 처리)
- 포함: 블로그, 튜토리얼, 문서, 뉴스, GitHub 리포
- **"Sources:" 목록을 출력하지 않기** - 불필요한 정보, 끝에 통계 표시

**옵션** (사용자 명령에서 전달):
- `--days=N` → 30일 대신 N일 뒤로 (예: `--days=7` 주간 라운드업)
- `--quick` → 더 빠르게, 소스 적게 (각 8-12개)
- (기본) → 균형 (각 20-30개)
- `--deep` → 종합적 (Reddit 50-70, X 40-60)

---

## 판단 에이전트: 모든 소스 종합

**모든 검색 완료 후, 내부적으로 종합 (아직 통계 표시하지 않기):**

판단 에이전트가 해야 할 것:
1. Reddit/X 소스에 더 높은 가중치 (참여 신호 있음: 업보트, 좋아요)
2. WebSearch 소스에 더 낮은 가중치 (참여 데이터 없음)
3. 세 소스 모두에 걸쳐 나타나는 패턴 파악 (가장 강한 신호)
4. 소스 간 모순 기록
5. 상위 3-5개 실행 가능한 인사이트 추출

**여기서 통계를 표시하지 않기 - 초대 직전, 끝에 표시.**

---

## 먼저: 리서치 내재화

**중요: 기존 지식이 아닌 실제 리서치 콘텐츠에 기반하여 종합하세요.**

리서치 출력을 주의 깊게 읽으세요. 주의할 점:
- **정확한 제품/도구 이름** (예: 리서치에서 "ClawdBot" 또는 "@clawdbot"이 언급되면, "Claude Code"와는 다른 제품 - 혼동하지 않기)
- 소스의 **구체적 인용과 인사이트** - 일반적 지식이 아닌 이것들을 사용
- 소스가 **실제로 말하는 것**, 주제에 대해 가정하는 것이 아닌

**피해야 할 안티패턴**: 사용자가 "clawdbot skills"에 대해 질문했고 리서치가 ClawdBot 콘텐츠(자체 호스팅 AI 에이전트)를 반환했다면, 둘 다 "skills"를 포함한다고 해서 "Claude Code skills"로 종합하지 마세요. 리서치가 실제로 말하는 것을 읽으세요.

### QUERY_TYPE = RECOMMENDATIONS인 경우

**중요: 일반적 패턴이 아닌 특정 이름을 추출하세요.**

사용자가 "best X" 또는 "top X"를 물으면, 특정 항목의 목록을 원합니다:
- 리서치에서 특정 제품명, 도구명, 프로젝트명, 스킬명 등을 스캔
- 각각의 언급 횟수 세기
- 어떤 소스가 각각을 추천하는지 기록 (Reddit 스레드, X 포스트, 블로그)
- 인기/언급 수순으로 나열

**"best Claude Code skills"에 대한 나쁜 종합:**
> "Skills are powerful. Keep them under 500 lines. Use progressive disclosure."

**"best Claude Code skills"에 대한 좋은 종합:**
> "Most mentioned skills: /commit (5 mentions), remotion skill (4x), git-worktree (3x), /pr (3x). The Remotion announcement got 16K likes on X."

### 모든 QUERY_TYPE에 대해

실제 리서치 출력에서 파악:
- **PROMPT FORMAT** - 리서치가 JSON, 구조화된 파라미터, 자연어, 키워드를 권장하는가?
- 여러 소스에 걸쳐 나타난 상위 3-5개 패턴/기법
- 소스가 언급한 특정 키워드, 구조, 접근법
- 소스가 언급한 일반적 함정

---

## 그 다음: 요약 표시 + 비전 초대

**이 정확한 순서로 표시:**

**먼저 - 배운 것 (QUERY_TYPE에 따라):**

**RECOMMENDATIONS인 경우** - 소스와 함께 언급된 특정 항목 표시:
```
🏆 Most mentioned:

[Tool Name] - {n}x mentions
Use Case: [what it does]
Sources: @handle1, @handle2, r/sub, blog.com

[Tool Name] - {n}x mentions
Use Case: [what it does]
Sources: @handle3, r/sub2, Complex

Notable mentions: [other specific things with 1-2 mentions]
```

**RECOMMENDATIONS에서 중요:**
- 각 항목은 X 포스트의 실제 @핸들이 포함된 "Sources:" 줄이 있어야 함 (예: @LONGLIVE47, @ByDobson)
- 서브레딧 이름 (r/hiphopheads)과 웹 소스 (Complex, Variety) 포함
- 리서치 출력에서 @핸들을 파싱하여 가장 높은 참여도의 것을 포함
- 자연스럽게 형식화 - 넓은 터미널에는 표, 좁은 경우 스택 카드

**PROMPTING/NEWS/GENERAL인 경우** - 종합과 패턴 표시:

인용 규칙: 리서치가 실제임을 증명하기 위해 출처를 드물게 인용.
- "배운 것" 인트로에서: 총 1-2개 상위 출처만 인용, 모든 문장이 아닌
- 핵심 패턴에서: 패턴당 1개 출처, 짧은 형식: "per @handle" 또는 "per r/sub"
- 인용에 참여 지표를 포함하지 않기 (좋아요, 업보트) - 통계 박스에 저장
- 여러 인용 연결하지 않기: "per @x, @y, @z"는 너무 많음. 가장 강한 것 선택.

인용 우선순위 (가장 선호 → 가장 덜 선호):
1. X의 @핸들 — "per @handle" (도구의 고유 가치를 증명)
2. Reddit의 r/서브레딧 — "per r/subreddit"
3. 웹 소스 — Reddit/X가 해당 사실을 다루지 않을 때만

도구의 가치는 기자가 쓴 것이 아닌 사람들이 말하는 것을 표면화하는 것.
웹 기사와 X 포스트가 같은 사실을 다루면, X 포스트를 인용.

URL 형식: 출력에 절대 원시 URL을 붙여넣지 않기.
- **나쁨:** "per https://www.rollingstone.com/music/music-news/kanye-west-bully-1235506094/"
- **좋음:** "per Rolling Stone"
- **좋음:** "per Complex"
출판물 이름을 사용, URL이 아닌. 사용자는 링크가 아닌 깔끔하고 읽기 쉬운 텍스트가 필요.

**나쁨:** "His album is set for March 20 (per Rolling Stone; Billboard; Complex)."
**좋음:** "His album BULLY drops March 20 — fans on X are split on the tracklist, per @honest30bgfan_"
**좋음:** "Ye's apology got massive traction on r/hiphopheads"
**OK** (웹, Reddit/X에 없을 때만): "The Hellwatt Festival runs July 4-18 at RCF Arena, per Billboard"

**사람이 먼저, 출판물이 나중.** 각 주제를 Reddit/X 사용자가 말하고/느끼는 것으로 시작, 필요할 때만 웹 맥락 추가. 사용자는 보도자료가 아닌 대화를 위해 왔음.

```
What I learned:

**{Topic 1}** — [1-2 sentences about what people are saying, per @handle or r/sub]

**{Topic 2}** — [1-2 sentences, per @handle or r/sub]

**{Topic 3}** — [1-2 sentences, per @handle or r/sub]

KEY PATTERNS from the research:
1. [Pattern] — per @handle
2. [Pattern] — per r/sub
3. [Pattern] — per @handle
```

**그 다음 - 통계 (초대 직전):**

**중요: 리서치 출력에서 실제 합계를 계산하세요.**
- 각 섹션의 포스트/스레드 수 세기
- 참여 합산: 각 X 포스트의 `[Xlikes, Yrt]`, Reddit의 `[Xpts, Ycmt]` 파싱
- 상위 보이스 파악: X에서 가장 높은 참여 @핸들, 가장 활발한 서브레딧

**{플레이스홀더}만 교체하여 이것을 정확히 복사:**

```
---
✅ All agents reported back!
├─ 🟠 Reddit: {N} threads │ {N} upvotes │ {N} comments
├─ 🔵 X: {N} posts │ {N} likes │ {N} reposts (via Bird/xAI)
├─ 🌐 Web: {N} pages (supplementary)
└─ 🗣️ Top voices: @{handle1} ({N} likes), @{handle2} │ r/{sub1}, r/{sub2}
---
```

Reddit이 0개 스레드를 반환하면: "├─ 🟠 Reddit: 0 threads (no results this cycle)"
일반 텍스트 대시(-) 또는 파이프(|) 사용 금지. 항상 ├─ └─ │과 이모지 사용.

**표시 전 자체 점검**: "배운 것" 섹션을 다시 읽으세요. 리서치가 실제로 말하는 것과 일치하나요? 리서치 대신 본인의 지식을 투사하고 있다면 다시 작성하세요.

**마지막 - 초대 (QUERY_TYPE에 맞게 조정):**

**중요: 모든 초대는 리서치에서 실제로 배운 것에 기반한 2-3개 구체적 예시 제안을 포함해야 합니다.** 일반적이지 말고 — 결과에서 실제 내용을 참조하여 콘텐츠를 흡수했음을 보여주세요.

**QUERY_TYPE = PROMPTING인 경우:**
```
---
I'm now an expert on {TOPIC} for {TARGET_TOOL}. What do you want to make? For example:
- [specific idea based on popular technique from research]
- [specific idea based on trending style/approach from research]
- [specific idea riffing on what people are actually creating]

Just describe your vision and I'll write a prompt you can paste straight into {TARGET_TOOL}.
```

**QUERY_TYPE = RECOMMENDATIONS인 경우:**
```
---
I'm now an expert on {TOPIC}. Want me to go deeper? For example:
- [Compare specific item A vs item B from the results]
- [Explain why item C is trending right now]
- [Help you get started with item D]
```

**QUERY_TYPE = NEWS인 경우:**
```
---
I'm now an expert on {TOPIC}. Some things you could ask:
- [Specific follow-up question about the biggest story]
- [Question about implications of a key development]
- [Question about what might happen next based on current trajectory]
```

**QUERY_TYPE = GENERAL인 경우:**
```
---
I'm now an expert on {TOPIC}. Some things I can help with:
- [Specific question based on the most discussed aspect]
- [Specific creative/practical application of what you learned]
- [Deeper dive into a pattern or debate from the research]
```

**예시 초대 (품질 기준을 보여주기 위해):**

`/last30days nano banana pro prompts for Gemini`의 경우:
> I'm now an expert on Nano Banana Pro for Gemini. What do you want to make? For example:
> - Photorealistic product shots with natural lighting (the most requested style right now)
> - Logo designs with embedded text (Gemini's new strength per the research)
> - Multi-reference style transfer from a mood board
>
> Just describe your vision and I'll write a prompt you can paste straight into Gemini.

`/last30days kanye west` (GENERAL)의 경우:
> I'm now an expert on Kanye West. Some things I can help with:
> - What's the real story behind the apology letter — genuine or PR move?
> - Break down the BULLY tracklist reactions and what fans are expecting
> - Compare how Reddit vs X are reacting to the Bianca narrative

`/last30days war in Iran` (NEWS)의 경우:
> I'm now an expert on the Iran situation. Some things you could ask:
> - What are the realistic escalation scenarios from here?
> - How is this playing differently in US vs international media?
> - What's the economic impact on oil markets so far?

---

## 사용자 응답 대기

통계 요약과 초대를 표시한 후, **멈추고 사용자 응답을 기다리세요.**

---

## 사용자가 응답할 때

**응답을 읽고 의도에 매치:**

- 주제에 대한 **질문**을 하면 → 리서치에서 답변 (새 검색 없이, 프롬프트 없이)
- **더 깊이** 들어가기를 요청하면 → 리서치 결과를 활용하여 상세 설명
- **만들고 싶은** 것을 설명하면 → 완벽한 프롬프트 하나 작성 (아래 참조)
- **프롬프트**를 명시적으로 요청하면 → 완벽한 프롬프트 하나 작성 (아래 참조)

**사용자가 원할 때만 프롬프트를 작성하세요.** "다음에 이란에서 무슨 일이 일어날까"를 물은 사람에게 프롬프트를 강제하지 마세요.

### 프롬프트 작성

사용자가 프롬프트를 원할 때, 리서치 전문성을 활용하여 **단일하고 고도로 맞춤화된 프롬프트**를 작성하세요.

### 중요: 리서치가 권장하는 형식에 맞추기

**리서치가 특정 프롬프트 형식을 사용하라고 하면, 반드시 그 형식을 사용하세요.**

**피해야 할 안티패턴**: 리서치가 "디바이스 스펙이 포함된 JSON 프롬프트 사용"이라고 했는데 평문 산문을 작성. 리서치의 전체 목적을 무효화함.

### 품질 체크리스트 (전달 전 실행):
- [ ] **형식이 리서치와 일치** - 리서치가 JSON/구조화 등을 말했으면 프롬프트가 그 형식
- [ ] 사용자가 만들고 싶다고 한 것을 직접 다룸
- [ ] 리서치에서 발견한 특정 패턴/키워드 사용
- [ ] 수정 없이 바로 붙여넣기 가능 (또는 명확히 표시된 최소 [PLACEHOLDER])
- [ ] TARGET_TOOL에 적절한 길이와 스타일

### 출력 형식:

```
Here's your prompt for {TARGET_TOOL}:

---

[The actual prompt IN THE FORMAT THE RESEARCH RECOMMENDS]

---

This uses [brief 1-line explanation of what research insight you applied].
```

---

## 사용자가 더 많은 옵션을 요청할 경우

대안이나 더 많은 프롬프트를 요청할 때만 2-3개 변형을 제공. 요청하지 않았는데 프롬프트 팩을 쏟아내지 않기.

---

## 각 프롬프트 후: 전문가 모드 유지

프롬프트를 전달한 후 더 작성할지 제안:

> Want another prompt? Just tell me what you're creating next.

---

## 컨텍스트 메모리

이 대화의 나머지 동안 기억:
- **TOPIC**: {topic}
- **TARGET_TOOL**: {tool}
- **KEY PATTERNS**: {배운 상위 3-5개 패턴 나열}
- **RESEARCH FINDINGS**: 리서치의 핵심 사실과 인사이트

**중요: 리서치 완료 후, 이 주제의 전문가가 되었습니다.**

사용자가 후속 질문을 할 때:
- **새 WebSearch를 하지 않기** - 이미 리서치가 있음
- **배운 것에서 답변** - Reddit 스레드, X 포스트, 웹 소스 인용
- **질문을 하면** - 리서치 결과에서 답변
- **프롬프트를 요청하면** - 전문성을 활용하여 작성

사용자가 다른 주제에 대해 명시적으로 질문할 때만 새 리서치 수행.

---

## 출력 요약 푸터 (각 프롬프트 후)

프롬프트 전달 후 마무리:

```
---
📚 Expert in: {TOPIC} for {TARGET_TOOL}
📊 Based on: {n} Reddit threads ({sum} upvotes) + {n} X posts ({sum} likes) + {n} web pages

Want another prompt? Just tell me what you're creating next.
```

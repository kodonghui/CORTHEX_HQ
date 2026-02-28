"""
CORTHEX HQ - 텔레그램 봇 모듈 (P9 리팩토링)

CEO 텔레그램 인터페이스: 명령 핸들러, 모델 선택, AI 명령 라우팅,
토론/브로드캐스트 명령, 웹 응답 전달 등.
arm_server.py에서 ~773줄 분리.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from ws_manager import wm
from state import app_state
from db import (
    save_message, create_task, update_task,
    save_activity_log, save_setting, load_setting, get_today_cost,
)
from config_loader import (
    _log, _diag, logger, _extract_title_summary, KST, AGENTS,
)
try:
    from ai_handler import is_ai_ready
except ImportError:
    def is_ai_ready(): return False

from agent_router import _process_ai_command, _tg_convert_names
from batch_system import _start_batch_chain

# ── 텔레그램 라이브러리 (선택적 로드) ──
_telegram_available = False
try:
    from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )
    _telegram_available = True
    _diag["tg_import"] = True
    _log("[TG] python-telegram-bot 임포트 성공 ✅")
except ImportError as e:
    _diag["tg_import_error"] = str(e)
    _log(f"[TG] python-telegram-bot 임포트 실패 ❌: {e}")


async def _forward_web_response_to_telegram(
    user_command: str, result_data: dict
) -> None:
    """웹 채팅 에이전트 응답을 텔레그램 CEO에게 자동 전달합니다."""
    if not app_state.telegram_app:
        return
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
    if not ceo_id:
        return
    content = result_data.get("content", "")
    if not content:
        return
    handled_by = result_data.get("handled_by", "")
    # 텔레그램 코드명 변환
    tg_who = _tg_convert_names(handled_by) if handled_by else ""
    cost = result_data.get("cost", 0)
    try:
        # 텔레그램 메시지 길이 제한 (4096자)
        cmd_preview = user_command[:60] + ("..." if len(user_command) > 60 else "")
        header = f"💬 [{tg_who}] 웹 응답\n📝 \"{cmd_preview}\"\n─────\n"
        footer = f"\n─────\n💰 ${cost:.4f}" if cost else ""
        max_content = 4096 - len(header) - len(footer) - 50
        if len(content) > max_content:
            content = content[:max_content] + "\n\n... (전체는 웹에서 확인)"
        msg = f"{header}{content}{footer}"
        await app_state.telegram_app.bot.send_message(
            chat_id=int(ceo_id), text=msg,
        )
    except Exception as e:
        _log(f"[TG] 웹 응답 전송 실패: {e}")


async def _start_telegram_bot() -> None:
    """텔레그램 봇을 시작합니다 (FastAPI 이벤트 루프 안에서 실행)."""

    _log(f"[TG] 봇 시작 시도 (_telegram_available={_telegram_available})")

    if not _telegram_available:
        _log("[TG] ❌ 라이브러리 없음 — 건너뜀")
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    _log(f"[TG] 토큰 존재: {bool(token)} (길이: {len(token)})")
    if not token:
        _log("[TG] ❌ 토큰 미설정 — 건너뜀")
        _diag["tg_error"] = "TELEGRAM_BOT_TOKEN 환경변수 없음"
        return

    try:
        _log("[TG] Application 빌드 중...")
        app_state.telegram_app = Application.builder().token(token).build()

        # ── 핸들러 함수들 (라이브러리 설치된 경우에만 정의) ──

        async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            chat_id = update.effective_chat.id
            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
            if not ceo_id:
                logger.info("텔레그램 chat_id 감지: %s", chat_id)
                await update.message.reply_text(
                    f"CORTHEX HQ 텔레그램 봇입니다.\n\n"
                    f"당신의 chat_id: `{chat_id}`\n\n"
                    f"서버 환경변수에 TELEGRAM_CEO_CHAT_ID={chat_id} 를 추가하세요.",
                    parse_mode="Markdown",
                )
                return
            if str(chat_id) != ceo_id:
                await update.message.reply_text("권한이 없습니다.")
                return
            await update.message.reply_text(
                "*CORTHEX HQ 텔레그램 봇*\n\n"
                "CEO 인증 완료.\n"
                "24시간 서버에서 작동 중입니다.\n\n"
                "/help 로 사용법을 확인하세요.",
                parse_mode="Markdown",
            )

        async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            await update.message.reply_text(
                "*CORTHEX HQ 사용법*\n\n"
                "*정보*\n"
                "/agents — 에이전트 목록\n"
                "/health — 서버 상태\n"
                "/status — 배치 진행 현황\n"
                "/budget — 오늘 비용 / 한도 변경\n\n"
                "*AI 명령*\n"
                "/토론 \\[주제\\] — 임원 토론 (2라운드)\n"
                "/심층토론 \\[주제\\] — 심층 임원 토론 (3라운드)\n"
                "/전체 \\[메시지\\] — 29명 동시 지시\n"
                "/순차 \\[작업\\] — 에이전트 릴레이 순차 협업\n"
                "@에이전트명 \\[지시\\] — 특정 에이전트 직접 지시\n\n"
                "*모드 전환*\n"
                "/rt — 실시간 모드 (AI 즉시 답변)\n"
                "/batch — 배치 모드\n\n"
                "*설정*\n"
                "/models — 전원 모델 변경 (3단계 버튼)\n"
                "/pause — AI 처리 중단\n"
                "/resume — AI 처리 재개\n\n"
                "일반 메시지를 보내면 AI가 자동 라우팅합니다.",
                parse_mode="Markdown",
            )

        async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            divisions = {}
            for a in AGENTS:
                div = a.get("division", "기타")
                divisions.setdefault(div, []).append(a)
            lines = ["*CORTHEX HQ 에이전트 목록*\n"]
            div_labels = {
                "secretary": "비서실",
                "leet_master.tech": "기술개발처 (CTO)",
                "leet_master.strategy": "사업기획처 (CSO)",
                "leet_master.legal": "법무·IP처 (CLO)",
                "leet_master.marketing": "마케팅·고객처 (CMO)",
                "finance.investment": "투자분석처 (CIO)",
                "publishing": "출판·기록처 (CPO)",
            }
            for div, agents_list in divisions.items():
                label = div_labels.get(div, div)
                lines.append(f"\n*{label}* ({len(agents_list)}명)")
                for a in agents_list:
                    icon = "👔" if a["role"] == "manager" else "👤"
                    display = a.get("telegram_code", a["name_ko"])
                    lines.append(f"  {icon} {display}")
            lines.append(f"\n총 {len(AGENTS)}명")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            await update.message.reply_text(
                f"*서버 상태*\n\n"
                f"상태: 정상 운영 중\n"
                f"서버: Oracle Cloud (춘천)\n"
                f"에이전트: {len(AGENTS)}명 대기 중\n"
                f"시간: {now} KST",
                parse_mode="Markdown",
            )

        async def cmd_rt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """실시간 모드 전환 (/rt)."""
            if not _is_tg_ceo(update):
                return
            save_setting("tg_mode", "realtime")
            await update.message.reply_text(
                "🔴 *실시간 모드*로 전환했습니다.\n\n"
                "이제 보내시는 메시지에 AI가 즉시 답변합니다.",
                parse_mode="Markdown",
            )

        async def cmd_batch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """배치 모드 전환 (/batch)."""
            if not _is_tg_ceo(update):
                return
            save_setting("tg_mode", "batch")
            await update.message.reply_text(
                "📦 *배치 모드*로 전환했습니다.\n\n"
                "메시지를 접수만 하고, AI 처리는 하지 않습니다.",
                parse_mode="Markdown",
            )

        # ── /status — 배치 진행 목록 ──
        async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            chains = load_setting("batch_chains") or []
            active = [c for c in chains if c.get("status") in ("running", "pending")]
            if not active:
                await update.message.reply_text("현재 진행 중인 배치가 없습니다.")
                return
            lines = [f"*진행 중인 배치 ({len(active)}건)*\n"]
            for c in active[:10]:
                step = c.get("step", "?")
                text_preview = c.get("text", "")[:40]
                chain_id = c.get("chain_id", "?")[:8]
                lines.append(f"• `{chain_id}` | {step} | {text_preview}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        # ── /budget — 오늘 지출 확인/변경 ──
        async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            args = (update.message.text or "").split()
            today_cost = get_today_cost()
            daily_limit = load_setting("daily_budget_usd") or 10
            if len(args) >= 2:
                try:
                    new_limit = float(args[1])
                    save_setting("daily_budget_usd", new_limit)
                    await update.message.reply_text(
                        f"💰 일일 예산을 *${new_limit:.2f}*로 변경했습니다.\n오늘 사용: ${today_cost:.4f}",
                        parse_mode="Markdown",
                    )
                    return
                except ValueError:
                    pass
            pct = (today_cost / daily_limit * 100) if daily_limit > 0 else 0
            await update.message.reply_text(
                f"💰 *오늘 비용 현황*\n\n"
                f"사용: ${today_cost:.4f}\n"
                f"한도: ${daily_limit:.2f}\n"
                f"사용률: {pct:.1f}%\n\n"
                f"한도 변경: `/budget 15` (15달러로 변경)",
                parse_mode="Markdown",
            )

        # ── /pause, /resume — AI 처리 중단/재개 ──
        async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            save_setting("ai_paused", True)
            await update.message.reply_text("⏸ *AI 처리를 일시 중단*했습니다.\n\n`/resume`으로 재개하세요.", parse_mode="Markdown")

        async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            save_setting("ai_paused", False)
            await update.message.reply_text("▶️ *AI 처리를 재개*했습니다.", parse_mode="Markdown")

        # ── /models — 3단계 인라인 버튼으로 모델 변경 ──
        # 프로바이더별 모델 목록 (코드 내 _MODEL_CATALOG과 동기화)
        _TG_MODELS = {
            "Anthropic": [
                ("claude-opus-4-6", "Opus 4.6", ["xhigh", "high", "low", "없음"]),
                ("claude-sonnet-4-6", "Sonnet 4.6", ["high", "medium", "low", "없음"]),
                ("claude-haiku-4-5-20251001", "Claude Haiku 4.5", []),
            ],
            "OpenAI": [
                ("gpt-5.2-pro", "GPT-5.2 Pro", ["xhigh", "high", "medium", "없음"]),
                ("gpt-5.2", "GPT-5.2", ["xhigh", "high", "medium", "low", "없음"]),
                ("gpt-5", "GPT-5", ["xhigh", "high", "low", "없음"]),
                ("gpt-5-mini", "GPT-5 Mini", []),
            ],
            "Google": [
                ("gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview", ["high", "low", "없음"]),
                ("gemini-2.5-pro", "Gemini 2.5 Pro", ["high", "low", "없음"]),
                ("gemini-2.5-flash", "Gemini 2.5 Flash", []),
            ],
        }

        async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            current = load_setting("global_model_override") or {}
            cur_model = current.get("model", "없음")
            cur_reason = current.get("reasoning", "없음")
            buttons = [
                [InlineKeyboardButton("🟣 Anthropic", callback_data="mdl_p_Anthropic")],
                [InlineKeyboardButton("🟢 OpenAI", callback_data="mdl_p_OpenAI")],
                [InlineKeyboardButton("🔵 Google", callback_data="mdl_p_Google")],
            ]
            await update.message.reply_text(
                f"*전원 모델 변경*\n\n현재: `{cur_model}` (추론: {cur_reason})\n\n프로바이더를 선택하세요:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

        async def models_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            query = update.callback_query
            await query.answer()
            data = query.data

            # 1단계: 프로바이더 선택 → 모델 목록 표시
            if data.startswith("mdl_p_"):
                provider = data[6:]
                models_list = _TG_MODELS.get(provider, [])
                buttons = []
                for model_id, label, _ in models_list:
                    buttons.append([InlineKeyboardButton(label, callback_data=f"mdl_m_{model_id}")])
                buttons.append([InlineKeyboardButton("« 뒤로", callback_data="mdl_back")])
                await query.edit_message_text(
                    f"*{provider}* 모델을 선택하세요:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )

            # 2단계: 모델 선택 → 추론 강도 표시 (또는 바로 저장)
            elif data.startswith("mdl_m_"):
                model_id = data[6:]
                # 모델의 추론 레벨 찾기
                reasoning_levels = []
                for provider, models_list in _TG_MODELS.items():
                    for mid, label, levels in models_list:
                        if mid == model_id:
                            reasoning_levels = levels
                            break

                if not reasoning_levels:
                    # 추론 없음 → 바로 저장 (웹과 동일한 키 사용 → 동기화)
                    save_setting("model_mode", "manual")
                    save_setting("model_override", model_id)
                    save_setting("global_model_override", {"model": model_id, "reasoning": "없음"})
                    await query.edit_message_text(f"✅ 전원 모델을 `{model_id}` 으로 변경했습니다.\n(추론: 없음)", parse_mode="Markdown")
                else:
                    # 추론 레벨 선택 버튼
                    context.user_data["pending_model"] = model_id
                    buttons = []
                    for level in reasoning_levels:
                        buttons.append([InlineKeyboardButton(level, callback_data=f"mdl_r_{level}")])
                    buttons.append([InlineKeyboardButton("« 뒤로", callback_data="mdl_back")])
                    await query.edit_message_text(
                        f"*{model_id}*\n추론 강도를 선택하세요:",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )

            # 3단계: 추론 강도 선택 → 저장
            elif data.startswith("mdl_r_"):
                level = data[6:]
                model_id = context.user_data.get("pending_model", "")
                if model_id:
                    # 웹과 동일한 키 사용 → 동기화
                    save_setting("model_mode", "manual")
                    save_setting("model_override", model_id)
                    save_setting("global_model_override", {"model": model_id, "reasoning": level})
                    await query.edit_message_text(
                        f"✅ 전원 모델을 `{model_id}` 으로 변경했습니다.\n(추론: {level})",
                        parse_mode="Markdown",
                    )
                else:
                    await query.edit_message_text("❌ 모델 정보가 없습니다. /models를 다시 시도하세요.")

            # 뒤로가기
            elif data == "mdl_back":
                current = load_setting("global_model_override") or {}
                cur_model = current.get("model", "없음")
                cur_reason = current.get("reasoning", "없음")
                buttons = [
                    [InlineKeyboardButton("🟣 Anthropic", callback_data="mdl_p_Anthropic")],
                    [InlineKeyboardButton("🟢 OpenAI", callback_data="mdl_p_OpenAI")],
                    [InlineKeyboardButton("🔵 Google", callback_data="mdl_p_Google")],
                ]
                await query.edit_message_text(
                    f"*전원 모델 변경*\n\n현재: `{cur_model}` (추론: {cur_reason})\n\n프로바이더를 선택하세요:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )

        # ── 장기 실행 명령 공통 헬퍼 (토론/전체/순차 등 2~10분 소요 명령) ──
        async def _tg_long_command(update_obj, task_text, target_agent_id=None):
            """백그라운드로 실행하고 완료 시 텔레그램으로 결과 전송."""
            chat_id = str(update_obj.effective_chat.id)
            task = create_task(task_text, source="telegram")
            cmd_name = task_text.split()[0]
            await update_obj.message.reply_text(
                f"⏳ *{cmd_name}* 시작 (#{task['task_id']})\n"
                f"완료 시 결과를 보내드립니다. (2~10분 소요)",
                parse_mode="Markdown",
            )

            async def _bg(t, tid, cid):
                try:
                    update_task(tid, status="running")
                    result = await _process_ai_command(t, tid, target_agent_id=target_agent_id)
                    content = result.get("content", result.get("error", "결과 없음"))
                    cost = result.get("cost_usd", result.get("total_cost_usd", 0))
                    tg_agent_id = result.get("agent_id", "chief_of_staff")
                    if "error" in result:
                        update_task(tid, status="failed",
                                    result_summary=str(result.get("error", ""))[:200],
                                    success=0, agent_id=tg_agent_id)
                    else:
                        update_task(tid, status="completed",
                                    result_summary=_extract_title_summary(content or ""),
                                    success=1, cost_usd=cost, agent_id=tg_agent_id)
                    if len(content) > 3900:
                        content = content[:3900] + "\n\n... (결과가 잘렸습니다. 웹에서 전체 확인)"
                    await app_state.telegram_app.bot.send_message(
                        chat_id=int(cid),
                        text=f"{content}\n\n─────\n💰 ${cost:.4f}",
                    )
                except Exception as e:
                    update_task(tid, status="failed",
                                result_summary=str(e)[:200], success=0)
                    try:
                        await app_state.telegram_app.bot.send_message(chat_id=int(cid), text=f"❌ 오류: {e}")
                    except Exception as e2:
                        logger.debug("TG 오류 메시지 전송 실패: %s", e2)

            asyncio.create_task(_bg(task_text, task["task_id"], chat_id))

        # ── /토론 [주제] — 임원 토론 (2라운드) ──
        async def cmd_debate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            topic = " ".join(context.args) if context.args else ""
            if not topic:
                await update.message.reply_text(
                    "사용법: `/토론 [주제]`\n예: `/토론 AI가 인간의 일자리를 대체할까?`",
                    parse_mode="Markdown",
                )
                return
            await _tg_long_command(update, f"/토론 {topic}")

        # ── /심층토론 [주제] — 심층 임원 토론 (3라운드) ──
        async def cmd_deep_debate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            topic = " ".join(context.args) if context.args else ""
            if not topic:
                await update.message.reply_text(
                    "사용법: `/심층토론 [주제]`\n예: `/심층토론 CORTHEX 2026 전략 방향`",
                    parse_mode="Markdown",
                )
                return
            await _tg_long_command(update, f"/심층토론 {topic}")

        # ── /전체 [메시지] — 29명 동시 브로드캐스트 ──
        async def cmd_broadcast_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            message = " ".join(context.args) if context.args else "전체 출석 보고"
            await _tg_long_command(update, f"/전체 {message}")

        # ── /순차 [메시지] — 에이전트 릴레이 순차 협업 ──
        async def cmd_sequential(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            message = " ".join(context.args) if context.args else ""
            if not message:
                await update.message.reply_text(
                    "사용법: `/순차 [작업]`\n예: `/순차 CORTHEX 웹사이트 기술→보안→사업성 분석`",
                    parse_mode="Markdown",
                )
                return
            await _tg_long_command(update, f"/순차 {message}")

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            text = update.message.text.strip()
            if not text:
                return

            # @에이전트명 직접 지시 파싱 (예: "@cto_manager 기술 분석해줘")
            tg_target_agent_id = None
            if text.startswith("@"):
                parts = text.split(None, 1)
                if len(parts) >= 2:
                    mention = parts[0][1:]
                    mention_lower = mention.lower()
                    for a in AGENTS:
                        aid = a.get("agent_id", "").lower()
                        aname = a.get("name_ko", "")
                        tcode = a.get("telegram_code", "").lstrip("@")
                        if aid == mention_lower or aid.startswith(mention_lower) or mention_lower in aname.lower() or mention == tcode:
                            tg_target_agent_id = a["agent_id"]
                            text = parts[1]
                            break
                    if not tg_target_agent_id:
                        await update.message.reply_text(
                            f"❌ `@{parts[0][1:]}` 에이전트를 찾을 수 없습니다.\n"
                            f"/agents 로 에이전트 목록을 확인하세요.",
                            parse_mode="Markdown",
                        )
                        return

            # 한국어 명령어 처리 (텔레그램 CommandHandler는 영어만 지원하므로 텍스트로 처리)
            if text in ("실시간", "/실시간"):
                save_setting("tg_mode", "realtime")
                await update.message.reply_text(
                    "🔴 *실시간 모드*로 전환했습니다.\n\n"
                    "이제 보내시는 메시지에 AI가 즉시 답변합니다.",
                    parse_mode="Markdown",
                )
                return
            if text in ("배치", "/배치"):
                save_setting("tg_mode", "batch")
                await update.message.reply_text(
                    "📦 *배치 모드*로 전환했습니다.\n\n"
                    "메시지를 접수만 하고, AI 처리는 하지 않습니다.",
                    parse_mode="Markdown",
                )
                return

            # 한국어 AI 명령어 (/토론, /심층토론, /전체, /순차)
            if text.startswith("/토론 ") or text == "/토론":
                topic = text[len("/토론"):].strip()
                if not topic:
                    await update.message.reply_text(
                        "사용법: /토론 [주제]\n예: /토론 AI가 인간의 일자리를 대체할까?")
                    return
                await _tg_long_command(update, f"/토론 {topic}")
                return
            if text.startswith("/심층토론 ") or text == "/심층토론":
                topic = text[len("/심층토론"):].strip()
                if not topic:
                    await update.message.reply_text(
                        "사용법: /심층토론 [주제]\n예: /심층토론 CORTHEX 2026 전략 방향")
                    return
                await _tg_long_command(update, f"/심층토론 {topic}")
                return
            if text.startswith("/전체 ") or text == "/전체":
                message_text = text[len("/전체"):].strip() or "전체 출석 보고"
                await _tg_long_command(update, f"/전체 {message_text}")
                return
            if text.startswith("/순차 ") or text == "/순차":
                message_text = text[len("/순차"):].strip()
                if not message_text:
                    await update.message.reply_text(
                        "사용법: /순차 [작업]\n예: /순차 CORTHEX 웹사이트 기술→보안→사업성 분석")
                    return
                await _tg_long_command(update, f"/순차 {message_text}")
                return

            chat_id = str(update.effective_chat.id)
            # DB에 메시지 + 작업 저장
            task = create_task(text, source="telegram")
            save_message(text, source="telegram", chat_id=chat_id,
                         task_id=task["task_id"])

            # AI 일시 중단 체크
            if load_setting("ai_paused"):
                await update.message.reply_text("⏸ AI 처리가 일시 중단된 상태입니다.\n`/resume`으로 재개하세요.", parse_mode="Markdown")
                return

            # 모드 확인
            mode = load_setting("tg_mode") or "realtime"
            now = datetime.now(KST).strftime("%H:%M")
            result = {}  # 웹소켓 브로드캐스트용

            if mode == "realtime" and is_ai_ready():
                # 실시간 모드: AI가 답변
                update_task(task["task_id"], status="running")
                await update.message.reply_text(f"⏳ 처리 중... (#{task['task_id']})")

                result = await _process_ai_command(text, task["task_id"], target_agent_id=tg_target_agent_id)

                tg_rt_agent_id = result.get("agent_id", "chief_of_staff")
                if "error" in result:
                    update_task(task["task_id"], status="failed",
                                result_summary=str(result.get("error", ""))[:200],
                                success=0, agent_id=tg_rt_agent_id)
                    await update.message.reply_text(f"❌ {result['error']}")
                else:
                    content = result.get("content", "")
                    cost = result.get("cost_usd", 0)
                    model = result.get("model", "")
                    # 텔레그램 메시지 길이 제한 (4096자)
                    if len(content) > 3900:
                        content = content[:3900] + "\n\n... (결과가 잘렸습니다. 웹에서 전체 확인)"
                    delegation = result.get("delegation", "")
                    model_short = model.split("-")[1] if "-" in model else model
                    # 담당자 표시: 팀장 이름 또는 비서실장
                    footer_who = delegation if delegation else "비서실장"
                    update_task(task["task_id"], status="completed",
                                result_summary=_extract_title_summary(content or ""),
                                success=1, cost_usd=cost,
                                time_seconds=result.get("time_seconds", 0),
                                agent_id=tg_rt_agent_id)
                    await update.message.reply_text(
                        f"{content}\n\n"
                        f"─────\n"
                        f"👤 {footer_who} | 💰 ${cost:.4f} | 🤖 {model_short}",
                        parse_mode=None,
                    )
            elif mode == "batch" and is_ai_ready():
                # 배치 모드 + AI 연결됨 → 실제 배치 체인 실행
                update_task(task["task_id"], status="pending",
                            result_summary="📦 [배치 체인] 시작 중...")
                await update.message.reply_text(
                    f"📦 배치 접수 완료 (#{task['task_id']})\n"
                    f"배치 체인이 백그라운드에서 실행됩니다.\n"
                    f"완료 시 결과를 여기로 보내드리겠습니다.",
                    parse_mode=None,
                )

                # 배치 체인을 백그라운드로 실행
                async def _tg_run_batch(text_arg, task_id_arg, chat_id_arg):
                    try:
                        chain_result = await _start_batch_chain(text_arg, task_id_arg)
                        if "error" in chain_result and app_state.telegram_app:
                            try:
                                await app_state.telegram_app.bot.send_message(
                                    chat_id=int(chat_id_arg),
                                    text=f"❌ 배치 시작 실패: {chain_result['error']}",
                                )
                            except Exception as e2:
                                logger.debug("TG 배치 실패 전송 실패: %s", e2)
                    except Exception as e:
                        _log(f"[TG] 배치 체인 오류: {e}")

                asyncio.create_task(_tg_run_batch(text, task["task_id"], chat_id))
            else:
                # AI 미연결 → 접수만
                update_task(task["task_id"], status="completed",
                            result_summary="AI 미연결 — 접수만 완료",
                            success=1, time_seconds=0.1)
                await update.message.reply_text(
                    f"📋 접수했습니다. ({now})\n"
                    f"작업 ID: `{task['task_id']}`\n"
                    f"상태: AI 미연결",
                    parse_mode="Markdown",
                )

            # 활동 로그 저장 + 웹소켓 브로드캐스트 (웹 채팅에도 대화 표시)
            log_entry = save_activity_log(
                "chief_of_staff",
                f"[텔레그램] CEO 지시: {text[:50]}{'...' if len(text) > 50 else ''} (#{task['task_id']})",
            )
            await wm.broadcast_multi([
                ("task_accepted", task),
                ("activity_log", log_entry),
                ("telegram_message", {"type": "user", "text": text, "source": "telegram"}),
            ])
            if "error" not in result:
                await wm.broadcast("result", {
                    "content": result.get("content", ""),
                    "sender_id": result.get("agent_id", "chief_of_staff"),
                    "handled_by": result.get("handled_by", "비서실장"),
                    "delegation": result.get("delegation", ""),
                    "time_seconds": result.get("time_seconds", 0),
                    "cost": result.get("total_cost_usd", result.get("cost_usd", 0)),
                    "model": result.get("model", ""),
                    "routing_method": result.get("routing_method", ""),
                    "source": "telegram",
                })
            else:
                await wm.broadcast("result", {
                    "content": f"❌ {result['error']}",
                    "sender_id": "chief_of_staff",
                    "handled_by": "비서실장",
                    "time_seconds": 0, "cost": 0,
                    "source": "telegram",
                })

        def _is_tg_ceo(update: Update) -> bool:
            if not update.effective_chat or not update.message:
                return False
            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
            if not ceo_id:
                return False
            if str(update.effective_chat.id) != ceo_id:
                asyncio.create_task(update.message.reply_text("권한이 없습니다."))
                return False
            return True

        # ── 글로벌 에러 핸들러 (핸들러 예외 로깅) ──
        async def _tg_error_handler(update, context):
            _log(f"[TG] ❌ 핸들러 오류: {context.error}")
            import traceback
            _diag["tg_last_error"] = str(context.error)
            _diag["tg_error_time"] = datetime.now(KST).isoformat()
            traceback.print_exc()
        app_state.telegram_app.add_error_handler(_tg_error_handler)

        # 핸들러 등록
        app_state.telegram_app.add_handler(CommandHandler("start", cmd_start))
        app_state.telegram_app.add_handler(CommandHandler("help", cmd_help))
        app_state.telegram_app.add_handler(CommandHandler("agents", cmd_agents))
        app_state.telegram_app.add_handler(CommandHandler("health", cmd_health))
        app_state.telegram_app.add_handler(CommandHandler("rt", cmd_rt))
        app_state.telegram_app.add_handler(CommandHandler("batch", cmd_batch))
        app_state.telegram_app.add_handler(CommandHandler("status", cmd_status))
        app_state.telegram_app.add_handler(CommandHandler("budget", cmd_budget))
        app_state.telegram_app.add_handler(CommandHandler("pause", cmd_pause))
        app_state.telegram_app.add_handler(CommandHandler("resume", cmd_resume))
        app_state.telegram_app.add_handler(CommandHandler("models", cmd_models))
        app_state.telegram_app.add_handler(CallbackQueryHandler(models_callback, pattern=r"^mdl_"))
        # 한국어 명령(/토론, /심층토론, /전체, /순차)은 handle_message에서 텍스트로 처리
        # (Telegram CommandHandler는 라틴 소문자+숫자+밑줄만 허용)
        app_state.telegram_app.add_handler(
            MessageHandler(filters.TEXT, handle_message)
        )

        _log("[TG] 핸들러 등록 완료, initialize()...")
        await app_state.telegram_app.initialize()

        # 토큰 유효성 사전 확인 (getMe)
        try:
            me = await app_state.telegram_app.bot.get_me()
            _diag["tg_bot_username"] = me.username
            _diag["tg_bot_id"] = me.id
            _log(f"[TG] ✅ 봇 인증 성공: @{me.username} (ID: {me.id})")
        except Exception as me_err:
            _log(f"[TG] ❌ 봇 토큰 무효 또는 네트워크 오류: {me_err}")
            _diag["tg_error"] = f"getMe 실패: {me_err}"
            app_state.telegram_app = None
            return

        # webhook 충돌 방지: polling 시작 전 webhook 강제 삭제
        for attempt in range(3):
            try:
                await app_state.telegram_app.bot.delete_webhook(drop_pending_updates=False)
                _log("[TG] webhook 삭제 완료 (polling 충돌 방지)")
                break
            except Exception as we:
                _log(f"[TG] webhook 삭제 시도 {attempt+1}/3 실패: {we}")
                if attempt < 2:
                    await asyncio.sleep(1)

        # 봇 명령어 메뉴 설정 (initialize 이후에 API 호출 가능)
        # NOTE: Telegram BotCommand는 라틴 소문자+숫자+밑줄만 허용 (한국어 불가)
        # 한국어 명령(/토론, /심층토론, /전체, /순차)은 CommandHandler로만 동작
        try:
            await app_state.telegram_app.bot.set_my_commands([
                BotCommand("start", "봇 시작"),
                BotCommand("help", "사용법 (한국어 명령 포함)"),
                BotCommand("agents", "에이전트 목록"),
                BotCommand("health", "서버 상태"),
                BotCommand("rt", "실시간 모드"),
                BotCommand("batch", "배치 모드"),
                BotCommand("models", "전원 모델 변경"),
                BotCommand("status", "배치 진행 상태"),
                BotCommand("budget", "오늘 비용 / 한도 변경"),
                BotCommand("pause", "AI 처리 중단"),
                BotCommand("resume", "AI 처리 재개"),
            ])
        except Exception as cmd_err:
            _log(f"[TG] 명령어 메뉴 설정 건너뜀 (봇은 정상 동작): {cmd_err}")

        _log("[TG] start()...")
        await app_state.telegram_app.start()
        _log("[TG] polling 시작...")
        # drop_pending_updates=True: 이전 쌓인 메시지 무시하고 새 메시지만 처리
        await app_state.telegram_app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )

        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        _diag["tg_started"] = True
        _log(f"[TG] ✅ 봇 시작 완료! (CEO: {ceo_id or '미설정'})")
    except Exception as e:
        _diag["tg_error"] = str(e)
        _log(f"[TG] ❌ 봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        app_state.telegram_app = None


async def _stop_telegram_bot() -> None:
    """텔레그램 봇을 종료합니다."""

    if app_state.telegram_app:
        try:
            await app_state.telegram_app.updater.stop()
            await app_state.telegram_app.stop()
            await app_state.telegram_app.shutdown()
            logger.info("텔레그램 봇 종료 완료")
        except Exception as e:
            logger.warning("텔레그램 봇 종료 중 오류: %s", e)
        app_state.telegram_app = None

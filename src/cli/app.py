"""
CORTHEX HQ - Rich Terminal CLI Application.

CEO가 한국어로 명령을 내리면, 에이전트 조직이 자동으로 업무를 처리합니다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from src.core.budget import BudgetManager
from src.core.context import SharedContext
from src.core.healthcheck import run_healthcheck, HealthStatus
from src.core.message import Message, MessageType
from src.core.orchestrator import Orchestrator
from src.core.performance import build_performance_report
from src.core.preset import PresetManager
from src.core.registry import AgentRegistry
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.openai_provider import OpenAIProvider
from src.llm.router import ModelRouter
from src.tools.pool import ToolPool

logger = logging.getLogger("corthex.cli")

_BANNER = r"""
   ██████╗ ██████╗ ██████╗ ████████╗██╗  ██╗███████╗██╗  ██╗
  ██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██║  ██║██╔════╝╚██╗██╔╝
  ██║     ██║   ██║██████╔╝   ██║   ███████║█████╗   ╚███╔╝
  ██║     ██║   ██║██╔══██╗   ██║   ██╔══██║██╔══╝   ██╔██╗
  ╚██████╗╚██████╔╝██║  ██║   ██║   ██║  ██║███████╗██╔╝ ██╗
   ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
"""


class CorthexCLI:
    """Rich terminal interface for CEO interaction with CORTHEX HQ."""

    def __init__(self) -> None:
        self.console = Console()
        self.config_dir = Path(__file__).resolve().parent.parent.parent / "config"
        self.orchestrator: Orchestrator | None = None
        self.model_router: ModelRouter | None = None
        self.registry: AgentRegistry | None = None
        self.context: SharedContext | None = None
        self.budget_manager: BudgetManager | None = None
        self.preset_manager: PresetManager | None = None
        # Live streaming state
        self._active_agents: dict[str, str] = {}  # agent_id -> status text

    async def run(self) -> None:
        """Main CLI loop."""
        self._show_banner()

        self.orchestrator, self.model_router, self.registry, self.context = await self._bootstrap()
        self._show_org_chart()
        self.console.print()
        self.console.print("[bold green]CORTHEX HQ 시스템 준비 완료.[/bold green]")
        self.console.print("[dim]명령을 입력하세요. '도움말' 입력 시 사용법 안내.[/dim]\n")

        while True:
            try:
                user_input = Prompt.ask("[bold cyan]CEO[/bold cyan]")

                if not user_input.strip():
                    continue

                cmd = user_input.strip()
                cmd_lower = cmd.lower()

                if cmd_lower in ("exit", "quit", "종료"):
                    self._show_cost_summary()
                    self.console.print("[yellow]CORTHEX HQ를 종료합니다.[/yellow]")
                    break
                if cmd_lower in ("help", "도움말"):
                    self._show_help()
                    continue
                if cmd_lower in ("cost", "비용"):
                    self._show_cost_summary()
                    continue
                if cmd_lower in ("org", "조직도"):
                    self._show_org_chart()
                    continue
                if cmd_lower in ("health", "헬스체크"):
                    await self._show_healthcheck()
                    continue
                if cmd_lower in ("performance", "성과"):
                    self._show_performance()
                    continue
                if cmd_lower in ("budget", "예산"):
                    self._show_budget()
                    continue

                # --- Preset commands ---
                if cmd.startswith("프리셋 ") or cmd.startswith("preset "):
                    self._handle_preset_command(cmd)
                    continue
                if cmd_lower in ("프리셋 목록", "preset list", "프리셋", "preset"):
                    self._show_presets()
                    continue

                # Check if input matches a preset name
                if self.preset_manager:
                    resolved = self.preset_manager.resolve(cmd)
                    if resolved:
                        self.console.print(
                            f"[dim]프리셋 '{cmd}' 실행 → {resolved}[/dim]"
                        )
                        user_input = resolved

                # Process command with live streaming
                result = await self._process_with_streaming(user_input)

                # Display result
                self._display_result(result)

                # Budget warning after each command
                if self.budget_manager and self.model_router:
                    warning = self.budget_manager.check_warning(
                        self.model_router.cost_tracker
                    )
                    if warning:
                        self.console.print(f"[bold yellow]  {warning}[/bold yellow]")

            except KeyboardInterrupt:
                self.console.print("\n[yellow]중단됨. '종료' 입력 시 안전하게 종료합니다.[/yellow]")
            except Exception as e:
                self.console.print(f"[red]오류: {e}[/red]")

    async def _process_with_streaming(self, user_input: str) -> object:
        """Process command with real-time agent activity display."""
        self._active_agents.clear()

        # Set up streaming callback
        def on_stream_message(msg: Message) -> None:
            if not self.registry:
                return
            if msg.type == MessageType.TASK_REQUEST:
                receiver_id = msg.receiver_id
                try:
                    agent = self.registry.get_agent(receiver_id)
                    name = agent.config.name_ko
                except Exception:
                    name = receiver_id
                self._active_agents[receiver_id] = f"[green]▶[/green] {name} 작업 중..."
            elif msg.type == MessageType.TASK_RESULT:
                sender_id = msg.sender_id
                try:
                    agent = self.registry.get_agent(sender_id)
                    name = agent.config.name_ko
                except Exception:
                    name = sender_id
                self._active_agents[sender_id] = f"[dim]✓ {name} 완료[/dim]"

        # Temporarily set our streaming callback
        old_callback = self.context._status_callback if self.context else None
        if self.context:
            def combined_callback(msg: Message) -> None:
                on_stream_message(msg)
                if old_callback:
                    old_callback(msg)
            self.context.set_status_callback(combined_callback)

        try:
            with Live(
                self._build_stream_panel(),
                console=self.console,
                refresh_per_second=4,
                transient=True,
            ) as live:
                # Run command in background, update live display periodically
                task = asyncio.create_task(self.orchestrator.process_command(user_input))

                while not task.done():
                    live.update(self._build_stream_panel())
                    await asyncio.sleep(0.25)

                result = await task
                return result
        finally:
            # Restore original callback
            if self.context:
                self.context.set_status_callback(old_callback)

    def _build_stream_panel(self) -> Panel:
        """Build a live-updating panel showing active agents."""
        if not self._active_agents:
            text = Text("에이전트 조직이 업무를 처리하고 있습니다...", style="bold green")
        else:
            lines = []
            for agent_id, status in self._active_agents.items():
                lines.append(status)
            text = Text.from_markup("\n".join(lines))

        return Panel(
            text,
            title="[bold yellow]작업 진행 상황[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        )

    async def _bootstrap(self) -> tuple[Orchestrator, ModelRouter, AgentRegistry, SharedContext]:
        """Initialize all components from config files."""
        self.console.print("[dim]설정 파일 로딩 중...[/dim]")

        # Load YAML configs
        agents_cfg = yaml.safe_load(
            (self.config_dir / "agents.yaml").read_text(encoding="utf-8")
        )
        tools_cfg = yaml.safe_load(
            (self.config_dir / "tools.yaml").read_text(encoding="utf-8")
        )

        # Build LLM providers
        openai_key = os.getenv("OPENAI_API_KEY", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

        openai_provider = OpenAIProvider(api_key=openai_key) if openai_key else None
        anthropic_provider = AnthropicProvider(api_key=anthropic_key) if anthropic_key else None

        if not openai_provider and not anthropic_provider:
            self.console.print(
                "[bold red]오류: API 키가 설정되지 않았습니다![/bold red]\n"
                "[yellow].env 파일에 OPENAI_API_KEY 또는 ANTHROPIC_API_KEY를 설정하세요.\n"
                "cp .env.example .env  후 키를 입력하세요.[/yellow]"
            )
            raise SystemExit(1)

        model_router = ModelRouter(
            openai_provider=openai_provider,
            anthropic_provider=anthropic_provider,
        )

        # Build tool pool
        tool_pool = ToolPool(model_router)
        tool_pool.build_from_config(tools_cfg)
        self.console.print(f"  [green]>[/green] 도구 {len(tool_pool.list_tools())}개 로드")

        # Build agent registry
        context = SharedContext()
        registry = AgentRegistry()
        registry.build_from_config(agents_cfg, model_router, tool_pool, context)
        context.set_registry(registry)
        self.console.print(f"  [green]>[/green] 에이전트 {registry.agent_count}개 로드")

        # Build orchestrator
        orchestrator = Orchestrator(registry, model_router)
        self.console.print("  [green]>[/green] 오케스트레이터 초기화 완료")

        # Build budget manager
        self.budget_manager = BudgetManager(self.config_dir / "budget.yaml")
        self.console.print("  [green]>[/green] 예산 관리 로드")

        # Build preset manager
        self.preset_manager = PresetManager(self.config_dir / "presets.yaml")
        preset_count = len(self.preset_manager.list_all())
        self.console.print(f"  [green]>[/green] 프리셋 {preset_count}개 로드")

        return orchestrator, model_router, registry, context

    def _show_banner(self) -> None:
        panel = Panel(
            f"[bold white]{_BANNER}[/bold white]\n"
            "[dim]AI Agent Corporation Headquarters v0.4.0[/dim]",
            title="[bold yellow]CORTHEX HQ[/bold yellow]",
            border_style="bright_blue",
        )
        self.console.print(panel)

    def _show_org_chart(self) -> None:
        tree = Tree("[bold white]CEO (동희 님)[/bold white]")

        # 비서실장 (총괄 오케스트레이터)
        sec = tree.add("[yellow]비서실장 (Chief of Staff)[/yellow] ← 총괄 오케스트레이터")
        sec.add("보고 요약 Worker")
        sec.add("일정/미결 추적 Worker")
        sec.add("사업부 간 정보 중계 Worker")

        # LEET Master 본부
        leet = tree.add("[cyan]LEET Master 본부[/cyan] (제품 개발)")

        tech = leet.add("[green]기술개발처 (CTO)[/green]")
        for s in ["프론트엔드", "백엔드/API", "DB/인프라", "AI 모델"]:
            tech.add(s)

        strategy = leet.add("[green]사업기획처 (CSO)[/green]")
        for s in ["시장조사", "사업계획서", "재무모델링"]:
            strategy.add(s)

        legal = leet.add("[green]법무·IP처 (CLO)[/green]")
        for s in ["저작권", "특허/약관"]:
            legal.add(s)

        marketing = leet.add("[green]마케팅·고객처 (CMO)[/green]")
        for s in ["설문/리서치", "콘텐츠", "커뮤니티"]:
            marketing.add(s)

        # 투자분석 본부
        invest_hq = tree.add("[magenta]투자분석 본부[/magenta] (주식/금융 투자)")
        invest = invest_hq.add("[green]투자분석처 (CIO)[/green]")
        for s in ["시황분석 [병렬]", "종목분석 [병렬]", "기술적분석 [병렬]", "리스크관리 [순차]"]:
            invest.add(s)

        # Tool Pool
        tools = tree.add("[red]AgentTool Pool[/red]")
        for t in ["변리사", "세무사", "디자이너", "번역가", "웹검색"]:
            tools.add(t + " Tool")

        self.console.print(Panel(tree, title="[bold]조직도[/bold]", border_style="bright_blue"))

    def _display_result(self, result) -> None:
        if result.success:
            content = str(result.result_data or result.summary)
            try:
                panel_content = Markdown(content)
            except Exception:
                panel_content = content

            self.console.print(Panel(
                panel_content,
                title=f"[green]결과[/green] | {result.sender_id} | {result.execution_time_seconds:.1f}초",
                border_style="green",
                padding=(1, 2),
            ))
        else:
            self.console.print(Panel(
                str(result.result_data),
                title="[red]오류[/red]",
                border_style="red",
            ))

    def _show_cost_summary(self) -> None:
        if not self.model_router:
            return

        tracker = self.model_router.cost_tracker
        summary = tracker.summary_by_model()

        if not summary:
            self.console.print("[dim]아직 API 호출 기록이 없습니다.[/dim]")
            return

        table = Table(title="API 비용 요약")
        table.add_column("모델", style="cyan")
        table.add_column("호출 수", justify="right")
        table.add_column("입력 토큰", justify="right")
        table.add_column("출력 토큰", justify="right")
        table.add_column("비용 (USD)", justify="right", style="green")

        for model, data in summary.items():
            table.add_row(
                model,
                str(data["calls"]),
                f"{data['input_tokens']:,}",
                f"{data['output_tokens']:,}",
                f"${data['cost_usd']:.4f}",
            )

        table.add_section()
        table.add_row(
            "[bold]합계[/bold]", str(tracker.total_calls), "", "",
            f"[bold]${tracker.total_cost:.4f}[/bold]",
        )
        self.console.print(table)

    def _show_budget(self) -> None:
        if not self.budget_manager or not self.model_router:
            self.console.print("[dim]시스템이 아직 초기화되지 않았습니다.[/dim]")
            return

        status = self.budget_manager.get_status(self.model_router.cost_tracker)

        table = Table(title="토큰 예산 현황")
        table.add_column("구분", style="cyan")
        table.add_column("한도", justify="right")
        table.add_column("사용", justify="right")
        table.add_column("잔여", justify="right", style="green")
        table.add_column("소진율", justify="right")

        # Daily
        daily_style = "[red]" if status.daily_exceeded else "[yellow]" if status.daily_warning else "[green]"
        table.add_row(
            "일일",
            f"${status.daily_limit:.2f}",
            f"${status.daily_used:.4f}",
            f"${status.daily_remaining:.4f}",
            f"{daily_style}{status.daily_pct:.1f}%[/]",
        )

        # Monthly
        monthly_style = "[red]" if status.monthly_exceeded else "[yellow]" if status.monthly_warning else "[green]"
        table.add_row(
            "월간",
            f"${status.monthly_limit:.2f}",
            f"${status.monthly_used:.4f}",
            f"${status.monthly_remaining:.4f}",
            f"{monthly_style}{status.monthly_pct:.1f}%[/]",
        )

        self.console.print(table)
        self.console.print(
            f"[dim]경고 임계값: {status.warn_threshold_pct}% | "
            f"설정 파일: config/budget.yaml[/dim]"
        )

    def _handle_preset_command(self, cmd: str) -> None:
        """Handle preset sub-commands: 저장/삭제/목록."""
        if not self.preset_manager:
            self.console.print("[dim]프리셋 매니저가 초기화되지 않았습니다.[/dim]")
            return

        # Remove prefix
        for prefix in ("프리셋 ", "preset "):
            if cmd.startswith(prefix):
                rest = cmd[len(prefix):].strip()
                break
        else:
            rest = cmd

        if rest.startswith("저장 ") or rest.startswith("save "):
            # 프리셋 저장 <이름> <명령>
            parts = rest.split(maxsplit=2)
            if len(parts) < 3:
                self.console.print("[yellow]사용법: 프리셋 저장 <이름> <명령>[/yellow]")
                return
            name, command = parts[1], parts[2]
            self.preset_manager.add(name, command)
            self.console.print(f"[green]프리셋 '{name}' 저장 완료.[/green]")

        elif rest.startswith("삭제 ") or rest.startswith("delete "):
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                self.console.print("[yellow]사용법: 프리셋 삭제 <이름>[/yellow]")
                return
            name = parts[1].strip()
            if self.preset_manager.remove(name):
                self.console.print(f"[green]프리셋 '{name}' 삭제 완료.[/green]")
            else:
                self.console.print(f"[yellow]프리셋 '{name}'을 찾을 수 없습니다.[/yellow]")

        elif rest in ("목록", "list", ""):
            self._show_presets()

        else:
            self.console.print(
                "[yellow]사용법:\n"
                "  프리셋 저장 <이름> <명령>\n"
                "  프리셋 삭제 <이름>\n"
                "  프리셋 목록[/yellow]"
            )

    def _show_presets(self) -> None:
        if not self.preset_manager:
            return

        presets = self.preset_manager.list_all()
        if not presets:
            self.console.print("[dim]저장된 프리셋이 없습니다.[/dim]")
            return

        table = Table(title="명령 프리셋 (즐겨찾기)")
        table.add_column("이름", style="cyan bold")
        table.add_column("명령")

        for name, command in presets.items():
            table.add_row(name, command)

        self.console.print(table)
        self.console.print("[dim]프리셋 이름을 입력하면 바로 실행됩니다.[/dim]")

    async def _show_healthcheck(self) -> None:
        if not self.registry or not self.model_router:
            self.console.print("[dim]시스템이 아직 초기화되지 않았습니다.[/dim]")
            return

        with self.console.status("[bold green]헬스체크 실행 중..."):
            report = await run_healthcheck(self.registry, self.model_router)

        # Status color mapping
        status_style = {
            HealthStatus.OK: "[green]OK[/green]",
            HealthStatus.WARN: "[yellow]WARN[/yellow]",
            HealthStatus.ERROR: "[red]ERROR[/red]",
        }

        table = Table(title="시스템 헬스체크")
        table.add_column("항목", style="cyan")
        table.add_column("상태", justify="center")
        table.add_column("내용")
        table.add_column("지연(ms)", justify="right")

        for check in report.checks:
            latency_str = f"{check.latency_ms:.0f}" if check.latency_ms is not None else "-"
            table.add_row(
                check.name,
                status_style[check.status],
                check.message,
                latency_str,
            )

        table.add_section()
        table.add_row(
            "[bold]종합[/bold]",
            status_style[report.overall],
            f"에이전트 {report.agent_count}개 | 프로바이더 {report.provider_count}개",
            "",
        )
        self.console.print(table)

    def _show_performance(self) -> None:
        if not self.model_router or not self.context:
            self.console.print("[dim]시스템이 아직 초기화되지 않았습니다.[/dim]")
            return

        report = build_performance_report(
            self.model_router.cost_tracker,
            self.context,
        )

        if report.total_llm_calls == 0 and report.total_tasks == 0:
            self.console.print("[dim]아직 작업 이력이 없습니다. 명령을 실행한 후 다시 확인하세요.[/dim]")
            return

        # Summary line
        self.console.print(
            f"\n[bold]총 LLM 호출:[/bold] {report.total_llm_calls}회 | "
            f"[bold]총 비용:[/bold] ${report.total_cost_usd:.4f} | "
            f"[bold]총 태스크:[/bold] {report.total_tasks}건\n"
        )

        table = Table(title="에이전트 성과 대시보드")
        table.add_column("에이전트", style="cyan")
        table.add_column("역할", style="dim")
        table.add_column("모델", style="dim")
        table.add_column("LLM 호출", justify="right")
        table.add_column("토큰 (입/출)", justify="right")
        table.add_column("비용 (USD)", justify="right", style="green")
        table.add_column("태스크", justify="right")
        table.add_column("성공률", justify="right")
        table.add_column("평균 응답(초)", justify="right")

        for a in report.agents:
            # Skip agents with no activity
            if a.llm_calls == 0 and a.tasks_received == 0:
                continue

            success_style = (
                "[green]" if a.success_rate >= 80
                else "[yellow]" if a.success_rate >= 50
                else "[red]"
            )

            table.add_row(
                a.name_ko,
                a.role,
                a.model_name,
                str(a.llm_calls),
                f"{a.input_tokens:,}/{a.output_tokens:,}",
                f"${a.cost_usd:.4f}",
                f"{a.tasks_completed}/{a.tasks_received}",
                f"{success_style}{a.success_rate:.0f}%[/]",
                f"{a.avg_execution_seconds:.1f}",
            )

        self.console.print(table)

    def _show_help(self) -> None:
        help_text = (
            "[bold]사용 가능한 명령어:[/bold]\n\n"
            "[cyan]자연어 명령[/cyan]          - 어떤 업무든 한국어로 입력하세요\n"
            "[cyan]조직도 / org[/cyan]         - 현재 조직 구조 표시\n"
            "[cyan]비용 / cost[/cyan]          - 누적 API 비용 확인\n"
            "[cyan]예산 / budget[/cyan]        - 토큰 예산 현황\n"
            "[cyan]헬스체크 / health[/cyan]     - 시스템 상태 진단\n"
            "[cyan]성과 / performance[/cyan]    - 에이전트 성과 대시보드\n"
            "[cyan]프리셋 목록[/cyan]           - 저장된 명령 프리셋 조회\n"
            "[cyan]프리셋 저장 <이름> <명령>[/cyan] - 명령 프리셋 저장\n"
            "[cyan]프리셋 삭제 <이름>[/cyan]    - 명령 프리셋 삭제\n"
            "[cyan]도움말 / help[/cyan]         - 이 도움말 표시\n"
            "[cyan]종료 / exit[/cyan]           - 프로그램 종료\n\n"
            "[bold]예시 명령:[/bold]\n"
            '  "LEET MASTER 서비스의 기술 스택을 제안해줘"\n'
            '  "삼성전자 주가를 분석해줘"\n'
            '  "아까 분석한 내용을 좀 더 자세히 설명해줘"  ← 대화 맥락 유지!\n\n'
            "[bold]프리셋 사용:[/bold]\n"
            '  프리셋 저장 주간보고 "이번 주 전체 사업부 현황을 요약해줘"\n'
            '  주간보고  ← 저장된 명령 바로 실행!'
        )
        self.console.print(Panel(help_text, title="[bold]도움말[/bold]", border_style="bright_blue"))

    def shutdown(self) -> None:
        if self.model_router:
            asyncio.get_event_loop().run_until_complete(self.model_router.close())

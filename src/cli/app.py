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
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.tree import Tree

from src.core.context import SharedContext
from src.core.orchestrator import Orchestrator
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

    async def run(self) -> None:
        """Main CLI loop."""
        self._show_banner()

        self.orchestrator, self.model_router = await self._bootstrap()
        self._show_org_chart()
        self.console.print()
        self.console.print("[bold green]CORTHEX HQ 시스템 준비 완료.[/bold green]")
        self.console.print("[dim]명령을 입력하세요. '도움말' 입력 시 사용법 안내.[/dim]\n")

        while True:
            try:
                user_input = Prompt.ask("[bold cyan]CEO[/bold cyan]")

                if not user_input.strip():
                    continue
                if user_input.strip().lower() in ("exit", "quit", "종료"):
                    self._show_cost_summary()
                    self.console.print("[yellow]CORTHEX HQ를 종료합니다.[/yellow]")
                    break
                if user_input.strip().lower() in ("help", "도움말"):
                    self._show_help()
                    continue
                if user_input.strip().lower() in ("cost", "비용"):
                    self._show_cost_summary()
                    continue
                if user_input.strip().lower() in ("org", "조직도"):
                    self._show_org_chart()
                    continue

                # Process command
                with self.console.status(
                    "[bold green]에이전트 조직이 업무를 처리하고 있습니다..."
                ):
                    result = await self.orchestrator.process_command(user_input)

                # Display result
                self._display_result(result)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]중단됨. '종료' 입력 시 안전하게 종료합니다.[/yellow]")
            except Exception as e:
                self.console.print(f"[red]오류: {e}[/red]")

    async def _bootstrap(self) -> tuple[Orchestrator, ModelRouter]:
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

        return orchestrator, model_router

    def _show_banner(self) -> None:
        panel = Panel(
            f"[bold white]{_BANNER}[/bold white]\n"
            "[dim]AI Agent Corporation Headquarters v0.3.0[/dim]",
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

    def _show_help(self) -> None:
        help_text = (
            "[bold]사용 가능한 명령어:[/bold]\n\n"
            "[cyan]자연어 명령[/cyan]  - 어떤 업무든 한국어로 입력하세요\n"
            "[cyan]조직도 / org[/cyan] - 현재 조직 구조 표시\n"
            "[cyan]비용 / cost[/cyan]  - 누적 API 비용 확인\n"
            "[cyan]도움말 / help[/cyan] - 이 도움말 표시\n"
            "[cyan]종료 / exit[/cyan]  - 프로그램 종료\n\n"
            "[bold]예시 명령:[/bold]\n"
            '  "LEET MASTER 서비스의 기술 스택을 제안해줘"\n'
            '  "삼성전자 주가를 분석해줘"\n'
            '  "서비스 이용약관 초안을 만들어줘"\n'
            '  "이번 달 사업 현황을 요약해줘"\n'
            '  "마케팅 콘텐츠 전략을 수립해줘"'
        )
        self.console.print(Panel(help_text, title="[bold]도움말[/bold]", border_style="bright_blue"))

    def shutdown(self) -> None:
        if self.model_router:
            asyncio.get_event_loop().run_until_complete(self.model_router.close())

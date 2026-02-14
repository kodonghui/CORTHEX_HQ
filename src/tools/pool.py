"""
Tool Pool: central registry of all available tools.

Any agent with permission can invoke a tool by name.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from src.core.errors import ToolNotFoundError
from src.tools.base import BaseTool, ToolConfig

if TYPE_CHECKING:
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.tools")


class ToolPool:
    """Central registry and dispatcher for all tools."""

    def __init__(self, model_router: ModelRouter) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._model_router = model_router

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.tool_id] = tool
        logger.debug("도구 등록: %s (%s)", tool.tool_id, tool.config.name_ko)

    def build_from_config(self, tools_config: dict) -> None:
        """Parse tools.yaml and instantiate all tools."""
        # 각 도구를 개별적으로 import (하나 실패해도 나머지는 동작)
        _imports: dict[str, str] = {
            "patent_attorney": "src.tools.patent_attorney.PatentAttorneyTool",
            "tax_accountant": "src.tools.tax_accountant.TaxAccountantTool",
            "designer": "src.tools.designer.DesignerTool",
            "translator": "src.tools.translator.TranslatorTool",
            "web_search": "src.tools.web_search.WebSearchTool",
            "sns_manager": "src.tools.sns.sns_manager.SNSManager",
            "daum_cafe": "src.tools.daum_cafe.DaumCafeTool",
            "leet_survey": "src.tools.leet_survey.LeetSurveyTool",
            # ─── CTO 기술개발처 신규 도구 ───
            "uptime_monitor": "src.tools.uptime_monitor.UptimeMonitorTool",
            "security_scanner": "src.tools.security_scanner.SecurityScannerTool",
            "log_analyzer": "src.tools.log_analyzer.LogAnalyzerTool",
            "api_benchmark": "src.tools.api_benchmark.ApiBenchmarkTool",
            # ─── CPO 출판기록처 신규 도구 ───
            "report_generator": "src.tools.report_generator.ReportGeneratorTool",
            "meeting_formatter": "src.tools.meeting_formatter.MeetingFormatterTool",
            # ─── 전사 공통 도구 ───
            "newsletter_builder": "src.tools.newsletter_builder.NewsletterBuilderTool",
        }
        tool_classes: dict[str, type[BaseTool]] = {}
        for tool_id, import_path in _imports.items():
            module_path, class_name = import_path.rsplit(".", 1)
            try:
                import importlib
                mod = importlib.import_module(module_path)
                tool_classes[tool_id] = getattr(mod, class_name)
            except Exception as e:
                logger.warning("도구 '%s' 로드 실패 (건너뜀): %s", tool_id, e)

        for tool_def in tools_config.get("tools", []):
            config = ToolConfig(**tool_def)
            cls = tool_classes.get(config.tool_id)
            if cls:
                try:
                    self.register(cls(config=config, model_router=self._model_router))
                except Exception as e:
                    logger.warning("도구 '%s' 등록 실패 (건너뜀): %s", config.tool_id, e)

        logger.info("총 %d개 도구 등록 완료", len(self._tools))

    async def invoke(self, tool_id: str, caller_id: str = "", **kwargs: Any) -> Any:
        if tool_id not in self._tools:
            raise ToolNotFoundError(tool_id)
        logger.info("[%s] 도구 호출: %s", caller_id, tool_id)
        return await self._tools[tool_id].execute(caller_id=caller_id, **kwargs)

    def list_tools(self) -> list[dict]:
        return [
            {"id": t.tool_id, "name": t.config.name_ko, "desc": t.config.description}
            for t in self._tools.values()
        ]

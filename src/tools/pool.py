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
        from src.tools.patent_attorney import PatentAttorneyTool
        from src.tools.tax_accountant import TaxAccountantTool
        from src.tools.designer import DesignerTool
        from src.tools.translator import TranslatorTool
        from src.tools.web_search import WebSearchTool
        from src.tools.sns.sns_manager import SNSManager
        from src.tools.daum_cafe import DaumCafeTool
        from src.tools.leet_survey import LeetSurveyTool
        # ─── 부서별 전문가 도구 ───
        from src.tools.kr_stock import KrStockTool
        from src.tools.dart_api import DartApiTool
        from src.tools.naver_news import NaverNewsTool
        from src.tools.ecos_macro import EcosMacroTool
        from src.tools.naver_datalab import NaverDatalabTool
        from src.tools.public_data import PublicDataTool
        from src.tools.kipris import KiprisTool
        from src.tools.law_search import LawSearchTool
        from src.tools.github_tool import GithubTool
        from src.tools.code_quality import CodeQualityTool
        from src.tools.notion_api import NotionApiTool
        from src.tools.doc_converter import DocConverterTool

        tool_classes: dict[str, type[BaseTool]] = {
            "patent_attorney": PatentAttorneyTool,
            "tax_accountant": TaxAccountantTool,
            "designer": DesignerTool,
            "translator": TranslatorTool,
            "web_search": WebSearchTool,
            "sns_manager": SNSManager,
            "daum_cafe": DaumCafeTool,
            "leet_survey": LeetSurveyTool,
            # ─── 부서별 전문가 도구 ───
            "kr_stock": KrStockTool,
            "dart_api": DartApiTool,
            "naver_news": NaverNewsTool,
            "ecos_macro": EcosMacroTool,
            "naver_datalab": NaverDatalabTool,
            "public_data": PublicDataTool,
            "kipris": KiprisTool,
            "law_search": LawSearchTool,
            "github_tool": GithubTool,
            "code_quality": CodeQualityTool,
            "notion_api": NotionApiTool,
            "doc_converter": DocConverterTool,
        }

        for tool_def in tools_config.get("tools", []):
            config = ToolConfig(**tool_def)
            cls = tool_classes.get(config.tool_id)
            if cls:
                self.register(cls(config=config, model_router=self._model_router))

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

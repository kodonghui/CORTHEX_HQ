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
        self._agent_models: dict[str, str] = {}  # agent_id → model_name 매핑
        self._agent_temperatures: dict[str, float] = {}  # agent_id → temperature

    def set_agent_model(self, agent_id: str, model: str, temperature: float | None = None) -> None:
        """에이전트 모델/temperature를 풀에 등록. 도구가 caller 설정을 따르도록."""
        if agent_id and model:
            self._agent_models[agent_id] = model
        if agent_id and temperature is not None:
            self._agent_temperatures[agent_id] = temperature

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
            # ─── 부서별 전문가 도구 ───
            "kr_stock": "src.tools.kr_stock.KrStockTool",
            "dart_api": "src.tools.dart_api.DartApiTool",
            "naver_news": "src.tools.naver_news.NaverNewsTool",
            "ecos_macro": "src.tools.ecos_macro.EcosMacroTool",
            "naver_datalab": "src.tools.naver_datalab.NaverDatalabTool",
            "public_data": "src.tools.public_data.PublicDataTool",
            "kipris": "src.tools.kipris.KiprisTool",
            "law_search": "src.tools.law_search.LawSearchTool",
            "github_tool": "src.tools.github_tool.GithubTool",
            "code_quality": "src.tools.code_quality.CodeQualityTool",
            "notion_api": "src.tools.notion_api.NotionApiTool",
            "doc_converter": "src.tools.doc_converter.DocConverterTool",
            # CLO 법무IP처 + CSO 사업기획처 도구
            "platform_market_scraper": "src.tools.platform_market_scraper.PlatformMarketScraperTool",
            "precedent_analyzer": "src.tools.precedent_analyzer.PrecedentAnalyzerTool",
            "trademark_similarity": "src.tools.trademark_similarity.TrademarkSimilarityTool",
            "contract_reviewer": "src.tools.contract_reviewer.ContractReviewerTool",
            "nda_analyzer": "src.tools.nda_analyzer.NdaAnalyzerTool",
            "license_scanner": "src.tools.license_scanner.LicenseScannerTool",
            "ip_portfolio_manager": "src.tools.ip_portfolio_manager.IPPortfolioManagerTool",
            "ai_governance_checker": "src.tools.ai_governance_checker.AIGovernanceCheckerTool",
            "law_change_monitor": "src.tools.law_change_monitor.LawChangeMonitorTool",
            "regulation_radar": "src.tools.regulation_radar.RegulationRadarTool",
            "dispute_simulator": "src.tools.dispute_simulator.DisputeSimulatorTool",
            # ─── CIO 투자분석처 신규 도구 ───
            "us_stock": "src.tools.us_stock.UsStockTool",
            # ─── CIO 미국 주식 전문 도구 10종 ───
            "sec_edgar": "src.tools.sec_edgar.SecEdgarTool",
            "us_financial_analyzer": "src.tools.us_financial_analyzer.UsFinancialAnalyzerTool",
            "us_technical_analyzer": "src.tools.us_technical_analyzer.UsTechnicalAnalyzerTool",
            "options_flow": "src.tools.options_flow.OptionsFlowTool",
            "macro_fed_tracker": "src.tools.macro_fed_tracker.MacroFedTrackerTool",
            "sector_rotation": "src.tools.sector_rotation.SectorRotationTool",
            "earnings_ai": "src.tools.earnings_ai.EarningsAiTool",
            "sentiment_nlp": "src.tools.sentiment_nlp.SentimentNlpTool",
            "portfolio_optimizer_v2": "src.tools.portfolio_optimizer_v2.PortfolioOptimizerV2Tool",
            "correlation_analyzer": "src.tools.correlation_analyzer.CorrelationAnalyzerTool",
            "dart_monitor": "src.tools.dart_monitor.DartMonitorTool",
            "stock_screener": "src.tools.stock_screener.StockScreenerTool",
            "backtest_engine": "src.tools.backtest_engine.BacktestEngineTool",
            "insider_tracker": "src.tools.insider_tracker.InsiderTrackerTool",
            "dividend_calendar": "src.tools.dividend_calendar.DividendCalendarTool",
            "technical_analyzer": "src.tools.technical_analyzer.TechnicalAnalyzerTool",
            "dcf_valuator": "src.tools.dcf_valuator.DcfValuatorTool",
            "portfolio_optimizer": "src.tools.portfolio_optimizer.PortfolioOptimizerTool",
            "risk_calculator": "src.tools.risk_calculator.RiskCalculatorTool",
            "sector_rotator": "src.tools.sector_rotator.SectorRotatorTool",
            "sentiment_scorer": "src.tools.sentiment_scorer.SentimentScorerTool",
            "pair_analyzer": "src.tools.pair_analyzer.PairAnalyzerTool",
            "earnings_surprise": "src.tools.earnings_surprise.EarningsSurpriseTool",
            "macro_regime": "src.tools.macro_regime.MacroRegimeTool",
            # ─── CMO 마케팅고객처 신규 도구 ───
            "funnel_analyzer": "src.tools.funnel_analyzer.FunnelAnalyzerTool",
            "ab_test_engine": "src.tools.ab_test_engine.AbTestEngineTool",
            "customer_ltv_model": "src.tools.customer_ltv_model.CustomerLtvModelTool",
            "rfm_segmentation": "src.tools.customer_cohort_analyzer.CustomerCohortAnalyzer",
            "content_quality_scorer": "src.tools.content_quality_scorer.ContentQualityScorerTool",
            "pricing_sensitivity": "src.tools.pricing_sensitivity.PricingSensitivityTool",
            "churn_risk_scorer": "src.tools.churn_risk_scorer.ChurnRiskScorerTool",
            "marketing_attribution": "src.tools.marketing_attribution.MarketingAttributionTool",
            "cohort_retention": "src.tools.cohort_retention.CohortRetentionTool",
            "viral_coefficient": "src.tools.viral_coefficient.ViralCoefficientTool",
            "seo_analyzer": "src.tools.seo_analyzer.SeoAnalyzerTool",
            "sentiment_analyzer": "src.tools.sentiment_analyzer.SentimentAnalyzerTool",
            "hashtag_recommender": "src.tools.hashtag_recommender.HashtagRecommenderTool",
            "email_optimizer": "src.tools.email_optimizer.EmailOptimizerTool",
            "competitor_sns_monitor": "src.tools.competitor_sns_monitor.CompetitorSnsMonitorTool",
            # ─── CSO 사업기획처 신규 도구 ───
            "competitor_monitor": "src.tools.competitor_monitor.CompetitorMonitorTool",
            "app_review_scraper": "src.tools.app_review_scraper.AppReviewScraperTool",
            "youtube_analyzer": "src.tools.youtube_analyzer.YoutubeAnalyzerTool",
            "subsidy_finder": "src.tools.subsidy_finder.SubsidyFinderTool",
            "naver_place_scraper": "src.tools.naver_place_scraper.NaverPlaceScraperTool",
            "scholar_scraper": "src.tools.scholar_scraper.ScholarScraperTool",
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
            # ─── Phase 1: 최우선 신규 도구 ───
            "real_web_search": "src.tools.real_web_search.RealWebSearchTool",
            "spreadsheet_tool": "src.tools.spreadsheet_tool.SpreadsheetTool",
            "chart_generator": "src.tools.chart_generator.ChartGeneratorTool",
            "pdf_parser": "src.tools.pdf_parser.PdfParserTool",
            "prompt_tester": "src.tools.prompt_tester.PromptTesterTool",
            "embedding_tool": "src.tools.embedding_tool.EmbeddingTool",
            "token_counter": "src.tools.token_counter.TokenCounterTool",
            # ─── Phase 2: 중요 신규 도구 ───
            "notification_engine": "src.tools.notification_engine.NotificationEngineTool",
            "global_market_tool": "src.tools.global_market_tool.GlobalMarketTool",
            "financial_calculator": "src.tools.financial_calculator.FinancialCalculatorTool",
            "calendar_tool": "src.tools.calendar_tool.CalendarTool",
            "email_sender": "src.tools.email_sender.EmailSenderTool",
            # ─── Phase 3: 미래 투자 신규 도구 ───
            "vector_knowledge": "src.tools.vector_knowledge.VectorKnowledgeTool",
            "decision_tracker": "src.tools.decision_tracker.DecisionTrackerTool",
            "image_generator": "src.tools.image_generator.ImageGeneratorTool",
            "audio_transcriber": "src.tools.audio_transcriber.AudioTranscriberTool",
            "cross_agent_protocol": "src.tools.cross_agent_protocol.CrossAgentProtocolTool",
            "trading_settings_control": "src.tools.trading_settings_control.TradingSettingsControlTool",
            "trading_executor": "src.tools.trading_executor.TradingExecutorTool",
            # ─── CMO Gemini 이미지 생성 (8유형 통합) ───
            "gemini_image_generator": "src.tools.gemini_image_generator.GeminiImageGeneratorTool",
            # ─── Phase 2: 교수급 전문 도구 (25개) ───
            # CTO 기술개발처
            "architecture_evaluator": "src.tools.architecture_evaluator.ArchitectureEvaluatorTool",
            "performance_profiler": "src.tools.performance_profiler.PerformanceProfilerTool",
            "tech_debt_analyzer": "src.tools.tech_debt_analyzer.TechDebtAnalyzerTool",
            "system_design_advisor": "src.tools.system_design_advisor.SystemDesignAdvisorTool",
            "ai_model_evaluator": "src.tools.ai_model_evaluator.AIModelEvaluatorTool",
            # CSO 사업기획처
            "market_sizer": "src.tools.market_sizer.MarketSizer",
            "business_model_scorer": "src.tools.business_model_scorer.BusinessModelScorer",
            "competitive_mapper": "src.tools.competitive_mapper.CompetitiveMapper",
            "growth_forecaster": "src.tools.growth_forecaster.GrowthForecaster",
            "scenario_simulator": "src.tools.scenario_simulator.ScenarioSimulator",
            # CPO 출판기록처 교수급
            "document_summarizer": "src.tools.document_summarizer.DocumentSummarizerTool",
            "terms_generator": "src.tools.terms_generator.TermsGeneratorTool",
            "communication_optimizer": "src.tools.communication_optimizer.CommunicationOptimizerTool",
            # 비서실 교수급
            "agenda_optimizer": "src.tools.agenda_optimizer.AgendaOptimizerTool",
            "priority_matrix": "src.tools.priority_matrix.PriorityMatrixTool",
            "meeting_effectiveness": "src.tools.meeting_effectiveness.MeetingEffectivenessTool",
            "delegation_analyzer": "src.tools.delegation_analyzer.DelegationAnalyzerTool",
            "stakeholder_mapper": "src.tools.stakeholder_mapper.StakeholderMapperTool",
            # CLO 법무IP처 교수급
            "compliance_checker": "src.tools.compliance_checker.ComplianceCheckerTool",
            "privacy_auditor": "src.tools.privacy_auditor.PrivacyAuditorTool",
            "risk_communicator": "src.tools.risk_communicator.RiskCommunicatorTool",
            "risk_matrix": "src.tools.risk_matrix.RiskMatrixTool",
            # CSO/CMO 공용 교수급
            "pricing_optimizer": "src.tools.pricing_optimizer.PricingOptimizer",
            "customer_cohort_analyzer": "src.tools.customer_cohort_analyzer.CustomerCohortAnalyzer",
            "swot_quantifier": "src.tools.swot_quantifier.SwotQuantifier",
            # ─── Skill 도구 (89개) — 마케팅/개발/코딩패턴/유틸 ───
            "skill_copywriting": "src.tools.skill_tool.SkillTool",
            "skill_copy_editing": "src.tools.skill_tool.SkillTool",
            "skill_social_content": "src.tools.skill_tool.SkillTool",
            "skill_email_sequence": "src.tools.skill_tool.SkillTool",
            "skill_seo_audit": "src.tools.skill_tool.SkillTool",
            "skill_schema_markup": "src.tools.skill_tool.SkillTool",
            "skill_content_strategy": "src.tools.skill_tool.SkillTool",
            "skill_page_cro": "src.tools.skill_tool.SkillTool",
            "skill_form_cro": "src.tools.skill_tool.SkillTool",
            "skill_marketing_ideas": "src.tools.skill_tool.SkillTool",
            "skill_marketing_psychology": "src.tools.skill_tool.SkillTool",
            "skill_pricing_strategy": "src.tools.skill_tool.SkillTool",
            "skill_launch_strategy": "src.tools.skill_tool.SkillTool",
            "skill_competitor_alternatives": "src.tools.skill_tool.SkillTool",
            "skill_paid_ads": "src.tools.skill_tool.SkillTool",
            "skill_referral_program": "src.tools.skill_tool.SkillTool",
            # ─── 개발 프로세스 스킬 ───
            "skill_tdd_workflow": "src.tools.skill_tool.SkillTool",
            "skill_verification_loop": "src.tools.skill_tool.SkillTool",
            "skill_systematic_debugging": "src.tools.skill_tool.SkillTool",
            "skill_code_review": "src.tools.skill_tool.SkillTool",
            "skill_writing_plans": "src.tools.skill_tool.SkillTool",
            "skill_coding_standards": "src.tools.skill_tool.SkillTool",
            "skill_frontend_patterns": "src.tools.skill_tool.SkillTool",
            "skill_frontend_design": "src.tools.skill_tool.SkillTool",
            "skill_backend_patterns": "src.tools.skill_tool.SkillTool",
            "skill_python_patterns": "src.tools.skill_tool.SkillTool",
            "skill_security_review": "src.tools.skill_tool.SkillTool",
            "skill_code_documenter": "src.tools.skill_tool.SkillTool",
            "skill_changelog_generator": "src.tools.skill_tool.SkillTool",
            "skill_last30days": "src.tools.skill_tool.SkillTool",
            "skill_canvas_design": "src.tools.skill_tool.SkillTool",
            "skill_defuddle": "src.tools.skill_tool.SkillTool",
            "skill_brainstorming": "src.tools.skill_tool.SkillTool",
            "skill_handoff": "src.tools.skill_tool.SkillTool",
            "skill_mcp_builder": "src.tools.skill_tool.SkillTool",
            # ─── CRO / 마케팅 고급 스킬 ───
            "skill_programmatic_seo": "src.tools.skill_tool.SkillTool",
            "skill_signup_flow_cro": "src.tools.skill_tool.SkillTool",
            "skill_onboarding_cro": "src.tools.skill_tool.SkillTool",
            "skill_popup_cro": "src.tools.skill_tool.SkillTool",
            "skill_paywall_upgrade_cro": "src.tools.skill_tool.SkillTool",
            "skill_free_tool_strategy": "src.tools.skill_tool.SkillTool",
            "skill_product_marketing_context": "src.tools.skill_tool.SkillTool",
            # ─── TDD / 검증 스킬 ───
            "skill_test_driven_development": "src.tools.skill_tool.SkillTool",
            "skill_eval_harness": "src.tools.skill_tool.SkillTool",
            "skill_verification_before_completion": "src.tools.skill_tool.SkillTool",
            "skill_requesting_code_review": "src.tools.skill_tool.SkillTool",
            "skill_receiving_code_review": "src.tools.skill_tool.SkillTool",
            "skill_create_pr": "src.tools.skill_tool.SkillTool",
            "skill_executing_plans": "src.tools.skill_tool.SkillTool",
            "skill_dispatching_parallel_agents": "src.tools.skill_tool.SkillTool",
            "skill_subagent_driven_development": "src.tools.skill_tool.SkillTool",
            "skill_finishing_branch": "src.tools.skill_tool.SkillTool",
            "skill_git_worktrees": "src.tools.skill_tool.SkillTool",
            "skill_strategic_compact": "src.tools.skill_tool.SkillTool",
            # ─── 기획 / 유틸리티 스킬 ───
            "skill_brainstorm": "src.tools.skill_tool.SkillTool",
            "skill_senior_frontend": "src.tools.skill_tool.SkillTool",
            "skill_artifacts_builder": "src.tools.skill_tool.SkillTool",
            # ─── 언어별 코딩 패턴 스킬 ───
            "skill_python_testing": "src.tools.skill_tool.SkillTool",
            "skill_java_coding_standards": "src.tools.skill_tool.SkillTool",
            "skill_springboot_patterns": "src.tools.skill_tool.SkillTool",
            "skill_springboot_security": "src.tools.skill_tool.SkillTool",
            "skill_springboot_tdd": "src.tools.skill_tool.SkillTool",
            "skill_springboot_verification": "src.tools.skill_tool.SkillTool",
            "skill_jpa_patterns": "src.tools.skill_tool.SkillTool",
            "skill_django_patterns": "src.tools.skill_tool.SkillTool",
            "skill_django_security": "src.tools.skill_tool.SkillTool",
            "skill_django_tdd": "src.tools.skill_tool.SkillTool",
            "skill_django_verification": "src.tools.skill_tool.SkillTool",
            "skill_golang_patterns": "src.tools.skill_tool.SkillTool",
            "skill_golang_testing": "src.tools.skill_tool.SkillTool",
            "skill_cpp_testing": "src.tools.skill_tool.SkillTool",
            "skill_postgres_patterns": "src.tools.skill_tool.SkillTool",
            "skill_clickhouse_io": "src.tools.skill_tool.SkillTool",
            # ─── 보안 / 디자인 / 분석 스킬 ───
            "skill_security_scan": "src.tools.skill_tool.SkillTool",
            "skill_theme_factory": "src.tools.skill_tool.SkillTool",
            "skill_developer_growth": "src.tools.skill_tool.SkillTool",
            "skill_route_researcher": "src.tools.skill_tool.SkillTool",
            # ─── Obsidian / 노트 스킬 ───
            "skill_obsidian_markdown": "src.tools.skill_tool.SkillTool",
            "skill_obsidian_cli": "src.tools.skill_tool.SkillTool",
            "skill_obsidian_bases": "src.tools.skill_tool.SkillTool",
            "skill_json_canvas": "src.tools.skill_tool.SkillTool",
            # ─── 설정 / 학습 / 메타 스킬 ───
            "skill_configure_ecc": "src.tools.skill_tool.SkillTool",
            "skill_nutrient_doc": "src.tools.skill_tool.SkillTool",
            "skill_pensieve": "src.tools.skill_tool.SkillTool",
            "skill_continuous_learning": "src.tools.skill_tool.SkillTool",
            "skill_continuous_learning_v2": "src.tools.skill_tool.SkillTool",
            "skill_using_superpowers": "src.tools.skill_tool.SkillTool",
            "skill_iterative_retrieval": "src.tools.skill_tool.SkillTool",
            "skill_project_guidelines": "src.tools.skill_tool.SkillTool",
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
        tool = self._tools[tool_id]
        # caller 에이전트의 모델/temperature를 kwargs에 주입
        if caller_id:
            if "_caller_model" not in kwargs:
                caller_model = self._agent_models.get(caller_id)
                if caller_model:
                    kwargs["_caller_model"] = caller_model
            if "_caller_temperature" not in kwargs:
                caller_temp = self._agent_temperatures.get(caller_id)
                if caller_temp is not None:
                    kwargs["_caller_temperature"] = caller_temp
        # 도구 인스턴스에 caller 설정 주입 — _llm_call()이 자동으로 사용
        tool._current_caller_model = kwargs.get("_caller_model")
        tool._current_caller_temperature = kwargs.get("_caller_temperature")
        return await tool.execute(caller_id=caller_id, **kwargs)

    def list_tools(self) -> list[dict]:
        return [
            {"id": t.tool_id, "name": t.config.name_ko, "desc": t.config.description}
            for t in self._tools.values()
        ]

"""
Agent Registry: builds and holds all agent instances.

The registry is the factory that reads agents.yaml and creates
the entire organizational hierarchy.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from src.core.agent import AgentConfig, BaseAgent, ManagerAgent, SpecialistAgent, WorkerAgent
from src.core.errors import AgentNotFoundError
from src.core.knowledge import KnowledgeManager

if TYPE_CHECKING:
    from src.llm.router import ModelRouter
    from src.tools.pool import ToolPool
    from src.core.context import SharedContext

logger = logging.getLogger("corthex.registry")

# Role string -> Agent class mapping
_ROLE_CLASS_MAP: dict[str, type[BaseAgent]] = {
    "division_head": ManagerAgent,  # Division heads are managers
    "manager": ManagerAgent,
    "specialist": SpecialistAgent,
    "worker": WorkerAgent,
}


class AgentRegistry:
    """Builds all agent instances from YAML config and provides lookup."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def build_from_config(
        self,
        agents_config: dict,
        model_router: ModelRouter,
        tool_pool: ToolPool,
        context: SharedContext,
        knowledge_dir: Optional[Path] = None,
    ) -> None:
        """Parse agents.yaml and instantiate every agent."""
        # Load knowledge if available
        km: Optional[KnowledgeManager] = None
        if knowledge_dir and knowledge_dir.exists():
            km = KnowledgeManager(knowledge_dir)
            km.load_all()

        for agent_def in agents_config.get("agents", []):
            try:
                config = AgentConfig(**agent_def)

                # Inject shared knowledge into system prompt
                if km:
                    extra_knowledge = km.get_knowledge_for_agent(config.division)
                    if extra_knowledge:
                        config = config.model_copy(update={
                            "system_prompt": config.system_prompt + extra_knowledge
                        })

                agent_cls = _ROLE_CLASS_MAP.get(config.role, SpecialistAgent)
                agent = agent_cls(
                    config=config,
                    model_router=model_router,
                    tool_pool=tool_pool,
                    context=context,
                )
                self._agents[config.agent_id] = agent
                logger.debug("에이전트 등록: %s (%s)", config.agent_id, config.name_ko)
            except Exception as e:
                logger.error("에이전트 생성 실패 [%s]: %s", agent_def.get("agent_id", "?"), e)

        logger.info("총 %d개 에이전트 등록 완료", len(self._agents))

    def get_agent(self, agent_id: str) -> BaseAgent:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        return self._agents[agent_id]

    def list_all(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def list_division_heads(self) -> list[dict]:
        """Return summary of division heads for routing."""
        heads = []
        for agent in self._agents.values():
            if agent.config.role == "division_head" or agent.config.superior_id is None:
                heads.append({
                    "agent_id": agent.agent_id,
                    "name_ko": agent.config.name_ko,
                    "division": agent.config.division,
                    "capabilities": agent.config.capabilities,
                })
        return heads

    @property
    def agent_count(self) -> int:
        return len(self._agents)

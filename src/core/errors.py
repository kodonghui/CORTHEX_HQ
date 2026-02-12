"""Custom exceptions for CORTHEX HQ."""


class CorthexError(Exception):
    """Base exception for all CORTHEX HQ errors."""


class AgentNotFoundError(CorthexError):
    """Raised when an agent ID is not found in the registry."""

    def __init__(self, agent_id: str):
        super().__init__(f"에이전트를 찾을 수 없습니다: '{agent_id}'")
        self.agent_id = agent_id


class ToolNotFoundError(CorthexError):
    """Raised when a tool ID is not found in the pool."""

    def __init__(self, tool_id: str):
        super().__init__(f"도구를 찾을 수 없습니다: '{tool_id}'")
        self.tool_id = tool_id


class ToolPermissionError(CorthexError):
    """Raised when an agent tries to use a tool it doesn't have permission for."""

    def __init__(self, agent_id: str, tool_id: str):
        super().__init__(
            f"에이전트 '{agent_id}'은(는) 도구 '{tool_id}' 사용 권한이 없습니다."
        )
        self.agent_id = agent_id
        self.tool_id = tool_id


class LLMProviderError(CorthexError):
    """Raised when an LLM API call fails."""

    def __init__(self, provider: str, model: str, detail: str = ""):
        msg = f"LLM 호출 실패 [{provider}/{model}]"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
        self.provider = provider
        self.model = model


class ConfigError(CorthexError):
    """Raised when configuration is invalid."""

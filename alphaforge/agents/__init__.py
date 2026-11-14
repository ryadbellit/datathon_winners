from alphaforge.agents.base import Agent
from alphaforge.agents.specialists import DocumentAnalystAgent, RiskExplainerAgent, SentimentAgent

DEFAULT_AGENTS: tuple[type[Agent], ...] = (DocumentAnalystAgent, SentimentAgent, RiskExplainerAgent)

__all__ = ["Agent", "DEFAULT_AGENTS", "DocumentAnalystAgent", "SentimentAgent", "RiskExplainerAgent"]

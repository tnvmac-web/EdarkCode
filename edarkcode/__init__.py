"""edarkcode — autonomous coding agent."""
from __future__ import annotations

__version__ = "0.1.0"

from .core.agent import Agent
from .core.config import Settings
from .core.types import AgentPhase, Message, Role, StreamEvent

__all__ = ["Agent", "Settings", "AgentPhase", "Message", "Role", "StreamEvent", "__version__"]

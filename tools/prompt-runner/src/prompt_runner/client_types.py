"""Backend-neutral client types for prompt-runner integrations.

The current prompt-runner backends share the same call/response/error
shapes.  This module provides neutral names so downstream tools do not
need to import from a Claude-specific module.
"""
from __future__ import annotations

from prompt_runner.claude_client import (
    ClaudeCall as AgentCall,
    ClaudeClient as AgentClient,
    ClaudeInvocationError as AgentInvocationError,
    ClaudeResponse as AgentResponse,
)

__all__ = [
    "AgentCall",
    "AgentClient",
    "AgentInvocationError",
    "AgentResponse",
]

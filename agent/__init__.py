"""Agent package — orchestration, workshop loop, and session state.

Note: AgentSession and WorkshopAgent are quarantined from public re-exports
during stabilization.  They remain importable directly from their modules
for test use, but are no longer surfaced via ``from agent import *``.
"""
from agent.intent_orchestrator import IntentOrchestrator  # noqa: F401

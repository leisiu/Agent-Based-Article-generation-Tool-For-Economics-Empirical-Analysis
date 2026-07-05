"""
Core module for paper generation
Contains base agent, generator, and orchestrator

Note: To avoid circular imports, `generator` and `orchestrator` are NOT imported at
package level. They should be imported explicitly when needed:
    from core.generator import MultiAgentPaperGenerator, create_multi_agent_generator
    from core.orchestrator import MultiAgentOrchestrator
"""
from .base_agent import BaseAgent, Task, AgentResponse

__all__ = [
    'BaseAgent',
    'Task',
    'AgentResponse',
]

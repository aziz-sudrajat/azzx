"""AZZX v10.4 agent layer — one unified agent.

Native capabilities, integrated into AZZX's normal workflows (no separate
modes or competing CLIs):

- providers: typed AI provider errors, bounded retries, cancellation
- multi_agent: role-based collaboration (planner/researcher/coder/reviewer/
  tester/security) backed by the configured AI provider
- memory: SQLite persistent memory, keyword + semantic hybrid search,
  shared/private boundaries, project scoping
- session: session journal with end/resume/stale detection
- tasks: background task queue with detached drainer, cancel/interrupt/resume
- skills: validated, trust-gated native skill registry
- scheduler: persistent interval scheduler for registered tools
- reasoning/tracer/streaming/vision/message_bus: supporting infrastructure
"""

from __future__ import annotations

from .embeddings import SimpleEmbedder, tokenize
from .memory import MemoryEntry, MemoryStore, find_secret_kind, get_memory_store
from .message_bus import MessageBus, MessageEnvelope, get_message_bus
from .multi_agent import AgentProfile, MultiAgentOrchestrator, get_multi_agent_orchestrator, run_multi_agent_task as run_agent_task
from .orchestrator import (
    assemble_memory_prompt,
    describe_tools_for_ai,
    get_memory_store as get_global_memory_store,
    get_message_bus as get_global_message_bus,
    get_orchestrator,
    map_nl_to_tool,
    register_all,
    run_multi_agent_task,
    run_tool_call,
    stream_multi_agent_task,
)
from .providers import (
    AIRouter,
    AuthenticationError,
    BaseAdapter,
    CancelledError,
    MalformedResponseError,
    MockAdapter,
    ProviderConfigError,
    ProviderError,
    ProviderOutageError,
    ProviderTimeoutError,
    RateLimitError,
    RouteResult,
    adapter_for,
    classify_http_error,
    default_router,
)
from .reasoning import ReasoningTrace, ThoughtStep, STEP_KINDS
from .scheduler import ToolScheduler
from .session import SESSION_STATUSES, SessionMemoryJournal, SessionSnapshot, get_session_journal
from .skills import SkillError, SkillRegistry, register_skill_tools, validate_args, validate_manifest
from .streaming import AgentStream, StreamEvent, TokenStream, stream_task_progress
from .tasks import TaskQueue, check_tool_approvals, get_task_queue, run_drainer, spawn_drainer
from .tracer import Span, Tracer, get_tracer
from .vision import encode_image, is_vision_model, to_vision_content

__all__ = [
    "MemoryEntry",
    "MemoryStore",
    "find_secret_kind",
    "get_memory_store",
    "MessageBus",
    "MessageEnvelope",
    "get_message_bus",
    "AgentProfile",
    "MultiAgentOrchestrator",
    "get_multi_agent_orchestrator",
    "run_agent_task",
    "SessionMemoryJournal",
    "SessionSnapshot",
    "SESSION_STATUSES",
    "get_session_journal",
    "AgentStream",
    "StreamEvent",
    "TokenStream",
    "stream_task_progress",
    "SimpleEmbedder",
    "tokenize",
    "ReasoningTrace",
    "ThoughtStep",
    "STEP_KINDS",
    "TaskQueue",
    "check_tool_approvals",
    "get_task_queue",
    "run_drainer",
    "spawn_drainer",
    "ToolScheduler",
    "SkillRegistry",
    "SkillError",
    "register_skill_tools",
    "validate_args",
    "validate_manifest",
    "Span",
    "Tracer",
    "get_tracer",
    "encode_image",
    "is_vision_model",
    "to_vision_content",
    "AIRouter",
    "AuthenticationError",
    "BaseAdapter",
    "CancelledError",
    "MalformedResponseError",
    "MockAdapter",
    "ProviderConfigError",
    "ProviderError",
    "ProviderOutageError",
    "ProviderTimeoutError",
    "RateLimitError",
    "RouteResult",
    "adapter_for",
    "classify_http_error",
    "default_router",
    "register_all",
    "describe_tools_for_ai",
    "run_tool_call",
    "map_nl_to_tool",
    "get_global_memory_store",
    "get_global_message_bus",
    "get_orchestrator",
    "assemble_memory_prompt",
    "run_multi_agent_task",
    "stream_multi_agent_task",
]

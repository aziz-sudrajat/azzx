"""AZZX v10.2 agent layer — Hermes-like: memory, bus, streaming, sessions, orchestration, reasoning, tracing, queue."""

from __future__ import annotations

from .embeddings import SimpleEmbedder, tokenize
from .memory import MemoryStore, get_memory_store
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
from .reasoning import ReasoningTrace, ThoughtStep, STEP_KINDS
from .session import SessionMemoryJournal, SessionSnapshot, get_session_journal
from .streaming import AgentStream, StreamEvent, TokenStream, stream_task_progress
from .tasks import TaskQueue, get_task_queue, run_drainer, spawn_drainer
from .tracer import Span, Tracer, get_tracer
from .vision import encode_image, is_vision_model, to_vision_content

__all__ = [
    "MemoryStore",
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
    "get_task_queue",
    "run_drainer",
    "spawn_drainer",
    "Span",
    "Tracer",
    "get_tracer",
    "encode_image",
    "is_vision_model",
    "to_vision_content",
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

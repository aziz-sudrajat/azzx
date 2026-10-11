"""AZZX v10.5 agent layer — one unified, autonomous agent.

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
- sandbox: confined command execution (local + docker backends)
- planning: explicit tool-grounded plans + agent todo list
- learning: post-task distillation into staged memory/skill proposals
- checkpoints: snapshot/rollback before destructive work
- autonomy: plan -> approve -> execute -> learn loop (azzx auto)
- webreader: lightweight page fetch + DDG search (no JS)
- webagent: autonomous goal-driven browsing loop (azzx webauto)
- connectors: GitHub + email app connectors
- cronutil: dependency-free cron expression parsing
- auditor: records every tool call; rule-based + LLM-judge correctness reports
- compressor: shrink big files (signatures/extractive/head_tail/summarize)
  before they enter AI context
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
from .autonomy import AutonomousRunner
from .checkpoints import create as create_checkpoint, list_checkpoints, prune as prune_checkpoints, rollback as rollback_checkpoint
from .companion import companion_system_prompt, get_profile, remember_fact, save_profile
from .learning import approve as approve_learned, discard as discard_learned, distill as distill_learnings, list_pending as list_pending_learnings
from .mcp import register_mcp_tools
from .webreader import fetch as web_fetch, register_webreader_tools, search as web_search
from .webagent import WebAgent
from .connectors import register_connector_tools
from .cronutil import describe_cron, next_cron_time, parse_cron
from .auditor import end_run as audit_end_run, judge as audit_judge, log_custom as audit_log_custom, recent_calls as audit_recent_calls, report as audit_report, start_run as audit_start_run, stats as audit_stats
from .compressor import compress_context, compress_file, compress_text, estimate_tokens
from .attachments import attach_file, resolve_in_root, resolve_mentions, session_attachments
from .autochain import auto_learn, learn_note, recall_block
from .webforms import browser_mode, close_session, forms as web_forms, set_browser_mode, submit as web_submit
from .planning import TodoList, generate_plan, get_todo_list, load_plan, render_plan_text
from .reasoning import ReasoningTrace, ThoughtStep, STEP_KINDS
from .sandbox import SandboxExecutor, SandboxResult, get_sandbox_executor
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

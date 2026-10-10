"""Native AI provider layer for AZZX (v10.4).

Single home for everything the agent needs to talk to an AI provider:

- Typed error taxonomy (auth / rate-limit / timeout / malformed / outage / config)
  so callers can react appropriately instead of catching one flat exception.
- Provider adapters: OpenAI-compatible, Anthropic, Cohere.
- ``AIRouter``: ordered provider/key fallback, bounded retries with
  exponential backoff + jitter (never infinite), and cooperative
  cancellation via ``threading.Event``.
- ``MockAdapter``: deterministic in-process fake for the offline test suite.

Secrets: API keys are never logged. Error messages name the provider and the
failure class, never the key material.

This module was extracted from the historical ``azzx_cli.py`` monolith so the
agent layer (``azzx.agent.multi_agent`` etc.) can use the configured provider
without importing the CLI script. ``azzx_cli`` re-exports these names for
backwards compatibility.
"""
from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - hard dependency in practice
    httpx = None  # type: ignore[assignment]

from azzx.core import AzzxError


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base class for all provider failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return False

    @property
    def hint(self) -> str:
        return ""


class AuthenticationError(ProviderError):
    """401/403 or rejected key. Retrying will not help."""

    @property
    def hint(self) -> str:
        return "check the API key for this provider (`azzx ai` to reconfigure)"


class RateLimitError(ProviderError):
    """429 — quota or rate limit hit."""

    def __init__(self, message: str, status_code: int | None = 429, retry_after: float | None = None) -> None:
        super().__init__(message, status_code)
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "rate/quota limit reached — wait a bit, lower usage, or switch provider"


class ProviderTimeoutError(ProviderError):
    """The provider did not answer in time."""

    @property
    def retryable(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "provider timed out — check your network or raise the timeout in config"


class MalformedResponseError(ProviderError):
    """The provider answered, but the payload was not usable."""

    @property
    def hint(self) -> str:
        return "provider returned an unexpected response format"


class ProviderOutageError(ProviderError):
    """5xx or connection failure — the provider side is having trouble."""

    @property
    def retryable(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "provider appears to be down or unreachable — check network / status page"


class ProviderConfigError(ProviderError):
    """Local misconfiguration (missing base URL, model, or key)."""

    @property
    def hint(self) -> str:
        return "provider is misconfigured (`azzx ai` to fix base URL / model / key)"


class CancelledError(AzzxError):
    """Raised when a cooperative cancellation event fires mid-request."""


def classify_http_error(status_code: int, message: str) -> ProviderError:
    """Map an HTTP status to the most useful typed error."""
    if status_code in (401, 403):
        return AuthenticationError(f"HTTP {status_code}: {message}", status_code)
    if status_code == 429:
        return RateLimitError(f"HTTP 429: {message}", status_code)
    if 500 <= status_code < 600:
        return ProviderOutageError(f"HTTP {status_code}: {message}", status_code)
    return ProviderError(f"HTTP {status_code}: {message}", status_code)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def normalize_base_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def headers_for_provider(provider: dict[str, Any], api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    headers.update(provider.get("headers") or {})
    if api_key:
        # The key itself is only ever placed in the outgoing HTTP header;
        # it is never written to logs, traces, or error messages.
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def extract_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if value is None:
        return ""
    return str(value)


def _require_httpx() -> None:
    if httpx is None:
        raise ProviderConfigError(
            "The 'httpx' package is required for AI provider calls. "
            "Install it with: pip install httpx"
        )


def _wrap_transport_error(exc: Exception) -> ProviderError:
    """Classify httpx transport failures without leaking internals."""
    name = type(exc).__name__
    if "Timeout" in name:
        return ProviderTimeoutError(f"Request timed out: {exc}")
    if "Connect" in name or "Network" in name or "RemoteProtocol" in name:
        return ProviderOutageError(f"Could not reach provider: {exc}")
    return ProviderError(f"Transport error: {exc}")


def _check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("AI request cancelled by user")


def _sleep_interruptible(seconds: float, cancel_event: threading.Event | None) -> None:
    """Sleep in small slices so cancellation stays responsive."""
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        _check_cancelled(cancel_event)
        time.sleep(min(0.1, deadline - time.monotonic()))


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

class BaseAdapter:
    """One provider kind. Subclasses implement chat/stream_chat."""

    #: seconds added between retries is computed by the router, not here.
    def __init__(self, provider: dict[str, Any], api_key: str, timeout: float) -> None:
        self.provider = provider
        self.api_key = api_key
        self.base_url = normalize_base_url(provider.get("base_url", ""))
        self.timeout = timeout

    def _check_config(self, model: str) -> None:
        if not self.base_url:
            raise ProviderConfigError("Base URL is not configured.")
        if not model:
            raise ProviderConfigError("Model is not selected.")

    def list_models(self) -> list[str]:
        raise NotImplementedError

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        raise NotImplementedError

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[str]:
        """Yield text tokens as they arrive. Default: single full chunk."""
        yield self.chat(messages, model, cancel_event=cancel_event)

    def _raise_http(self, response: Any) -> None:
        if response.is_success:
            return
        try:
            body = response.json()
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or str(err)
                else:
                    msg = body.get("message") or str(body)
            else:
                msg = str(body)
        except Exception:
            msg = response.text[:800]
        raise classify_http_error(response.status_code, msg)


class OpenAICompatibleAdapter(BaseAdapter):
    def list_models(self) -> list[str]:
        _require_httpx()
        if not self.base_url:
            return []
        url = f"{self.base_url}/models"
        headers = headers_for_provider(self.provider, self.api_key)
        try:
            with httpx.Client(timeout=min(self.timeout, 30)) as client:
                response = client.get(url, headers=headers)
            self._raise_http(response)
            body = response.json()
        except ProviderError:
            raise
        except Exception as exc:
            raise _wrap_transport_error(exc) from exc

        rows = body.get("data") if isinstance(body, dict) else None
        if not isinstance(rows, list) and isinstance(body, dict):
            rows = body.get("models")
        result: list[str] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    mid = row.get("id") or row.get("name")
                    if mid:
                        result.append(str(mid))
                elif isinstance(row, str):
                    result.append(row)
        return sorted(set(result), key=str.lower)

    def chat(self, messages, model, max_tokens=None, cancel_event=None) -> str:
        _require_httpx()
        _check_cancelled(cancel_event)
        self._check_config(model)
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        headers = headers_for_provider(self.provider, self.api_key)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
            self._raise_http(response)
            body = response.json()
        except ProviderError:
            raise
        except Exception as exc:
            raise _wrap_transport_error(exc) from exc

        try:
            choice = body["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content")
            text = extract_text_content(content)
            if not text and "text" in choice:
                text = extract_text_content(choice.get("text"))
            if not text:
                raise KeyError("empty content")
            return text
        except (KeyError, IndexError, TypeError) as exc:
            raise MalformedResponseError(
                f"Unrecognized response format: {str(body)[:900]}"
            ) from exc

    def stream_chat(self, messages, model, cancel_event=None) -> Iterator[str]:
        """SSE token streaming for OpenAI-compatible /chat/completions."""
        _require_httpx()
        _check_cancelled(cancel_event)
        self._check_config(model)
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        headers = headers_for_provider(self.provider, self.api_key)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    self._raise_http(response)
                    for line in response.iter_lines():
                        _check_cancelled(cancel_event)
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        try:
                            delta = chunk["choices"][0].get("delta") or {}
                            token = extract_text_content(delta.get("content"))
                        except (KeyError, IndexError, TypeError):
                            continue
                        if token:
                            yield token
        except ProviderError:
            raise
        except CancelledError:
            raise
        except Exception as exc:
            raise _wrap_transport_error(exc) from exc


class AnthropicAdapter(BaseAdapter):
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def list_models(self) -> list[str]:
        _require_httpx()
        try:
            with httpx.Client(timeout=min(self.timeout, 30)) as client:
                response = client.get(f"{self.base_url}/v1/models", headers=self._headers())
            self._raise_http(response)
            rows = response.json().get("data", [])
            return sorted({str(x.get("id")) for x in rows if isinstance(x, dict) and x.get("id")})
        except ProviderError:
            raise
        except Exception as exc:
            raise _wrap_transport_error(exc) from exc

    def chat(self, messages, model, max_tokens=None, cancel_event=None) -> str:
        _require_httpx()
        _check_cancelled(cancel_event)
        self._check_config(model)
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        convo = [m for m in messages if m.get("role") in {"user", "assistant"}]
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": int(max_tokens) if max_tokens else 4096,
            "messages": convo,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/v1/messages", headers=self._headers(), json=payload
                )
            self._raise_http(response)
            body = response.json()
            content = body.get("content", [])
            text = extract_text_content(content)
            if not text:
                raise KeyError("empty content")
            return text
        except ProviderError:
            raise
        except (KeyError, IndexError, TypeError) as exc:
            raise MalformedResponseError(
                f"Unrecognized response format: {str(body)[:900]}"
            ) from exc
        except Exception as exc:
            raise _wrap_transport_error(exc) from exc


class CohereAdapter(BaseAdapter):
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def list_models(self) -> list[str]:
        _require_httpx()
        urls = [f"{self.base_url}/v1/models", f"{self.base_url}/v2/models"]
        last_error: Exception | None = None
        for url in urls:
            try:
                with httpx.Client(timeout=min(self.timeout, 30)) as client:
                    response = client.get(url, headers=self._headers())
                if not response.is_success:
                    last_error = classify_http_error(response.status_code, "model list failed")
                    continue
                body = response.json()
                rows = body.get("models") or body.get("data") or []
                models = []
                for row in rows:
                    if isinstance(row, dict):
                        mid = row.get("name") or row.get("id")
                        if mid:
                            models.append(str(mid))
                if models:
                    return sorted(set(models), key=str.lower)
            except Exception as exc:
                last_error = exc
        if last_error:
            raise ProviderError(str(last_error))
        return []

    def chat(self, messages, model, max_tokens=None, cancel_event=None) -> str:
        _require_httpx()
        _check_cancelled(cancel_event)
        self._check_config(model)
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/v2/chat", headers=self._headers(), json=payload
                )
            self._raise_http(response)
            body = response.json()
            message = body.get("message") or {}
            text = extract_text_content(message.get("content"))
            if not text:
                raise KeyError("empty content")
            return text
        except ProviderError:
            raise
        except (KeyError, IndexError, TypeError) as exc:
            raise MalformedResponseError(
                f"Unrecognized response format: {str(body)[:900]}"
            ) from exc
        except Exception as exc:
            raise _wrap_transport_error(exc) from exc


def adapter_for(provider: dict[str, Any], api_key: str, timeout: float) -> BaseAdapter:
    kind = provider.get("kind", "openai")
    if kind == "anthropic":
        return AnthropicAdapter(provider, api_key, timeout)
    if kind == "cohere":
        return CohereAdapter(provider, api_key, timeout)
    return OpenAICompatibleAdapter(provider, api_key, timeout)


class MockAdapter(BaseAdapter):
    """Deterministic in-process fake provider for the offline test suite.

    ``script`` maps a call index (or "default") to either a string response
    or an exception instance to raise. ``fail_with`` raises the same error
    on every call. No network, no keys, no cost.
    """

    def __init__(
        self,
        script: dict[Any, Any] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        super().__init__({"name": "mock", "kind": "openai"}, api_key="", timeout=5)
        self.script = dict(script or {})
        self.fail_with = fail_with
        self.calls: list[dict[str, Any]] = []

    def _next(self, messages: list[dict[str, str]], model: str) -> str:
        self.calls.append({"messages": messages, "model": model})
        if self.fail_with is not None:
            raise self.fail_with
        idx = len(self.calls) - 1
        outcome = self.script.get(idx, self.script.get("default", f"[mock:{model}] ok"))
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    def chat(self, messages, model, max_tokens=None, cancel_event=None) -> str:
        _check_cancelled(cancel_event)
        return self._next(messages, model)

    def stream_chat(self, messages, model, cancel_event=None) -> Iterator[str]:
        text = self._next(messages, model)
        for word in text.split(" "):
            _check_cancelled(cancel_event)
            yield word + " "


@dataclass
class RouteResult:
    text: str
    provider_id: str
    provider_name: str
    model: str
    key_index: int
    attempts: int = 1
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def _backoff_delay(attempt: int, retry_after: float | None = None) -> float:
    """Exponential backoff with jitter, capped. attempt is 0-based."""
    if retry_after is not None:
        return min(max(0.0, retry_after), 60.0)
    return min(2.0 ** attempt, 8.0) * (0.5 + random.random())


class AIRouter:
    """Ordered provider/key fallback with bounded retries and cancellation.

    - ``max_retries`` bounds *per key* retries for retryable errors
      (rate-limit / timeout / outage). Non-retryable errors (auth, config,
      malformed) fail over to the next key/provider immediately.
    - ``cancel_event`` (``threading.Event``) is honored between attempts and
      while streaming. An in-flight plain HTTP call still relies on the
      provider ``timeout`` — httpx offers no mid-request abort.
    """

    def __init__(
        self,
        cfg: dict[str, Any],
        providers: dict[str, dict[str, Any]],
        vault: Any,
        adapter_factory: Callable[[dict[str, Any], str, float], BaseAdapter] | None = None,
    ) -> None:
        self.cfg = cfg
        self.providers = providers
        self.vault = vault
        self._adapter_factory = adapter_factory or adapter_for

    @property
    def max_retries(self) -> int:
        try:
            return max(0, int(self.cfg.get("provider_max_retries", 2)))
        except (TypeError, ValueError):
            return 2

    def route_order(self, forced_provider: str | None = None) -> list[str]:
        if forced_provider:
            return [forced_provider]
        default = self.cfg.get("default_provider", "")
        priority = [x for x in self.cfg.get("provider_priority", []) if x in self.providers]
        order: list[str] = []
        if default and default in self.providers:
            order.append(default)
        for pid in priority:
            if pid not in order:
                order.append(pid)
        if self.cfg.get("fallback_enabled", True):
            for pid, provider in self.providers.items():
                if provider.get("enabled", True) and pid not in order:
                    order.append(pid)
        return order

    def provider_for_role(self, role: str) -> str | None:
        if not self.cfg.get("smart_routing", True):
            return None
        roles = self.cfg.get("role_providers") or {}
        pid = str(roles.get(role) or "").strip()
        return pid if pid in self.providers else None

    def _key_ids(self, provider: dict[str, Any]) -> list[str]:
        key_ids = list(provider.get("key_ids") or [])
        if not key_ids and not provider.get("requires_key", True):
            key_ids = [""]  # keyless local providers (e.g. Ollama)
        return key_ids

    def _describe_failure(self, errors: list[str]) -> str:
        if not errors:
            return (
                "No AI provider is configured. "
                "Run `azzx ai` to add a provider (OpenAI-compatible, Anthropic, "
                "Cohere, or a local Ollama server) and set an API key."
            )
        joined = "\n".join(f"- {e}" for e in errors[-12:])
        return f"All AI providers failed.\n{joined}"

    def chat(
        self,
        messages: list[dict[str, str]],
        forced_provider: str | None = None,
        cancel_event: threading.Event | None = None,
        max_tokens: int | None = None,
    ) -> RouteResult:
        errors: list[str] = []
        timeout = float(self.cfg.get("timeout_seconds", 120))
        order = self.route_order(forced_provider)
        if not order:
            raise AzzxError(self._describe_failure(errors))
        _check_cancelled(cancel_event)

        for pid in order:
            provider = self.providers.get(pid)
            if not provider or not provider.get("enabled", True):
                continue
            model = str(provider.get("model") or "")
            key_ids = self._key_ids(provider)
            if not key_ids:
                errors.append(f"{pid}: API key missing ({ProviderConfigError('').hint})")
                continue

            for idx, key_id in enumerate(key_ids, 1):
                api_key = self.vault.get(key_id) if key_id else ""
                if provider.get("requires_key", True) and not api_key:
                    errors.append(f"{pid} key#{idx}: API key is empty")
                    continue
                _check_cancelled(cancel_event)
                adapter = self._adapter_factory(provider, api_key, timeout)
                attempts = 0
                while True:
                    attempts += 1
                    _check_cancelled(cancel_event)
                    try:
                        text = adapter.chat(
                            messages, model,
                            max_tokens=max_tokens,
                            cancel_event=cancel_event,
                        )
                        return RouteResult(
                            text=text,
                            provider_id=pid,
                            provider_name=provider.get("name", pid),
                            model=model,
                            key_index=idx,
                            attempts=attempts,
                            errors=errors,
                        )
                    except CancelledError:
                        raise
                    except ProviderError as exc:
                        label = f"{provider.get('name', pid)} key#{idx}"
                        hint = f" — {exc.hint}" if exc.hint else ""
                        if exc.retryable and attempts <= self.max_retries:
                            delay = _backoff_delay(
                                attempts - 1,
                                getattr(exc, "retry_after", None),
                            )
                            errors.append(
                                f"{label}: {exc} (retry {attempts}/{self.max_retries + 1} in {delay:.1f}s)"
                            )
                            _sleep_interruptible(delay, cancel_event)
                            continue
                        errors.append(f"{label}: {exc}{hint}")
                        break  # next key / provider
        raise AzzxError(self._describe_failure(errors))

    def chat_role(
        self,
        messages: list[dict[str, str]],
        role: str,
        forced_provider: str | None = None,
        cancel_event: threading.Event | None = None,
        max_tokens: int | None = None,
    ) -> RouteResult:
        return self.chat(
            messages,
            forced_provider or self.provider_for_role(role),
            cancel_event=cancel_event,
            max_tokens=max_tokens,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        forced_provider: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[tuple[str, str]]:
        """Yield (provider_id, token) tuples with the same fallback routing.

        Retries apply only *before* the first token; once streaming has
        started, an error ends the stream for that provider.
        """
        errors: list[str] = []
        timeout = float(self.cfg.get("timeout_seconds", 120))
        order = self.route_order(forced_provider)
        if not order:
            raise AzzxError(self._describe_failure(errors))
        _check_cancelled(cancel_event)

        for pid in order:
            provider = self.providers.get(pid)
            if not provider or not provider.get("enabled", True):
                continue
            model = str(provider.get("model") or "")
            key_ids = self._key_ids(provider)
            if not key_ids:
                errors.append(f"{pid}: API key missing")
                continue

            for idx, key_id in enumerate(key_ids, 1):
                api_key = self.vault.get(key_id) if key_id else ""
                if provider.get("requires_key", True) and not api_key:
                    errors.append(f"{pid} key#{idx}: API key is empty")
                    continue
                _check_cancelled(cancel_event)
                adapter = self._adapter_factory(provider, api_key, timeout)
                attempts = 0
                while True:
                    attempts += 1
                    _check_cancelled(cancel_event)
                    token_iter = adapter.stream_chat(messages, model, cancel_event=cancel_event)
                    try:
                        first = next(token_iter)
                    except StopIteration:
                        return  # empty stream: treat as success with no tokens
                    except CancelledError:
                        raise
                    except ProviderError as exc:
                        hint = f" — {exc.hint}" if exc.hint else ""
                        if exc.retryable and attempts <= self.max_retries:
                            _sleep_interruptible(
                                _backoff_delay(attempts - 1, getattr(exc, "retry_after", None)),
                                cancel_event,
                            )
                            continue
                        errors.append(f"{provider.get('name', pid)} key#{idx}: {exc}{hint}")
                        break
                    # First token arrived — commit to this provider.
                    yield pid, first
                    try:
                        for token in token_iter:
                            yield pid, token
                    except CancelledError:
                        raise
                    except ProviderError as exc:
                        errors.append(f"{provider.get('name', pid)} key#{idx} (mid-stream): {exc}")
                    return
        raise AzzxError(self._describe_failure(errors))


def default_router(
    adapter_factory: Callable[[dict[str, Any], str, float], BaseAdapter] | None = None,
) -> AIRouter:
    """Build an AIRouter from the user's configured providers and vault.

    Imports the CLI config helpers lazily so this module stays importable
    without the CLI script (no import cycle).
    """
    import azzx_cli  # lazy: azzx_cli imports this module at its top level

    return AIRouter(
        azzx_cli.load_config(),
        azzx_cli.load_providers(),
        azzx_cli.SecretVault(),
        adapter_factory=adapter_factory,
    )


__all__ = [
    "ProviderError",
    "AuthenticationError",
    "RateLimitError",
    "ProviderTimeoutError",
    "MalformedResponseError",
    "ProviderOutageError",
    "ProviderConfigError",
    "CancelledError",
    "classify_http_error",
    "normalize_base_url",
    "headers_for_provider",
    "extract_text_content",
    "BaseAdapter",
    "OpenAICompatibleAdapter",
    "AnthropicAdapter",
    "CohereAdapter",
    "adapter_for",
    "MockAdapter",
    "RouteResult",
    "AIRouter",
    "default_router",
]

"""Token compressor for AZZX (v10.6.1): shrink big files before they enter
the AI context.

Problem: ``azzx ask`` feeds whole files to the provider. A 5.000-line file
eats the context window and costs tokens. This module condenses text
*intelligently* instead of the old crude head-truncation.

Strategies:
- ``signatures`` — Python via ``ast``: keeps module docstring, imports, and
  every class/function signature + docstring. Bodies are dropped. Typical
  savings: 70-90% on code, structure fully preserved.
- ``extractive`` — keeps the highest-scoring lines for a query (keyword
  overlap), in original order. Good for logs and docs.
- ``head_tail`` — keeps the beginning and end with a cut marker. Good default
  for unknown formats.
- ``summarize`` — asks the provider for a summary (costs tokens to save
  tokens; only worth it for very large prose).
- ``auto`` — ``.py`` → ``signatures``; with a query → ``extractive``;
  otherwise → ``head_tail``.

``estimate_tokens`` uses the chars/4 heuristic — documented as an estimate,
not a tokenizer.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from azzx.core import AzzxError


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4). Heuristic, not a real tokenizer."""
    return max(1, len(text or "") // 4)


def _signatures_compress(source: str, budget: int) -> str:
    """AST-based: signatures + docstrings only."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _head_tail_compress(source, budget)
    out: list[str] = []
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        out.append(f'"""{mod_doc[:500]}"""')
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            try:
                out.append(ast.unparse(node))
            except Exception:
                pass
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = _format_args(node.args)
            kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            doc = ast.get_docstring(node)
            line = f"{kind} {node.name}({args}):"
            if doc:
                line += f'\n    """{doc[:200]}"""'
            out.append(line)
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(_unparse_safe(b) for b in node.bases)
            if bases:
                out.append(f"class {node.name}({bases}):")
            else:
                out.append(f"class {node.name}:")
            doc = ast.get_docstring(node)
            if doc:
                out.append(f'    """{doc[:200]}"""')
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = _format_args(sub.args)
                    kind = "async def" if isinstance(sub, ast.AsyncFunctionDef) else "def"
                    sdoc = ast.get_docstring(sub)
                    sline = f"    {kind} {sub.name}({args}):"
                    if sdoc:
                        sline += f' """{sdoc[:120]}"""'
                    out.append(sline)
    text = "\n".join(out)
    if len(text) > budget:
        return _head_tail_compress(text, budget)
    return text or _head_tail_compress(source, budget)


def _unparse_safe(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def _format_args(args: ast.arguments) -> str:
    parts = [a.arg for a in args.posonlyargs] + [a.arg for a in args.args]
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    parts += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    return ", ".join(parts)


def _head_tail_compress(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    marker = "\n…[compressed by AZZX: middle removed]…\n"
    keep = max(0, budget - len(marker))
    head = int(keep * 0.6)
    tail = keep - head
    return text[:head] + marker + (text[len(text) - tail:] if tail else "")


def _extractive_compress(text: str, budget: int, query: str) -> str:
    lines = text.splitlines()
    if len(text) <= budget:
        return text
    terms = [t.lower() for t in re.findall(r"\w{3,}", query or "")]
    scored: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        score = sum(low.count(t) * 3 for t in terms)
        # information density bonus: code-ish lines, headers, list items
        if re.match(r"^(def |class |#|##|[-*] |\d+\. )", s):
            score += 2
        if len(s) > 20:
            score += 1
        scored.append((score, i, line))
    # Always keep some head context.
    keep_n = max(5, budget // 120)
    head_idx = {i for i in range(min(8, len(lines)))}
    scored.sort(key=lambda t: (-t[0], t[1]))
    chosen = set(head_idx)
    used = sum(len(lines[i]) + 1 for i in chosen)
    for score, i, line in scored:
        if i in chosen:
            continue
        cost = len(line) + 1
        if used + cost > budget:
            break
        chosen.add(i)
        used += cost
        if len(chosen) >= keep_n and score == 0:
            break
    picked = sorted(chosen)
    out: list[str] = []
    prev = -2
    for i in picked:
        if i > prev + 1 and out:
            out.append("…")
        out.append(lines[i])
        prev = i
    return "\n".join(out)


def _summarize_compress(text: str, budget: int, query: str = "") -> str:
    from azzx.agent.providers import default_router
    router = default_router()
    target = max(200, budget)
    try:
        result = router.chat([
            {"role": "system", "content":
             "Summarize the following text concisely, preserving facts, names, "
             "numbers, and structure. Reply with the summary only."},
            {"role": "user", "content":
             (f"Focus on: {query}\n\n" if query else "") + text[:12000]},
        ], max_tokens=min(2000, target // 3))
        summary = result.text.strip()
    except Exception as exc:
        raise AzzxError(f"summarize needs an AI provider: {exc}")
    if len(summary) > budget:
        summary = _head_tail_compress(summary, budget)
    return f"[LLM summary — original {len(text)} chars]\n{summary}"


def compress_text(text: str, budget_chars: int = 8000, strategy: str = "auto",
                  query: str = "", filename: str = "") -> dict[str, Any]:
    """Compress text to fit budget_chars. Returns text + stats."""
    text = text or ""
    budget_chars = max(500, int(budget_chars or 8000))
    strategy = (strategy or "auto").lower()
    if strategy not in ("auto", "signatures", "extractive", "head_tail", "summarize"):
        raise AzzxError(f"unknown strategy: {strategy}")

    if len(text) <= budget_chars:
        used = "none (already fits)"
        out = text
    else:
        strat = strategy
        if strat == "auto":
            if filename.endswith(".py"):
                strat = "signatures"
            elif query:
                strat = "extractive"
            else:
                strat = "head_tail"
        if strat == "signatures" and not filename.endswith(".py"):
            strat = "extractive" if query else "head_tail"
        if strat == "signatures":
            out = _signatures_compress(text, budget_chars)
        elif strat == "extractive":
            out = _extractive_compress(text, budget_chars, query)
        elif strat == "summarize":
            out = _summarize_compress(text, budget_chars, query)
        else:
            out = _head_tail_compress(text, budget_chars)
        used = strat

    return {
        "text": out,
        "strategy": used,
        "original_chars": len(text),
        "compressed_chars": len(out),
        "original_tokens_est": estimate_tokens(text),
        "compressed_tokens_est": estimate_tokens(out),
        "ratio": round(len(out) / len(text), 3) if text else 1.0,
    }


def compress_file(path: str | Path, budget_chars: int = 8000,
                   strategy: str = "auto", query: str = "") -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_file():
        raise AzzxError(f"file not found: {path}")
    if p.stat().st_size > 20 * 1024 * 1024:
        raise AzzxError("file too large (>20 MiB)")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise AzzxError(f"cannot read {path}: {exc}")
    res = compress_text(text, budget_chars, strategy, query, filename=p.name)
    res["file"] = str(p)
    return res


def compress_context(files: list[str | Path], budget_chars: int = 24000,
                     query: str = "") -> dict[str, Any]:
    """Compress several files into a shared budget. Returns combined text."""
    files = [Path(f) for f in files]
    per_file = max(1000, budget_chars // max(1, len(files)))
    parts: list[str] = []
    total_orig = total_comp = 0
    for f in files:
        try:
            res = compress_file(f, per_file, "auto", query)
        except Exception:
            continue
        total_orig += res["original_chars"]
        total_comp += res["compressed_chars"]
        parts.append(f"\n===== FILE: {f} (compressed: {res['strategy']}, "
                     f"{res['ratio']*100:.0f}% of original) =====\n"
                     f"{res['text']}\n===== END FILE: {f} =====")
    text = "\n".join(parts)
    return {
        "text": text,
        "files": len(parts),
        "original_chars": total_orig,
        "compressed_chars": total_comp,
        "original_tokens_est": total_orig // 4,
        "compressed_tokens_est": total_comp // 4,
        "ratio": round(total_comp / total_orig, 3) if total_orig else 1.0,
    }

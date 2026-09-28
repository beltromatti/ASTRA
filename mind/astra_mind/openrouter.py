"""Client asincrono per OpenRouter con streaming, tool calling e misura dei tempi.

Misura per ogni richiesta: primo byte, primo token, nome del primo strumento,
argomenti completi e fine; riporta uso e costo dichiarati da OpenRouter.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .env import require

API_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class ToolCall:
    name: str = ""
    arguments_raw: str = ""

    def arguments(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.arguments_raw) if self.arguments_raw else {}
        except json.JSONDecodeError:
            return None


@dataclass
class Completion:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    t_first_byte: float | None = None
    t_first_token: float | None = None
    t_first_tool_name: float | None = None
    t_end: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    error: str = ""
    finish_reason: str = ""


class OpenRouter:
    """Sessione HTTP/2 persistente verso OpenRouter (connessione riutilizzata)."""

    def __init__(self, timeout: float = 60.0) -> None:
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "Authorization": f"Bearer {require('OPENROUTER_API_KEY')}",
                "HTTP-Referer": "https://github.com/beltromatti/ASTRA",
                "X-Title": "ASTRA",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = "auto",
        providers: list[str] | None = None,
        reasoning: dict[str, Any] | None = None,
        max_tokens: int = 500,
        temperature: float | None = 0.3,
        extra: dict[str, Any] | None = None,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "usage": {"include": True},
        }
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            # niente "parallel_tool_calls": nessun provider lo dichiara e, con
            # require_parameters, farebbe scartare tutti gli endpoint
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        if providers:
            body["provider"] = {"order": providers, "allow_fallbacks": False, "require_parameters": True}
        if reasoning is not None:
            body["reasoning"] = reasoning
        if extra:
            body.update(extra)

        out = Completion(model=model)
        calls: dict[int, ToolCall] = {}
        t0 = time.perf_counter()
        try:
            async with self._client.stream("POST", API_URL, json=body) as resp:
                if resp.status_code != 200:
                    text = (await resp.aread()).decode("utf-8", "replace")
                    out.error = f"HTTP {resp.status_code}: {text[:300]}"
                    return out
                async for line in resp.aiter_lines():
                    if out.t_first_byte is None:
                        out.t_first_byte = time.perf_counter() - t0
                    if not line.startswith("data:"):
                        continue  # commenti SSE (": OPENROUTER PROCESSING") e righe vuote
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        out.error = json.dumps(chunk["error"])[:300]
                        break
                    out.provider = chunk.get("provider", out.provider)
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            if out.t_first_token is None:
                                out.t_first_token = time.perf_counter() - t0
                            out.content += delta["content"]
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            call = calls.setdefault(idx, ToolCall())
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                call.name += fn["name"]
                                if out.t_first_tool_name is None:
                                    out.t_first_tool_name = time.perf_counter() - t0
                                if out.t_first_token is None:
                                    out.t_first_token = out.t_first_tool_name
                            if fn.get("arguments"):
                                call.arguments_raw += fn["arguments"]
                        if choice.get("finish_reason"):
                            out.finish_reason = choice["finish_reason"]
                    usage = chunk.get("usage")
                    if usage:
                        out.prompt_tokens = usage.get("prompt_tokens", 0) or 0
                        out.completion_tokens = usage.get("completion_tokens", 0) or 0
                        out.cost = float(usage.get("cost") or 0.0)
                        out.cached_tokens = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
                        out.reasoning_tokens = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            out.error = f"{type(exc).__name__}: {exc}"[:300]
        out.t_end = time.perf_counter() - t0
        out.tool_calls = [calls[i] for i in sorted(calls)]
        return out


async def credits() -> dict[str, float]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get("https://openrouter.ai/api/v1/credits",
                                headers={"Authorization": f"Bearer {require('OPENROUTER_API_KEY')}"})
        data = resp.json().get("data", {})
        return {"total": float(data.get("total_credits", 0)), "used": float(data.get("total_usage", 0))}

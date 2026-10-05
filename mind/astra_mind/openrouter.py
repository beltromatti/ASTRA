"""Client asincrono per OpenRouter con streaming, tool calling e misura dei tempi.

Misura per ogni richiesta: primo byte, primo token, nome del primo strumento,
argomenti completi e fine; riporta uso e costo dichiarati da OpenRouter.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .env import require

API_URL = "https://openrouter.ai/api/v1/chat/completions"
log = logging.getLogger("astra.openrouter")


@dataclass
class ToolCall:
    name: str = ""
    arguments_raw: str = ""
    id: str = ""

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
        # the key is read for every request (the player may enter or replace it in the game while the mind runs: env.reload_env)
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "HTTP-Referer": "https://github.com/beltromatti/ASTRA",
                "X-Title": "ASTRA",
            },
        )
        self.state = "ok"                          # what the game is told of the service: ok · invalid_key · no_credit · rate_limited · offline
        self.on_status: Any = None                 # (state, detail) -> None: called when the state changes (server.py tells the game)

    def _status(self, state: str, detail: str = "") -> None:
        if state != self.state:
            self.state = state
            log.warning("OpenRouter: %s %s", state, detail[:160]) if state != "ok" else log.info("OpenRouter: answering again")
            if self.on_status is not None:
                try:
                    self.on_status(state, detail)
                except Exception:  # noqa: BLE001
                    log.exception("the status hook failed")

    @staticmethod
    def _key_header() -> dict[str, str]:
        try:
            return {"Authorization": f"Bearer {require('OPENROUTER_API_KEY')}"}
        except RuntimeError:
            return {}

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
        on_tool_call: Any = None,
        allow_fallbacks: bool = False,
        max_price: tuple[float, float] | None = None,
        first_token_timeout: float | None = None,
    ) -> Completion:
        """Streaming chat. `on_tool_call(ToolCall)` (sync or async) fires as soon as each tool call's arguments are
        complete, before the rest of the reply has arrived: speech can start while the model is still writing.
        max_price: ($ per M input, $ per M output) ceiling for whatever provider OpenRouter picks (also on a fallback).
        first_token_timeout: seconds to wait for the first token or tool call; past it the request is dropped and
        `error` starts with "stall" (the caller may retry: nothing was spoken or done)."""
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
        if providers or max_price:
            prov: dict[str, Any] = {"allow_fallbacks": allow_fallbacks, "require_parameters": True}
            if providers:
                prov["order"] = providers
            if max_price:
                prov["max_price"] = {"prompt": max_price[0], "completion": max_price[1]}
            body["provider"] = prov
        if reasoning is not None:
            body["reasoning"] = reasoning
        if extra:
            body.update(extra)

        out = Completion(model=model)
        calls: dict[int, ToolCall] = {}
        fired: set[int] = set()
        t0 = time.perf_counter()

        async def fire(upto_exclusive: int | None) -> None:
            if on_tool_call is None:
                return
            for i in sorted(calls):
                if i in fired or (upto_exclusive is not None and i >= upto_exclusive):
                    continue
                if calls[i].arguments() is None:
                    continue
                fired.add(i)
                r = on_tool_call(calls[i])
                if hasattr(r, "__await__"):
                    await r
        auth = self._key_header()
        if not auth:
            out.error = "no OpenRouter key"
            self._status("invalid_key", "no key in the .env")
            return out
        try:
            async with self._client.stream("POST", API_URL, json=body, headers=auth) as resp:
                if resp.status_code != 200:
                    text = (await resp.aread()).decode("utf-8", "replace")
                    out.error = f"HTTP {resp.status_code}: {text[:300]}"
                    if resp.status_code in (401, 403):
                        self._status("invalid_key", text[:200])
                    elif resp.status_code == 402:
                        self._status("no_credit", text[:200])
                    elif resp.status_code == 429:
                        self._status("rate_limited", text[:200])
                    return out
                self._status("ok")
                lines = resp.aiter_lines().__aiter__()
                while True:
                    try:
                        if first_token_timeout and out.t_first_token is None:
                            line = await asyncio.wait_for(lines.__anext__(), timeout=max(0.05, first_token_timeout - (time.perf_counter() - t0)))
                        else:
                            line = await lines.__anext__()
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        out.error = f"stall: no first token in {first_token_timeout:.1f} s"
                        break
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
                            if idx not in calls and calls:
                                await fire(idx)          # a new call started: the previous ones are complete
                            call = calls.setdefault(idx, ToolCall())
                            if tc.get("id") and not call.id:
                                call.id = tc["id"]
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
            if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError)):
                self._status("offline", out.error)
        if not out.error:
            await fire(None)
        out.t_end = time.perf_counter() - t0
        out.tool_calls = [calls[i] for i in sorted(calls)]
        return out


async def credits() -> dict[str, float]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get("https://openrouter.ai/api/v1/credits", headers=OpenRouter._key_header())
        data = resp.json().get("data", {})
        return {"total": float(data.get("total_credits", 0)), "used": float(data.get("total_usage", 0))}

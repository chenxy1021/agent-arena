"""OpenAI-compatible API model adapter with live streamed output."""

from __future__ import annotations

import json
import random
import re
import socket
import time
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .agent import CallResult

OutputCallback = Callable[[str], None]


class _RunCancelled(Exception):
    def __init__(self, text: str):
        super().__init__("用户中止")
        self.text = text


def _is_cancelled(cancel_hook: Any) -> bool:
    if cancel_hook is None:
        return False
    try:
        return bool(cancel_hook.is_set())
    except AttributeError:
        return bool(cancel_hook)


def completions_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/chat/completions"


def _delta_text(payload: dict) -> tuple[str, str]:
    choices = payload.get("choices") or []
    if not choices:
        return "", ""
    choice = choices[0] or {}
    delta = choice.get("delta") or choice.get("message") or {}
    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
    content = delta.get("content") or ""
    return str(reasoning), str(content)


def _read_stream(
    lines: Iterable[bytes | str],
    on_output: OutputCallback | None,
    usage: dict[str, int] | None = None,
    cancel_hook: Any = None,
) -> str:
    reasoning_parts: list[str] = []
    content_parts: list[str] = []
    for raw_line in lines:
        if _is_cancelled(cancel_hook):
            raise _RunCancelled("".join(content_parts) or "".join(reasoning_parts))
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        reasoning, content = _delta_text(payload)
        if reasoning:
            reasoning_parts.append(reasoning)
            if on_output:
                on_output(reasoning)
        if content:
            content_parts.append(content)
            if on_output:
                on_output(content)
        if usage is not None:
            _collect_usage(payload, usage)
    return "".join(content_parts) or "".join(reasoning_parts)


def _collect_usage(payload: dict, usage: dict[str, int]) -> None:
    """把流式响应里的 usage 字段累加进 usage（部分服务商只在最后一帧返回）。"""
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = raw.get(key)
        if isinstance(value, (int, float)):
            usage[key] = max(usage.get(key, 0), int(value))


def _error_message(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        detail = data.get("error")
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("code")
        return str(detail or body)[:400]
    except Exception:
        return str(error.reason or error)[:400]


class ApiModelAgent:
    """A user-configured model exposed through an OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        config_id: int,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str = "",
        temperature: float | None = None,
    ):
        self.config_id = config_id
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt.strip()
        self.temperature = temperature
        self.version = model
        self.path = completions_url(base_url)

    @property
    def label(self) -> str:
        return self.model

    def __repr__(self) -> str:
        return f"<ApiModelAgent {self.name} {self.model}>"

    def ask(
        self,
        prompt: str,
        timeout: float = 240,
        retries: int = 1,
        on_output: OutputCallback | None = None,
        cancel_hook: Any = None,
    ) -> CallResult:
        last_error = ""
        for _ in range(retries + 1):
            if _is_cancelled(cancel_hook):
                return CallResult(cancelled=True)
            started = time.monotonic()
            try:
                usage: dict[str, int] = {}
                text = self._invoke(prompt, timeout, on_output, usage, cancel_hook)
                return CallResult(
                    text=text.strip(),
                    elapsed=time.monotonic() - started,
                    usage=usage,
                )
            except _RunCancelled as exc:
                return CallResult(
                    text=exc.text.strip(),
                    elapsed=time.monotonic() - started,
                    cancelled=True,
                )
            except HTTPError as exc:
                last_error = f"API {exc.code}：{_error_message(exc)}"
                if exc.code < 500 and exc.code != 429:
                    break
            except (TimeoutError, socket.timeout):
                return CallResult(error=f"超时（>{timeout:.0f}s）", elapsed=time.monotonic() - started)
            except URLError as exc:
                last_error = f"连接失败：{exc.reason}"
            except Exception as exc:
                last_error = str(exc) or type(exc).__name__
        return CallResult(error=last_error or "未知错误")

    def _invoke(
        self,
        prompt: str,
        timeout: float,
        on_output: OutputCallback | None,
        usage: dict[str, int] | None = None,
        cancel_hook: Any = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature

        request = Request(
            completions_url(self.base_url),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                return _read_stream(response, on_output, usage, cancel_hook)
            raw = response.read().decode("utf-8", errors="replace")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return _read_stream(raw.splitlines(), on_output, usage)
        reasoning, content = _delta_text(payload)
        if usage is not None:
            _collect_usage(payload, usage)
        text = content or reasoning
        if text and on_output:
            on_output(text)
        return text


def suggest_display_name(agent: ApiModelAgent, timeout: float = 30) -> str:
    """Ask a configured model for a short display name; this also tests connectivity."""
    prompt = random.choice((
        "请给自己起一个 2-8 个字的中文显示名，只回复名称，不要解释。",
        "为一个 AI 辩手取一个 2-8 个字的中文名字，只回复名称。",
        "给这个模型取一个简洁的中文名字，只回复名称，不要标点。",
    ))
    result = agent.ask(prompt, timeout=timeout, retries=0)
    if result.error:
        raise ValueError(f"连通性测试失败：{result.error}")
    raw = result.text.strip()
    quoted = re.search(r"[「『“\"']([^」』”\"']{1,40})[」』”\"']", raw)
    named = re.search(r"(?:我叫|名字是|命名为)[:：\s]*([^\s，。,.!?！？]{1,40})", raw)
    first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    name = (quoted or named).group(1) if (quoted or named) else first_line
    name = name.strip("\"'“”‘’《》「」『』【】 ").removeprefix("名称：").strip()
    if not name:
        raise ValueError("模型返回了空名称")
    return name[:40]

"""OpenAI-compatible API model adapter with live streamed output."""

from __future__ import annotations

import json
import socket
import time
from types import SimpleNamespace
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .adapters import CallResult

OutputCallback = Callable[[str], None]


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


def _read_stream(lines: Iterable[bytes | str], on_output: OutputCallback | None) -> str:
    reasoning_parts: list[str] = []
    content_parts: list[str] = []
    for raw_line in lines:
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
    return "".join(content_parts) or "".join(reasoning_parts)


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
        self.spec = SimpleNamespace(key=name, label=model, note="OpenAI-compatible API")
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
        workdir=None,
        timeout: float = 240,
        retries: int = 1,
        on_output: OutputCallback | None = None,
    ) -> CallResult:
        last_error = ""
        for _ in range(retries + 1):
            started = time.monotonic()
            try:
                text = self._invoke(prompt, timeout, on_output)
                return CallResult(text=text.strip(), elapsed=time.monotonic() - started)
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
        self, prompt: str, timeout: float, on_output: OutputCallback | None
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
                return _read_stream(response, on_output)
            raw = response.read().decode("utf-8", errors="replace")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return _read_stream(raw.splitlines(), on_output)
        reasoning, content = _delta_text(payload)
        text = content or reasoning
        if text and on_output:
            on_output(text)
        return text


def suggest_display_name(agent: ApiModelAgent, timeout: float = 30) -> str:
    """Ask a configured model for a short display name; this also tests connectivity."""
    prompt = "请给自己取一个名字。只输出名字，不要解释。"
    result = agent.ask(prompt, timeout=timeout, retries=0)
    if result.error:
        raise ValueError(f"连通性测试失败：{result.error}")
    first_line = next((line.strip() for line in result.text.splitlines() if line.strip()), "")
    name = first_line.strip("\"'“”‘’《》「」【】 ").removeprefix("名称：").strip()
    if not name:
        raise ValueError("模型返回了空名称")
    return name[:40]

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from apps.arena.agent import CallResult
from apps.arena.providers import ApiModelAgent, _read_stream, completions_url, suggest_display_name


class ProviderStreamTest(unittest.TestCase):
    def test_stream_emits_reasoning_and_returns_content(self) -> None:
        chunks: list[str] = []
        lines = [
            "data: " + json.dumps(
                {"choices": [{"delta": {"reasoning_content": "先分析"}}]},
                ensure_ascii=False,
            ),
            "data: " + json.dumps(
                {"choices": [{"delta": {"content": "最终"}}]},
                ensure_ascii=False,
            ),
            "data: " + json.dumps(
                {"choices": [{"delta": {"content": "回答"}}]},
                ensure_ascii=False,
            ),
            "data: [DONE]",
        ]

        text = _read_stream(lines, chunks.append)

        self.assertEqual(text, "最终回答")
        self.assertEqual("".join(chunks), "先分析最终回答")


class ProviderUrlTest(unittest.TestCase):
    def test_base_urls_resolve_to_chat_completions(self) -> None:
        self.assertEqual(
            completions_url("https://api.openai.com/v1"),
            "https://api.openai.com/v1/chat/completions",
        )
        self.assertEqual(
            completions_url("https://example.com/v1/chat/completions"),
            "https://example.com/v1/chat/completions",
        )


class SuggestDisplayNameTest(unittest.TestCase):
    def test_cleans_model_name_response(self) -> None:
        class FakeAgent:
            prompt = ""

            def ask(self, *_args, **_kwargs):
                self.prompt = _args[0]
                return CallResult(text="「星河辩手」", elapsed=0)

        agent = FakeAgent()
        self.assertEqual(suggest_display_name(agent), "星河辩手")
        self.assertNotIn("辩论赛", agent.prompt)
        self.assertNotIn("2-12", agent.prompt)
        self.assertNotIn("只输出", agent.prompt)

    def test_extracts_name_from_natural_reply(self) -> None:
        class FakeAgent:
            def ask(self, *_args, **_kwargs):
                return CallResult(text="我想叫「云岚」，因为这个名字比较轻。", elapsed=0)

        self.assertEqual(suggest_display_name(FakeAgent()), "云岚")

    def test_reports_connectivity_error(self) -> None:
        class FailingAgent:
            def ask(self, *_args, **_kwargs):
                return CallResult(error="API 401：unauthorized")

        with self.assertRaisesRegex(ValueError, "连通性测试失败"):
            suggest_display_name(FailingAgent())


class ApiModelAgentTest(unittest.TestCase):
    def test_streaming_chat_completion(self) -> None:
        received: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                received["path"] = self.path
                received["auth"] = self.headers.get("Authorization", "")
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(
                    b'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n'
                )
                self.wfile.write(
                    b'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
                )
                self.wfile.write(b"data: [DONE]\n\n")

            def log_message(self, *_args) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        chunks: list[str] = []
        agent = ApiModelAgent(
            config_id=1,
            name="模型A",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key="secret",
            model="test-model",
        )
        result = agent.ask("hi", timeout=2, retries=0, on_output=chunks.append)

        self.assertFalse(result.error)
        self.assertEqual(result.text, "hello world")
        self.assertEqual("".join(chunks), "hello world")
        self.assertEqual(received["path"], "/v1/chat/completions")
        self.assertEqual(received["auth"], "Bearer secret")


if __name__ == "__main__":
    unittest.main()

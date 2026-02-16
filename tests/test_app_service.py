from __future__ import annotations

import threading
import time
from typing import Any
from unittest import mock
import unittest

from slack_codex_bridge.app import (
    CodexCommandService,
    QUEUE_FULL_TEXT,
    _ephemeral,
    _is_allowed,
    build_worker,
    create_app,
    generate_job_id,
    usage_text,
    unauthorized_text,
)
from slack_codex_bridge.codex_runner import CodexResult
from slack_codex_bridge.config import Settings
from slack_codex_bridge.worker import CodexJob


def _noop_run_fn(_prompt: str) -> CodexResult:
    return {
        "ok": True,
        "output_text": "",
        "error_type": None,
        "error_detail": None,
        "exit_code": 0,
        "duration_ms": 0,
    }


class StubWorker:
    def __init__(self, *, should_enqueue: bool) -> None:
        self.should_enqueue = should_enqueue
        self.jobs: list[CodexJob] = []

    def enqueue(self, job: CodexJob) -> bool:
        if not self.should_enqueue:
            return False
        self.jobs.append(job)
        return True


def _settings(**overrides: Any) -> Settings:
    base = {
        "slack_app_token": "xapp-test",
        "slack_bot_token": "xoxb-test",
        "slack_signing_secret": "",
        "codex_bin": "codex",
        "codex_args": ("exec",),
        "codex_timeout_seconds": 300,
        "codex_workdir": ".",
        "claude_bin": "claude",
        "claude_args": ("-p",),
        "claude_timeout_seconds": 300,
        "claude_workdir": ".",
        "max_prompt_chars": 4000,
        "max_output_chars": 3500,
        "queue_max_size": 20,
        "worker_concurrency": 1,
        "allowed_user_ids": frozenset(),
        "allowed_channel_ids": frozenset(),
    }
    base.update(overrides)
    return Settings(**base)


def _ack_text(payload: dict[str, str]) -> str:
    return payload["text"]


class AppServiceTests(unittest.TestCase):
    def test_empty_prompt_returns_usage(self) -> None:
        acks: list[dict[str, str]] = []
        worker = StubWorker(should_enqueue=True)
        service = CodexCommandService(settings=_settings(), worker=worker)

        service.handle_command(
            command="codex",
            run_fn=_noop_run_fn,
            body={"text": "   ", "user_id": "U1", "channel_id": "C1"},
            ack=acks.append,
            post_message=lambda _channel, _text: None,
        )

        self.assertEqual(len(acks), 1)
        self.assertEqual(_ack_text(acks[0]), usage_text("codex"))
        self.assertEqual(worker.jobs, [])

    def test_empty_prompt_returns_claude_usage(self) -> None:
        acks: list[dict[str, str]] = []
        worker = StubWorker(should_enqueue=True)
        service = CodexCommandService(settings=_settings(), worker=worker)

        service.handle_command(
            command="claude",
            run_fn=_noop_run_fn,
            body={"text": "", "user_id": "U1", "channel_id": "C1"},
            ack=acks.append,
            post_message=lambda _channel, _text: None,
        )

        self.assertEqual(len(acks), 1)
        self.assertEqual(_ack_text(acks[0]), "Usage: /claude <prompt>")

    def test_queue_full_rejects_command(self) -> None:
        acks: list[dict[str, str]] = []
        worker = StubWorker(should_enqueue=False)
        service = CodexCommandService(settings=_settings(), worker=worker)

        service.handle_command(
            command="codex",
            run_fn=_noop_run_fn,
            body={"text": "run this", "user_id": "U1", "channel_id": "C1"},
            ack=acks.append,
            post_message=lambda _channel, _text: None,
        )

        self.assertEqual(len(acks), 1)
        self.assertEqual(_ack_text(acks[0]), QUEUE_FULL_TEXT)

    def test_prompt_length_validation(self) -> None:
        acks: list[dict[str, str]] = []
        worker = StubWorker(should_enqueue=True)
        service = CodexCommandService(
            settings=_settings(max_prompt_chars=5),
            worker=worker,
        )

        service.handle_command(
            command="codex",
            run_fn=_noop_run_fn,
            body={"text": "123456", "user_id": "U1", "channel_id": "C1"},
            ack=acks.append,
            post_message=lambda _channel, _text: None,
        )

        self.assertEqual(len(acks), 1)
        self.assertEqual(_ack_text(acks[0]), "Prompt exceeds 5 characters.")

    def test_unauthorized_text_reflects_command(self) -> None:
        acks: list[dict[str, str]] = []
        worker = StubWorker(should_enqueue=True)
        service = CodexCommandService(
            settings=_settings(allowed_user_ids=frozenset({"U99"})),
            worker=worker,
        )

        service.handle_command(
            command="claude",
            run_fn=_noop_run_fn,
            body={"text": "hello", "user_id": "U1", "channel_id": "C1"},
            ack=acks.append,
            post_message=lambda _channel, _text: None,
        )

        self.assertEqual(len(acks), 1)
        self.assertEqual(_ack_text(acks[0]), unauthorized_text("claude"))

    def test_job_carries_run_fn(self) -> None:
        worker = StubWorker(should_enqueue=True)
        service = CodexCommandService(settings=_settings(), worker=worker)

        service.handle_command(
            command="claude",
            run_fn=_noop_run_fn,
            body={"text": "hello", "user_id": "U1", "channel_id": "C1"},
            ack=lambda _: None,
            post_message=lambda _channel, _text: None,
        )

        self.assertEqual(len(worker.jobs), 1)
        self.assertIs(worker.jobs[0].run_fn, _noop_run_fn)

    def test_command_ack_then_eventual_response(self) -> None:
        def fake_run_codex(_: str) -> CodexResult:
            time.sleep(0.05)
            return {
                "ok": True,
                "output_text": "deterministic output",
                "error_type": None,
                "error_detail": None,
                "exit_code": 0,
                "duration_ms": 50,
            }

        worker = build_worker(
            _settings(max_output_chars=100),
            run_codex_fn=fake_run_codex,
        )
        service = CodexCommandService(settings=_settings(max_output_chars=100), worker=worker)

        done = threading.Event()
        events: list[tuple[str, float]] = []
        responses: list[tuple[str, str]] = []
        acks: list[dict[str, str]] = []

        def ack(payload: dict[str, str]) -> None:
            acks.append(payload)
            events.append(("ack", time.monotonic()))

        def post_message(channel: str, text: str) -> None:
            responses.append((channel, text))
            events.append(("post", time.monotonic()))
            done.set()

        worker.start()
        try:
            service.handle_command(
                command="codex",
                run_fn=fake_run_codex,
                body={"text": "hello world", "user_id": "U1", "channel_id": "C1"},
                ack=ack,
                post_message=post_message,
            )
            self.assertTrue(done.wait(timeout=1.5))
        finally:
            worker.stop()

        self.assertEqual(len(acks), 1)
        self.assertTrue(responses)
        self.assertEqual(events[0][0], "ack")
        self.assertEqual(responses[0][0], "C1")
        self.assertIn("completed", responses[0][1])


class HelperFunctionTests(unittest.TestCase):
    def test_usage_text_includes_command(self) -> None:
        self.assertEqual(usage_text("codex"), "Usage: /codex <prompt>")
        self.assertEqual(usage_text("claude"), "Usage: /claude <prompt>")

    def test_unauthorized_text_includes_command(self) -> None:
        self.assertEqual(
            unauthorized_text("codex"),
            "You are not allowed to use `/codex` in this context.",
        )

    def test_ephemeral_returns_correct_structure(self) -> None:
        result = _ephemeral("test message")
        self.assertEqual(result["response_type"], "ephemeral")
        self.assertEqual(result["text"], "test message")

    def test_generate_job_id_returns_hex_string(self) -> None:
        job_id = generate_job_id()
        self.assertEqual(len(job_id), 8)
        int(job_id, 16)

    def test_is_allowed_returns_true_when_allowlist_empty(self) -> None:
        self.assertTrue(_is_allowed("any_value", frozenset()))

    def test_is_allowed_returns_true_when_value_in_allowlist(self) -> None:
        self.assertTrue(_is_allowed("user1", frozenset({"user1", "user2"})))

    def test_is_allowed_returns_false_when_value_not_in_allowlist(self) -> None:
        self.assertFalse(_is_allowed("user3", frozenset({"user1", "user2"})))


class ChannelAuthorizationTests(unittest.TestCase):
    def test_unauthorized_channel_is_rejected(self) -> None:
        acks: list[dict[str, str]] = []
        worker = StubWorker(should_enqueue=True)
        service = CodexCommandService(
            settings=_settings(allowed_channel_ids=frozenset({"C99"})),
            worker=worker,
        )

        service.handle_command(
            command="codex",
            run_fn=_noop_run_fn,
            body={"text": "hello", "user_id": "U1", "channel_id": "C1"},
            ack=acks.append,
            post_message=lambda _channel, _text: None,
        )

        self.assertEqual(len(acks), 1)
        self.assertEqual(_ack_text(acks[0]), unauthorized_text("codex"))
        self.assertEqual(worker.jobs, [])


class CreateAppTests(unittest.TestCase):
    @mock.patch("slack_bolt.App")
    def test_create_app_returns_app_worker_service(self, mock_app_class: mock.Mock) -> None:
        mock_app = mock.Mock()
        mock_app_class.return_value = mock_app

        settings = _settings()
        app, worker, service = create_app(settings)

        self.assertIs(app, mock_app)
        self.assertIsNotNone(worker)
        self.assertIsInstance(service, CodexCommandService)
        worker.stop()

    @mock.patch("slack_bolt.App")
    def test_create_app_loads_settings_from_env_when_none(self, mock_app_class: mock.Mock) -> None:
        mock_app = mock.Mock()
        mock_app_class.return_value = mock_app

        with mock.patch.dict(
            "os.environ",
            {
                "SLACK_APP_TOKEN": "xapp-env-test",
                "SLACK_BOT_TOKEN": "xoxb-env-test",
            },
            clear=True,
        ):
            app, worker, service = create_app(None)
            self.assertIsNotNone(app)
            worker.stop()

    @mock.patch("slack_bolt.App")
    def test_create_app_registers_command_handlers(self, mock_app_class: mock.Mock) -> None:
        mock_app = mock.Mock()
        mock_app_class.return_value = mock_app

        settings = _settings()
        app, worker, service = create_app(settings)

        # Verify command handlers were registered
        self.assertEqual(mock_app.command.call_count, 2)
        mock_app.command.assert_any_call("/codex")
        mock_app.command.assert_any_call("/claude")
        worker.stop()

    @mock.patch("slack_bolt.App")
    def test_command_handler_invokes_service(self, mock_app_class: mock.Mock) -> None:
        mock_app = mock.Mock()
        mock_app_class.return_value = mock_app
        handlers: list = []

        def capture_handler(path: str):
            def decorator(fn):
                handlers.append((path, fn))
                return fn
            return decorator

        mock_app.command.side_effect = capture_handler

        settings = _settings()
        app, worker, service = create_app(settings)
        worker.start()

        try:
            # Find the /codex handler
            codex_handler = next(fn for path, fn in handlers if path == "/codex")

            # Mock ack, body, and client
            mock_ack = mock.Mock()
            mock_client = mock.Mock()
            mock_body = {"text": "test prompt", "user_id": "U1", "channel_id": "C1"}

            # Invoke the handler
            codex_handler(mock_ack, mock_body, mock_client)

            # Verify ack was called
            mock_ack.assert_called_once()
        finally:
            worker.stop()


class BuildWorkerTests(unittest.TestCase):
    def test_build_worker_uses_provided_run_fn(self) -> None:
        settings = _settings()
        custom_fn = lambda p: _noop_run_fn(p)
        worker = build_worker(settings, run_codex_fn=custom_fn)
        self.assertIsNotNone(worker)

    def test_build_worker_uses_default_run_fn(self) -> None:
        settings = _settings()
        worker = build_worker(settings)
        self.assertIsNotNone(worker)


if __name__ == "__main__":
    unittest.main()

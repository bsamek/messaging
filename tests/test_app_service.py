from __future__ import annotations

import threading
import time
from typing import Any
import unittest

from slack_codex_bridge.app import (
    CodexCommandService,
    QUEUE_FULL_TEXT,
    build_worker,
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


if __name__ == "__main__":
    unittest.main()

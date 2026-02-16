from __future__ import annotations

import threading
import time
import unittest

from slack_codex_bridge.codex_runner import CodexResult
from slack_codex_bridge.worker import CodexJob, JobWorker


def _ok_result(_: str) -> CodexResult:
    return {
        "ok": True,
        "output_text": "ok",
        "error_type": None,
        "error_detail": None,
        "exit_code": 0,
        "duration_ms": 1,
    }


def _fail_result(_: str) -> CodexResult:
    return {
        "ok": False,
        "output_text": "",
        "error_type": "non_zero_exit",
        "error_detail": "command failed",
        "exit_code": 1,
        "duration_ms": 1,
    }


def _timeout_result(_: str) -> CodexResult:
    return {
        "ok": False,
        "output_text": "",
        "error_type": "timeout",
        "error_detail": "exceeded timeout",
        "exit_code": None,
        "duration_ms": 1,
    }


class WorkerValidationTests(unittest.TestCase):
    def test_raises_on_max_queue_size_less_than_1(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            JobWorker(
                run_codex_fn=_ok_result,
                max_queue_size=0,
                concurrency=1,
                max_output_chars=200,
            )
        self.assertIn("max_queue_size must be >= 1", str(ctx.exception))

    def test_raises_on_concurrency_less_than_1(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            JobWorker(
                run_codex_fn=_ok_result,
                max_queue_size=1,
                concurrency=0,
                max_output_chars=200,
            )
        self.assertIn("concurrency must be >= 1", str(ctx.exception))


class WorkerEnqueueTests(unittest.TestCase):
    def test_enqueue_rejects_when_queue_is_full(self) -> None:
        worker = JobWorker(
            run_codex_fn=_ok_result,
            max_queue_size=1,
            concurrency=1,
            max_output_chars=200,
        )
        first = CodexJob(
            job_id="job-1",
            prompt="first",
            user_id="U1",
            channel_id="C1",
            respond=lambda _: None,
        )
        second = CodexJob(
            job_id="job-2",
            prompt="second",
            user_id="U1",
            channel_id="C1",
            respond=lambda _: None,
        )

        self.assertIs(worker.enqueue(first), True)
        self.assertIs(worker.enqueue(second), False)


class WorkerQueueDepthTests(unittest.TestCase):
    def test_queue_depth_returns_queue_size(self) -> None:
        worker = JobWorker(
            run_codex_fn=_ok_result,
            max_queue_size=10,
            concurrency=1,
            max_output_chars=200,
        )
        self.assertEqual(worker.queue_depth(), 0)

        job = CodexJob(
            job_id="job-1",
            prompt="test",
            user_id="U1",
            channel_id="C1",
            respond=lambda _: None,
        )
        worker.enqueue(job)
        self.assertEqual(worker.queue_depth(), 1)


class WorkerStartStopTests(unittest.TestCase):
    def test_start_is_idempotent(self) -> None:
        worker = JobWorker(
            run_codex_fn=_ok_result,
            max_queue_size=10,
            concurrency=2,
            max_output_chars=200,
        )
        worker.start()
        initial_threads = len(worker._threads)
        worker.start()
        self.assertEqual(len(worker._threads), initial_threads)
        worker.stop()

    def test_stop_clears_threads(self) -> None:
        worker = JobWorker(
            run_codex_fn=_ok_result,
            max_queue_size=10,
            concurrency=2,
            max_output_chars=200,
        )
        worker.start()
        self.assertEqual(len(worker._threads), 2)
        worker.stop()
        self.assertEqual(len(worker._threads), 0)


class WorkerProcessJobTests(unittest.TestCase):
    def test_processes_successful_job(self) -> None:
        responses: list[str] = []
        done = threading.Event()

        def respond(msg: str) -> None:
            responses.append(msg)
            done.set()

        worker = JobWorker(
            run_codex_fn=_ok_result,
            max_queue_size=10,
            concurrency=1,
            max_output_chars=200,
        )
        worker.start()
        try:
            job = CodexJob(
                job_id="job-1",
                prompt="test",
                user_id="U1",
                channel_id="C1",
                respond=respond,
            )
            worker.enqueue(job)
            done.wait(timeout=2.0)
        finally:
            worker.stop()

        self.assertEqual(len(responses), 1)
        self.assertIn("completed", responses[0])

    def test_processes_failed_job(self) -> None:
        responses: list[str] = []
        done = threading.Event()

        def respond(msg: str) -> None:
            responses.append(msg)
            done.set()

        worker = JobWorker(
            run_codex_fn=_fail_result,
            max_queue_size=10,
            concurrency=1,
            max_output_chars=200,
        )
        worker.start()
        try:
            job = CodexJob(
                job_id="job-1",
                prompt="test",
                user_id="U1",
                channel_id="C1",
                respond=respond,
            )
            worker.enqueue(job)
            done.wait(timeout=2.0)
        finally:
            worker.stop()

        self.assertEqual(len(responses), 1)
        self.assertIn("failed", responses[0])

    def test_processes_timeout_job(self) -> None:
        responses: list[str] = []
        done = threading.Event()

        def respond(msg: str) -> None:
            responses.append(msg)
            done.set()

        worker = JobWorker(
            run_codex_fn=_timeout_result,
            max_queue_size=10,
            concurrency=1,
            max_output_chars=200,
        )
        worker.start()
        try:
            job = CodexJob(
                job_id="job-1",
                prompt="test",
                user_id="U1",
                channel_id="C1",
                respond=respond,
            )
            worker.enqueue(job)
            done.wait(timeout=2.0)
        finally:
            worker.stop()

        self.assertEqual(len(responses), 1)
        self.assertIn("failed", responses[0])

    def test_job_uses_custom_run_fn(self) -> None:
        responses: list[str] = []
        done = threading.Event()

        def custom_run(_: str) -> CodexResult:
            return {
                "ok": True,
                "output_text": "custom output",
                "error_type": None,
                "error_detail": None,
                "exit_code": 0,
                "duration_ms": 5,
            }

        def respond(msg: str) -> None:
            responses.append(msg)
            done.set()

        worker = JobWorker(
            run_codex_fn=_ok_result,
            max_queue_size=10,
            concurrency=1,
            max_output_chars=200,
        )
        worker.start()
        try:
            job = CodexJob(
                job_id="job-1",
                prompt="test",
                user_id="U1",
                channel_id="C1",
                respond=respond,
                run_fn=custom_run,
            )
            worker.enqueue(job)
            done.wait(timeout=2.0)
        finally:
            worker.stop()

        self.assertEqual(len(responses), 1)
        self.assertIn("custom output", responses[0])

    def test_stop_with_full_queue(self) -> None:
        """Test that stop works when queue is full."""
        def slow_run(_: str) -> CodexResult:
            time.sleep(0.5)
            return _ok_result("")

        worker = JobWorker(
            run_codex_fn=slow_run,
            max_queue_size=1,
            concurrency=1,
            max_output_chars=200,
        )
        job = CodexJob(
            job_id="job-1",
            prompt="test",
            user_id="U1",
            channel_id="C1",
            respond=lambda _: None,
        )
        worker.enqueue(job)
        worker.start()
        time.sleep(0.1)
        worker.stop(wait=True)
        self.assertEqual(len(worker._threads), 0)


if __name__ == "__main__":
    unittest.main()

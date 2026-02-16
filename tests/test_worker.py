from __future__ import annotations

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


class WorkerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

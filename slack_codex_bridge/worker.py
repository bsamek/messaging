from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import queue
import threading
import time
from typing import Callable

from slack_codex_bridge.codex_runner import CodexResult
from slack_codex_bridge.formatter import format_failure, format_success


Responder = Callable[[str], None]
RunFn = Callable[[str], CodexResult]


@dataclass(frozen=True)
class CodexJob:
    job_id: str
    prompt: str
    user_id: str
    channel_id: str
    respond: Responder
    run_fn: RunFn | None = None


@dataclass
class WorkerMetrics:
    jobs_received_total: int = 0
    jobs_completed_total: int = 0
    jobs_failed_total: int = 0
    jobs_timeout_total: int = 0


class JobWorker:
    def __init__(
        self,
        *,
        run_codex_fn: RunFn,
        max_queue_size: int,
        concurrency: int,
        max_output_chars: int,
        logger: logging.Logger | None = None,
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be >= 1")
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")

        self._default_run_fn = run_codex_fn
        self._queue: queue.Queue[CodexJob | None] = queue.Queue(maxsize=max_queue_size)
        self._concurrency = concurrency
        self._max_output_chars = max_output_chars
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._logger = logger or logging.getLogger(__name__)
        self._metrics = WorkerMetrics()
        self._metrics_lock = threading.Lock()

    def start(self) -> None:
        if self._threads:
            return
        for idx in range(self._concurrency):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"codex-worker-{idx}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self, *, wait: bool = True) -> None:
        self._stop_event.set()
        for _ in self._threads:
            while True:
                try:
                    self._queue.put_nowait(None)
                    break
                except queue.Full:
                    time.sleep(0.01)
        if wait:
            for thread in self._threads:
                thread.join(timeout=3.0)
        self._threads.clear()

    def enqueue(self, job: CodexJob) -> bool:
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            return False

        with self._metrics_lock:
            self._metrics.jobs_received_total += 1

        self._log_event(
            "job_enqueued",
            job_id=job.job_id,
            user_id=job.user_id,
            channel_id=job.channel_id,
            prompt_len=len(job.prompt),
            prompt_hash=hashlib.sha256(job.prompt.encode("utf-8")).hexdigest()[:12],
            queue_depth=self._queue.qsize(),
        )
        return True

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def metrics(self) -> WorkerMetrics:
        with self._metrics_lock:
            return WorkerMetrics(
                jobs_received_total=self._metrics.jobs_received_total,
                jobs_completed_total=self._metrics.jobs_completed_total,
                jobs_failed_total=self._metrics.jobs_failed_total,
                jobs_timeout_total=self._metrics.jobs_timeout_total,
            )

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue

            if item is None:
                self._queue.task_done()
                break

            self._process_job(item)
            self._queue.task_done()

    def _process_job(self, job: CodexJob) -> None:
        status = "failed"
        error_type: str | None = None
        duration_ms = 0

        try:
            run_fn = job.run_fn or self._default_run_fn
            result = run_fn(job.prompt)
            duration_ms = result["duration_ms"]
            if result["ok"]:
                message = format_success(
                    job_id=job.job_id,
                    duration_ms=result["duration_ms"],
                    output_text=result["output_text"],
                    max_output_chars=self._max_output_chars,
                )
                self._send_response(job, message)
                status = "completed"
                with self._metrics_lock:
                    self._metrics.jobs_completed_total += 1
            else:
                error_type = result["error_type"] or "internal_error"
                message = format_failure(
                    job_id=job.job_id,
                    error_type=error_type,
                    error_detail=result["error_detail"],
                )
                self._send_response(job, message)
                self._record_failure(error_type)
        except Exception as exc:  # pragma: no cover - defensive fallback
            error_type = "internal_error"
            self._record_failure(error_type)
            self._send_response(
                job,
                format_failure(
                    job_id=job.job_id,
                    error_type=error_type,
                    error_detail=str(exc),
                ),
            )

        self._log_event(
            "job_finished",
            job_id=job.job_id,
            user_id=job.user_id,
            channel_id=job.channel_id,
            status=status,
            error_type=error_type,
            duration_ms=duration_ms,
            queue_depth=self._queue.qsize(),
        )

    def _record_failure(self, error_type: str) -> None:
        with self._metrics_lock:
            self._metrics.jobs_failed_total += 1
            if error_type == "timeout":
                self._metrics.jobs_timeout_total += 1

    def _send_response(self, job: CodexJob, message: str) -> None:
        try:
            job.respond(message)
        except Exception as exc:  # pragma: no cover - response hook should not kill worker
            self._log_event(
                "response_failed",
                job_id=job.job_id,
                user_id=job.user_id,
                channel_id=job.channel_id,
                error=str(exc),
            )

    def _log_event(self, event: str, **fields: object) -> None:
        payload = {"event": event, **fields}
        self._logger.info(json.dumps(payload, sort_keys=True))

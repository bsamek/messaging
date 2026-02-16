from __future__ import annotations

from functools import partial
import logging
import secrets
from typing import TYPE_CHECKING, Any, Callable, Protocol

from slack_codex_bridge.codex_runner import run_codex
from slack_codex_bridge.config import Settings
from slack_codex_bridge.worker import CodexJob, JobWorker, RunFn

if TYPE_CHECKING:
    from slack_bolt import App as SlackBoltApp
else:
    SlackBoltApp = Any


QUEUE_FULL_TEXT = "Queue is full right now. Please try again shortly."


def usage_text(command: str) -> str:
    return f"Usage: /{command} <prompt>"


def unauthorized_text(command: str) -> str:
    return f"You are not allowed to use `/{command}` in this context."

AckFn = Callable[[dict[str, str]], None]
PostMessageFn = Callable[[str, str], None]


class EnqueueWorker(Protocol):
    def enqueue(self, job: CodexJob) -> bool: ...


def _ephemeral(text: str) -> dict[str, str]:
    return {"response_type": "ephemeral", "text": text}


def generate_job_id() -> str:
    return secrets.token_hex(4)


def _is_allowed(value: str, allowlist: frozenset[str]) -> bool:
    return not allowlist or value in allowlist


class CodexCommandService:
    def __init__(
        self,
        *,
        settings: Settings,
        worker: EnqueueWorker,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._worker = worker
        self._logger = logger or logging.getLogger(__name__)

    def handle_command(
        self,
        *,
        command: str,
        run_fn: RunFn,
        body: dict[str, Any],
        ack: AckFn,
        post_message: PostMessageFn,
    ) -> None:
        user_id = str(body.get("user_id", "")).strip()
        channel_id = str(body.get("channel_id", "")).strip()
        prompt = str(body.get("text", "")).strip()

        if not _is_allowed(user_id, self._settings.allowed_user_ids):
            ack(_ephemeral(unauthorized_text(command)))
            return
        if not _is_allowed(channel_id, self._settings.allowed_channel_ids):
            ack(_ephemeral(unauthorized_text(command)))
            return

        if not prompt:
            ack(_ephemeral(usage_text(command)))
            return
        if len(prompt) > self._settings.max_prompt_chars:
            ack(
                _ephemeral(
                    f"Prompt exceeds {self._settings.max_prompt_chars} characters.",
                ),
            )
            return

        job_id = generate_job_id()
        job = CodexJob(
            job_id=job_id,
            prompt=prompt,
            user_id=user_id,
            channel_id=channel_id,
            respond=lambda message: post_message(channel_id, message),
            run_fn=run_fn,
        )

        if not self._worker.enqueue(job):
            ack(_ephemeral(QUEUE_FULL_TEXT))
            return

        ack(_ephemeral(f"Accepted job `{job_id}`; running now."))
        self._logger.info("accepted job_id=%s user_id=%s channel_id=%s command=%s", job_id, user_id, channel_id, command)


def build_worker(
    settings: Settings,
    *,
    run_codex_fn: Callable[[str], Any] | None = None,
    logger: logging.Logger | None = None,
) -> JobWorker:
    runner = run_codex_fn or partial(run_codex, runner_config=settings.to_runner_config())
    return JobWorker(
        run_codex_fn=runner,
        max_queue_size=settings.queue_max_size,
        concurrency=settings.worker_concurrency,
        max_output_chars=settings.max_output_chars,
        logger=logger,
    )


def create_app(
    settings: Settings | None = None,
) -> tuple[SlackBoltApp, JobWorker, CodexCommandService]:
    from slack_bolt import App

    loaded_settings = settings or Settings.from_env(require_slack_tokens=True)
    logger = logging.getLogger("slack_codex_bridge")

    codex_run_fn: RunFn = partial(run_codex, runner_config=loaded_settings.to_runner_config())
    claude_run_fn: RunFn = partial(run_codex, runner_config=loaded_settings.to_claude_runner_config())

    worker = build_worker(loaded_settings, run_codex_fn=codex_run_fn, logger=logger)
    service = CodexCommandService(settings=loaded_settings, worker=worker, logger=logger)

    app = App(
        token=loaded_settings.slack_bot_token,
        signing_secret=loaded_settings.slack_signing_secret or "unused",
    )

    def _make_handler(command: str, run_fn: RunFn) -> Callable[..., None]:
        def handler(ack, body, client) -> None:  # type: ignore[no-untyped-def]
            service.handle_command(
                command=command,
                run_fn=run_fn,
                body=body,
                ack=ack,
                post_message=lambda channel_id, message: client.chat_postMessage(
                    channel=channel_id,
                    text=message,
                ),
            )
        return handler

    app.command("/codex")(_make_handler("codex", codex_run_fn))
    app.command("/claude")(_make_handler("claude", claude_run_fn))

    return app, worker, service


def main() -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env(require_slack_tokens=True)
    app, worker, _ = create_app(settings)
    worker.start()

    handler = SocketModeHandler(app, settings.slack_app_token)
    try:
        handler.start()
    finally:
        worker.stop()


if __name__ == "__main__":
    main()

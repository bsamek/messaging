from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
from typing import Mapping

from slack_codex_bridge.codex_runner import RunnerConfig


def _parse_positive_int(name: str, value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be >= 1")
    return parsed


def _parse_csv_set(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    slack_app_token: str
    slack_bot_token: str
    slack_signing_secret: str
    codex_bin: str
    codex_args: tuple[str, ...]
    codex_timeout_seconds: int
    codex_workdir: str
    claude_bin: str
    claude_args: tuple[str, ...]
    claude_timeout_seconds: int
    claude_workdir: str
    max_prompt_chars: int
    max_output_chars: int
    queue_max_size: int
    worker_concurrency: int
    allowed_user_ids: frozenset[str]
    allowed_channel_ids: frozenset[str]

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        require_slack_tokens: bool = False,
    ) -> Settings:
        source = env or os.environ

        slack_app_token = source.get("SLACK_APP_TOKEN", "").strip()
        slack_bot_token = source.get("SLACK_BOT_TOKEN", "").strip()
        slack_signing_secret = source.get("SLACK_SIGNING_SECRET", "").strip()

        if require_slack_tokens and not slack_app_token:
            raise ValueError("SLACK_APP_TOKEN is required")
        if require_slack_tokens and not slack_bot_token:
            raise ValueError("SLACK_BOT_TOKEN is required")

        codex_bin = source.get("CODEX_BIN", "codex").strip() or "codex"
        codex_args = tuple(shlex.split(source.get("CODEX_ARGS", "")))
        codex_timeout_seconds = _parse_positive_int(
            "CODEX_TIMEOUT_SECONDS",
            source.get("CODEX_TIMEOUT_SECONDS"),
            300,
        )
        codex_workdir = source.get("CODEX_WORKDIR", os.getcwd()).strip() or os.getcwd()

        claude_bin = source.get("CLAUDE_BIN", "claude").strip() or "claude"
        claude_args = tuple(shlex.split(source.get("CLAUDE_ARGS", "-p")))
        claude_timeout_seconds = _parse_positive_int(
            "CLAUDE_TIMEOUT_SECONDS",
            source.get("CLAUDE_TIMEOUT_SECONDS"),
            300,
        )
        claude_workdir = source.get("CLAUDE_WORKDIR", codex_workdir).strip() or codex_workdir

        max_prompt_chars = _parse_positive_int(
            "MAX_PROMPT_CHARS",
            source.get("MAX_PROMPT_CHARS"),
            4000,
        )
        max_output_chars = _parse_positive_int(
            "MAX_OUTPUT_CHARS",
            source.get("MAX_OUTPUT_CHARS"),
            3500,
        )
        queue_max_size = _parse_positive_int(
            "QUEUE_MAX_SIZE",
            source.get("QUEUE_MAX_SIZE"),
            20,
        )
        worker_concurrency = _parse_positive_int(
            "WORKER_CONCURRENCY",
            source.get("WORKER_CONCURRENCY"),
            1,
        )

        allowed_user_ids = _parse_csv_set(source.get("ALLOWED_USER_IDS"))
        allowed_channel_ids = _parse_csv_set(source.get("ALLOWED_CHANNEL_IDS"))

        return cls(
            slack_app_token=slack_app_token,
            slack_bot_token=slack_bot_token,
            slack_signing_secret=slack_signing_secret,
            codex_bin=codex_bin,
            codex_args=codex_args,
            codex_timeout_seconds=codex_timeout_seconds,
            codex_workdir=codex_workdir,
            claude_bin=claude_bin,
            claude_args=claude_args,
            claude_timeout_seconds=claude_timeout_seconds,
            claude_workdir=claude_workdir,
            max_prompt_chars=max_prompt_chars,
            max_output_chars=max_output_chars,
            queue_max_size=queue_max_size,
            worker_concurrency=worker_concurrency,
            allowed_user_ids=allowed_user_ids,
            allowed_channel_ids=allowed_channel_ids,
        )

    def to_runner_config(self) -> RunnerConfig:
        return RunnerConfig(
            codex_bin=self.codex_bin,
            codex_args=self.codex_args,
            timeout_seconds=self.codex_timeout_seconds,
            workdir=self.codex_workdir,
        )

    def to_claude_runner_config(self) -> RunnerConfig:
        return RunnerConfig(
            codex_bin=self.claude_bin,
            codex_args=self.claude_args,
            timeout_seconds=self.claude_timeout_seconds,
            workdir=self.claude_workdir,
        )

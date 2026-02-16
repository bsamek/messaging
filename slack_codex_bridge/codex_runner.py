from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
import time
from typing import TypedDict


class CodexResult(TypedDict):
    ok: bool
    output_text: str
    error_type: str | None
    error_detail: str | None
    exit_code: int | None
    duration_ms: int


@dataclass(frozen=True)
class RunnerConfig:
    codex_bin: str = "codex"
    codex_args: tuple[str, ...] = ()
    timeout_seconds: int = 300
    workdir: str | None = None

    def resolved_workdir(self) -> str:
        return self.workdir or os.getcwd()


def run_codex(prompt: str, runner_config: RunnerConfig | None = None) -> CodexResult:
    config = runner_config or RunnerConfig()
    started = time.monotonic()
    args = [config.codex_bin, *config.codex_args, prompt]

    try:
        completed = subprocess.run(
            args,
            text=True,
            capture_output=True,
            timeout=config.timeout_seconds,
            cwd=config.resolved_workdir(),
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "output_text": "",
            "error_type": "timeout",
            "error_detail": f"exceeded {config.timeout_seconds}s timeout",
            "exit_code": None,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        return {
            "ok": False,
            "output_text": "",
            "error_type": "internal_error",
            "error_detail": str(exc),
            "exit_code": None,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_text = completed.stdout.strip()
    stderr_text = completed.stderr.strip()

    if completed.returncode != 0:
        detail = stderr_text or stdout_text or f"exit code {completed.returncode}"
        return {
            "ok": False,
            "output_text": stdout_text,
            "error_type": "non_zero_exit",
            "error_detail": detail[:300],
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
        }

    return {
        "ok": True,
        "output_text": stdout_text,
        "error_type": None,
        "error_detail": None,
        "exit_code": completed.returncode,
        "duration_ms": duration_ms,
    }

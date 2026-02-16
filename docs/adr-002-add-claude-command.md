# ADR-002: Add `/claude` command backed by Claude Code CLI

- **Status:** Accepted
- **Date:** 2026-02-16

## Context

The bot is live with `/codex` calling the Codex CLI. We want `/claude` to call the Claude Code CLI (`claude -p`). Both commands share the same queue, worker, and response formatting -- only the subprocess invocation differs.

## Decision: Per-job runner, not per-worker

One shared queue/worker pool handles both commands. The job carries which runner to use (`run_fn` field on `CodexJob`). This avoids duplicating the worker or adding a dispatch layer -- the job already carries its own `respond` closure, so carrying its own `run_fn` is consistent.

## Decision: Generic runner -- remove hardcoded `"exec"`

Both CLIs follow `[bin, *args, prompt]`. Codex needs `exec` as a subcommand, Claude needs `-p` as a flag. Both fit the same pattern if we move `"exec"` out of the code and into `CODEX_ARGS`. The runner becomes `[config.codex_bin, *config.codex_args, prompt]`.

## Changes

1. **codex_runner.py** -- removed hardcoded `"exec"` from args; command is now `[bin, *args, prompt]`.
2. **worker.py** -- added `run_fn` field to `CodexJob`; `_process_job` uses `job.run_fn` with fallback to the worker default.
3. **config.py** -- new env vars `CLAUDE_BIN`, `CLAUDE_ARGS`, `CLAUDE_TIMEOUT_SECONDS`, `CLAUDE_WORKDIR`; new `to_claude_runner_config()` method.
4. **app.py** -- dynamic command name in usage/error messages; two runner partials (codex + claude); `/claude` handler registered.
5. **.envrc** -- added Claude vars; `CODEX_ARGS` now defaults to `"exec"`.
6. **tests** -- new tests for `/claude` dispatch, dynamic usage text, and `run_fn` propagation.

## Consequences

- `CODEX_ARGS` must now include `exec` (previously hardcoded). Existing deployments need to update `.envrc`.
- Both commands share the same queue, so a burst of `/claude` jobs can delay `/codex` jobs and vice versa.
- Adding more CLI backends in the future follows the same pattern: add config, build a partial, register the handler.

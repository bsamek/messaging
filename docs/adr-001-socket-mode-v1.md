# ADR-001: Slack -> Codex CLI Bridge (Socket Mode, V1)

- **Status:** Accepted
- **Date:** 2026-02-15

## 1. Overview

Build a Python service that lets Slack users run one-off Codex CLI tasks with:

`/codex <prompt>`

The service connects to Slack using Socket Mode (WebSocket) so no inbound ports or public HTTP endpoints are required.  
V1 is intentionally stateless: each command is an independent execution, with no conversation memory.

## 2. Goals

- Support a Slack slash command `/codex <prompt>`.
- Execute exactly one Codex CLI task per command.
- Return the result back to Slack in the same channel.
- Use Socket Mode end-to-end (no public Request URL).
- Keep implementation simple and operable on a single host.
- Use `uv` to manage Python versioning and dependencies.

## 3. Non-Goals (V1)

- Multi-turn conversations or persisted context.
- Concurrent multi-job orchestration across hosts.
- Streaming token-by-token output to Slack.
- Fine-grained authorization policies beyond basic allowlists.
- Web UI or admin dashboard.

## 4. Assumptions

- Codex CLI is installed on the host and executable by the service user.
- The host has outbound internet access to Slack and model endpoints used by Codex CLI.
- Slack workspace admins can install/configure a custom app.
- `uv` is installed on the host.

## 5. User Experience

1. User types `/codex summarize this error trace`.
2. Bot immediately acknowledges receipt (ephemeral), e.g. "Running Codex task…".
3. Bot posts final output when complete:
   - Success: formatted answer.
   - Failure: concise error + job id.

If the prompt is empty, bot returns usage help:

`Usage: /codex <prompt>`

## 6. High-Level Architecture

Components:

- `Slack Socket Client` (Python Bolt Socket Mode adapter)
- `Command Handler` (`/codex`)
- `Job Queue` (in-memory FIFO, single worker for V1)
- `Codex Runner` (subprocess wrapper around Codex CLI)
- `Slack Responder` (post final result via `respond`/Web API)
- `Logger` (structured logs with job ids)

Data flow:

1. Slack sends `slash_commands` payload over Socket Mode.
2. Handler validates input and calls `ack()` within Slack timeout window.
3. Handler enqueues a job.
4. Single worker dequeues and executes Codex CLI.
5. Result is posted back to Slack.

## 7. Slack App Configuration

Required settings:

- Enable **Socket Mode**.
- Create app-level token (`xapp-...`) with `connections:write`.
- Install bot token (`xoxb-...`).
- Add slash command `/codex`.

Required bot scopes (minimum):

- `commands` (slash command support)
- `chat:write` (send responses)

Notes:

- Socket Mode supports slash command payloads over WebSocket.
- App must be invited to channels where it posts, unless broader posting scopes are added.

## 8. Runtime Behavior

### 8.1 Command Handling

- Parse command text from payload.
- Trim whitespace.
- Reject empty prompt with usage response.
- Enforce max prompt length (default: 4000 chars).
- Optional allowlists:
  - `ALLOWED_USER_IDS`
  - `ALLOWED_CHANNEL_IDS`

### 8.2 Acknowledgement Strategy

- `ack()` immediately with a short ephemeral response:
  - "Accepted job `<job_id>`; running now."
- Never block `ack()` on Codex execution.

### 8.3 Job Execution

- Worker concurrency: `1` (single active Codex run at a time).
- Queue depth limit: configurable (default `20`); reject beyond limit.
- Execute Codex with subprocess, no shell interpolation.
- Pass prompt safely (stdin or argv list, never `shell=True`).
- Enforce timeout (default `300s`).

### 8.4 Response Formatting

- On success:
  - Post plain text answer with header line including job id and elapsed time.
- If output exceeds Slack message limits:
  - Truncate to configurable limit (default `3500` chars).
  - Append `...[truncated]`.
- On failure:
  - Post concise error category (`timeout`, `non_zero_exit`, `internal_error`) and job id.

## 9. Codex Runner Interface

Define a narrow interface so CLI details are isolated:

```python
class CodexResult(TypedDict):
    ok: bool
    output_text: str
    error_type: str | None
    error_detail: str | None
    exit_code: int | None
    duration_ms: int

def run_codex(prompt: str) -> CodexResult:
    ...
```

Configuration:

- `CODEX_BIN` (default: `codex`)
- `CODEX_ARGS` (optional static args)
- `CODEX_TIMEOUT_SECONDS` (default: `300`)
- `CODEX_WORKDIR` (default: service cwd)

## 10. Security

- Store Slack and Codex credentials in environment variables or host secret manager.
- Never log raw secrets or full token values.
- Use subprocess without shell to prevent command injection.
- Sanitize logged prompt content (or log length/hash only).
- Optionally restrict command usage to an allowlist of Slack users/channels.

## 11. Reliability and Operations

- Stateless process; in-memory queue means queued/in-flight jobs are lost on restart (accepted for V1).
- Automatic reconnect handled by Socket Mode client.
- Structured logs include:
  - `job_id`, `user_id`, `channel_id`, `duration_ms`, `status`, `error_type`
- Health behavior:
  - Process manager restarts on crash (`launchd`/`systemd`/supervisor).

## 12. Observability

Minimum metrics (log-derived is acceptable in V1):

- `jobs_received_total`
- `jobs_completed_total`
- `jobs_failed_total`
- `jobs_timeout_total`
- `job_duration_ms`
- `queue_depth`

## 13. Project Layout (Proposed)

```text
slack_codex_bridge/
  app.py                 # Bolt app + handlers
  worker.py              # queue + worker loop
  codex_runner.py        # subprocess wrapper
  config.py              # env parsing
  formatter.py           # Slack-safe formatting/truncation
  pyproject.toml
  uv.lock
  .python-version
  README.md
```

## 14. Environment Variables

```bash
SLACK_APP_TOKEN=xapp-...
SLACK_BOT_TOKEN=xoxb-...

CODEX_BIN=codex
CODEX_ARGS=
CODEX_TIMEOUT_SECONDS=300
CODEX_WORKDIR=/Users/brian/src/messaging

MAX_PROMPT_CHARS=4000
MAX_OUTPUT_CHARS=3500
QUEUE_MAX_SIZE=20
WORKER_CONCURRENCY=1

ALLOWED_USER_IDS=U123,U456
ALLOWED_CHANNEL_IDS=C123,C456
```

## 15. Testing Strategy

Unit tests:

- Prompt validation and empty prompt behavior.
- Queue full rejection path.
- Timeout handling in `run_codex`.
- Non-zero exit mapping to error response.
- Output truncation behavior.

Integration tests (local):

- Mock Codex binary returning deterministic output.
- Simulate slash command payload and verify:
  - immediate ack
  - eventual response message

Manual acceptance:

- `/codex hello` posts result.
- `/codex` shows usage.
- forced timeout returns timeout error.
- unauthorized user/channel is rejected when allowlist is configured.

## 16. Delivery Plan

Phase 1 (V1 implementation):

1. Slack app configuration and tokens.
2. Initialize Python project with `uv`, pin Python version, and define dependencies in `pyproject.toml`.
3. `/codex` handler + queue + single worker.
4. Codex subprocess runner with timeout.
5. Slack response formatting + truncation.
6. Basic logs and runbook.

## 17. Acceptance Criteria

- Running `/codex <prompt>` from Slack triggers exactly one Codex CLI execution.
- Bot acknowledges immediately and posts final result later.
- No inbound HTTP port is exposed.
- System remains stateless between commands.
- Failures are visible to users with a stable job id for troubleshooting.

## References

- Slack Socket Mode (includes slash command payload examples): https://docs.slack.dev/apis/events-api/using-socket-mode
- Bolt for Python Socket Mode: https://docs.slack.dev/tools/bolt-python/concepts/socket-mode

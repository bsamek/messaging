# Slack Codex Bridge (Socket Mode, V1)

Stateless Slack slash command bridge for one-off CLI runs.

## Features

- `/codex <prompt>` -- runs the Codex CLI (`codex exec <prompt>`).
- `/claude <prompt>` -- runs the Claude Code CLI (`claude -p <prompt>`).
- Immediate slash-command acknowledgement.
- In-memory FIFO queue with configurable max depth.
- Configurable worker concurrency (default: 1).
- Safe subprocess invocation (`shell=False`) with timeout handling.
- Slack-safe output truncation and stable job IDs.

## Requirements

- Python 3.12+
- `uv`
- Slack app configured for Socket Mode
- Codex CLI and/or Claude Code CLI installed and available to the service user

## Quick Start

1. Create an environment and install dependencies:

```bash
uv sync --group dev
```

2. Configure environment variables:

```bash
export SLACK_APP_TOKEN="xapp-..."
export SLACK_BOT_TOKEN="xoxb-..."

export CODEX_BIN="codex"
export CODEX_ARGS="exec"
export CODEX_TIMEOUT_SECONDS="300"
export CODEX_WORKDIR="/path/to/workdir"

export CLAUDE_BIN="claude"
export CLAUDE_ARGS="-p"
export CLAUDE_TIMEOUT_SECONDS="300"
export CLAUDE_WORKDIR="/path/to/workdir"

export MAX_PROMPT_CHARS="4000"
export MAX_OUTPUT_CHARS="3500"
export QUEUE_MAX_SIZE="20"
export WORKER_CONCURRENCY="1"

export ALLOWED_USER_IDS=""
export ALLOWED_CHANNEL_IDS=""
```

3. Run the service:

```bash
uv run slack-codex-bridge
```

## Development

Install the pre-commit hook to run tests automatically before each commit:

```bash
uv run pre-commit install
```

## Testing

```bash
uv run pytest
```

To run tests with coverage (CI enforces 100%):

```bash
uv run pytest --cov=slack_codex_bridge --cov-report=term-missing --cov-fail-under=100
```

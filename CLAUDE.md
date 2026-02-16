# Slack Codex Bridge

Stateless Slack slash-command bridge that runs one-off CLI tasks via `/codex` (Codex CLI) and `/claude` (Claude Code CLI).

## Architecture

- Python 3.12, `uv`, `slack-bolt` (Socket Mode).
- Single in-memory FIFO queue + configurable worker pool shared by all commands.
- Each job carries its own `run_fn` (subprocess partial) and `respond` callback.
- CLI invocation pattern: `[bin, *args, prompt]` with `shell=False`.

## Key modules

| File | Purpose |
|---|---|
| `slack_codex_bridge/app.py` | Bolt app, command handlers, service layer |
| `slack_codex_bridge/worker.py` | Job queue and worker loop |
| `slack_codex_bridge/codex_runner.py` | Subprocess wrapper (generic, not Codex-specific) |
| `slack_codex_bridge/config.py` | Env-var parsing into `Settings` |
| `slack_codex_bridge/formatter.py` | Slack-safe output formatting/truncation |

## ADRs

All implementation plans and architectural decisions are recorded as ADRs in `docs/`:

- [ADR-001: Socket Mode V1](docs/adr-001-socket-mode-v1.md)
- [ADR-002: Add /claude command](docs/adr-002-add-claude-command.md)

New changes should have an ADR when they alter architecture, add commands, or change the config surface.

## Running

```bash
uv sync --group dev
uv run slack-codex-bridge
```

## Testing

```bash
uv run pytest
```

## Workflow

- Commit early and often -- don't let large changesets accumulate.

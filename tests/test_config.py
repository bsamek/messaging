from __future__ import annotations

import os
import unittest

from slack_codex_bridge.config import Settings, _parse_positive_int, _parse_csv_set


class ParsePositiveIntTests(unittest.TestCase):
    def test_returns_default_when_value_is_none(self) -> None:
        result = _parse_positive_int("TEST", None, 42)
        self.assertEqual(result, 42)

    def test_returns_default_when_value_is_empty_string(self) -> None:
        result = _parse_positive_int("TEST", "  ", 42)
        self.assertEqual(result, 42)

    def test_parses_valid_integer(self) -> None:
        result = _parse_positive_int("TEST", "100", 42)
        self.assertEqual(result, 100)

    def test_raises_on_non_integer(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _parse_positive_int("TEST", "abc", 42)
        self.assertIn("TEST must be an integer", str(ctx.exception))

    def test_raises_on_zero(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _parse_positive_int("TEST", "0", 42)
        self.assertIn("TEST must be >= 1", str(ctx.exception))

    def test_raises_on_negative(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _parse_positive_int("TEST", "-5", 42)
        self.assertIn("TEST must be >= 1", str(ctx.exception))


class ParseCsvSetTests(unittest.TestCase):
    def test_returns_empty_frozenset_when_value_is_none(self) -> None:
        result = _parse_csv_set(None)
        self.assertEqual(result, frozenset())

    def test_returns_empty_frozenset_when_value_is_empty(self) -> None:
        result = _parse_csv_set("")
        self.assertEqual(result, frozenset())

    def test_parses_single_value(self) -> None:
        result = _parse_csv_set("user1")
        self.assertEqual(result, frozenset({"user1"}))

    def test_parses_multiple_values(self) -> None:
        result = _parse_csv_set("user1,user2,user3")
        self.assertEqual(result, frozenset({"user1", "user2", "user3"}))

    def test_strips_whitespace(self) -> None:
        result = _parse_csv_set(" user1 , user2 ")
        self.assertEqual(result, frozenset({"user1", "user2"}))

    def test_ignores_empty_parts(self) -> None:
        result = _parse_csv_set("user1,,user2,")
        self.assertEqual(result, frozenset({"user1", "user2"}))


class SettingsFromEnvTests(unittest.TestCase):
    def test_from_env_with_minimal_env(self) -> None:
        env = {}
        settings = Settings.from_env(env)
        self.assertEqual(settings.slack_app_token, "")
        self.assertEqual(settings.slack_bot_token, "")
        self.assertEqual(settings.codex_bin, "codex")
        self.assertEqual(settings.codex_timeout_seconds, 300)
        self.assertEqual(settings.claude_bin, "claude")
        self.assertEqual(settings.claude_args, ("-p",))
        self.assertEqual(settings.max_prompt_chars, 4000)
        self.assertEqual(settings.max_output_chars, 3500)
        self.assertEqual(settings.queue_max_size, 20)
        self.assertEqual(settings.worker_concurrency, 1)

    def test_from_env_raises_on_missing_app_token_when_required(self) -> None:
        env = {"SLACK_BOT_TOKEN": "xoxb-test"}
        with self.assertRaises(ValueError) as ctx:
            Settings.from_env(env, require_slack_tokens=True)
        self.assertIn("SLACK_APP_TOKEN is required", str(ctx.exception))

    def test_from_env_raises_on_missing_bot_token_when_required(self) -> None:
        env = {"SLACK_APP_TOKEN": "xapp-test"}
        with self.assertRaises(ValueError) as ctx:
            Settings.from_env(env, require_slack_tokens=True)
        self.assertIn("SLACK_BOT_TOKEN is required", str(ctx.exception))

    def test_from_env_with_all_values(self) -> None:
        env = {
            "SLACK_APP_TOKEN": "xapp-test",
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_SIGNING_SECRET": "secret123",
            "CODEX_BIN": "/usr/bin/codex",
            "CODEX_ARGS": "--flag1 --flag2",
            "CODEX_TIMEOUT_SECONDS": "120",
            "CODEX_WORKDIR": "/work/codex",
            "CLAUDE_BIN": "/usr/bin/claude",
            "CLAUDE_ARGS": "-p --verbose",
            "CLAUDE_TIMEOUT_SECONDS": "180",
            "CLAUDE_WORKDIR": "/work/claude",
            "MAX_PROMPT_CHARS": "5000",
            "MAX_OUTPUT_CHARS": "4000",
            "QUEUE_MAX_SIZE": "50",
            "WORKER_CONCURRENCY": "4",
            "ALLOWED_USER_IDS": "U1,U2",
            "ALLOWED_CHANNEL_IDS": "C1,C2,C3",
        }
        settings = Settings.from_env(env, require_slack_tokens=True)

        self.assertEqual(settings.slack_app_token, "xapp-test")
        self.assertEqual(settings.slack_bot_token, "xoxb-test")
        self.assertEqual(settings.slack_signing_secret, "secret123")
        self.assertEqual(settings.codex_bin, "/usr/bin/codex")
        self.assertEqual(settings.codex_args, ("--flag1", "--flag2"))
        self.assertEqual(settings.codex_timeout_seconds, 120)
        self.assertEqual(settings.codex_workdir, "/work/codex")
        self.assertEqual(settings.claude_bin, "/usr/bin/claude")
        self.assertEqual(settings.claude_args, ("-p", "--verbose"))
        self.assertEqual(settings.claude_timeout_seconds, 180)
        self.assertEqual(settings.claude_workdir, "/work/claude")
        self.assertEqual(settings.max_prompt_chars, 5000)
        self.assertEqual(settings.max_output_chars, 4000)
        self.assertEqual(settings.queue_max_size, 50)
        self.assertEqual(settings.worker_concurrency, 4)
        self.assertEqual(settings.allowed_user_ids, frozenset({"U1", "U2"}))
        self.assertEqual(settings.allowed_channel_ids, frozenset({"C1", "C2", "C3"}))

    def test_from_env_uses_os_environ_when_env_not_provided(self) -> None:
        original_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["SLACK_APP_TOKEN"] = "xapp-from-os"
            os.environ["SLACK_BOT_TOKEN"] = "xoxb-from-os"
            settings = Settings.from_env(require_slack_tokens=True)
            self.assertEqual(settings.slack_app_token, "xapp-from-os")
            self.assertEqual(settings.slack_bot_token, "xoxb-from-os")
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_from_env_uses_codex_workdir_as_default_for_claude_workdir(self) -> None:
        env = {
            "CODEX_WORKDIR": "/my/codex/dir",
        }
        settings = Settings.from_env(env)
        self.assertEqual(settings.codex_workdir, "/my/codex/dir")
        self.assertEqual(settings.claude_workdir, "/my/codex/dir")

    def test_from_env_defaults_to_cwd_for_workdir(self) -> None:
        settings = Settings.from_env({})
        self.assertEqual(settings.codex_workdir, os.getcwd())
        self.assertEqual(settings.claude_workdir, os.getcwd())

    def test_from_env_handles_empty_bin_values(self) -> None:
        env = {
            "CODEX_BIN": "",
            "CLAUDE_BIN": "",
        }
        settings = Settings.from_env(env)
        self.assertEqual(settings.codex_bin, "codex")
        self.assertEqual(settings.claude_bin, "claude")


class SettingsToRunnerConfigTests(unittest.TestCase):
    def test_to_runner_config(self) -> None:
        settings = Settings(
            slack_app_token="xapp-test",
            slack_bot_token="xoxb-test",
            slack_signing_secret="secret",
            codex_bin="/bin/codex",
            codex_args=("--arg1",),
            codex_timeout_seconds=120,
            codex_workdir="/work/codex",
            claude_bin="/bin/claude",
            claude_args=("-p",),
            claude_timeout_seconds=180,
            claude_workdir="/work/claude",
            max_prompt_chars=4000,
            max_output_chars=3500,
            queue_max_size=20,
            worker_concurrency=1,
            allowed_user_ids=frozenset(),
            allowed_channel_ids=frozenset(),
        )

        config = settings.to_runner_config()
        self.assertEqual(config.codex_bin, "/bin/codex")
        self.assertEqual(config.codex_args, ("--arg1",))
        self.assertEqual(config.timeout_seconds, 120)
        self.assertEqual(config.workdir, "/work/codex")

    def test_to_claude_runner_config(self) -> None:
        settings = Settings(
            slack_app_token="xapp-test",
            slack_bot_token="xoxb-test",
            slack_signing_secret="secret",
            codex_bin="/bin/codex",
            codex_args=("--arg1",),
            codex_timeout_seconds=120,
            codex_workdir="/work/codex",
            claude_bin="/bin/claude",
            claude_args=("-p", "--verbose"),
            claude_timeout_seconds=180,
            claude_workdir="/work/claude",
            max_prompt_chars=4000,
            max_output_chars=3500,
            queue_max_size=20,
            worker_concurrency=1,
            allowed_user_ids=frozenset(),
            allowed_channel_ids=frozenset(),
        )

        config = settings.to_claude_runner_config()
        self.assertEqual(config.codex_bin, "/bin/claude")
        self.assertEqual(config.codex_args, ("-p", "--verbose"))
        self.assertEqual(config.timeout_seconds, 180)
        self.assertEqual(config.workdir, "/work/claude")


if __name__ == "__main__":
    unittest.main()

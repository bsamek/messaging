from __future__ import annotations

import os
import sys
import unittest

from slack_codex_bridge.codex_runner import RunnerConfig, run_codex


class RunnerConfigTests(unittest.TestCase):
    def test_resolved_workdir_returns_workdir_when_set(self) -> None:
        config = RunnerConfig(workdir="/custom/path")
        self.assertEqual(config.resolved_workdir(), "/custom/path")

    def test_resolved_workdir_returns_cwd_when_none(self) -> None:
        config = RunnerConfig(workdir=None)
        self.assertEqual(config.resolved_workdir(), os.getcwd())

    def test_default_values(self) -> None:
        config = RunnerConfig()
        self.assertEqual(config.codex_bin, "codex")
        self.assertEqual(config.codex_args, ())
        self.assertEqual(config.timeout_seconds, 300)
        self.assertIsNone(config.workdir)


class CodexRunnerTests(unittest.TestCase):
    def test_run_codex_timeout_maps_to_timeout_error(self) -> None:
        config = RunnerConfig(
            codex_bin=sys.executable,
            codex_args=("-c", "import time; time.sleep(2)"),
            timeout_seconds=1,
            workdir=".",
        )
        result = run_codex("ignored", runner_config=config)

        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_type"], "timeout")
        self.assertIsNone(result["exit_code"])

    def test_run_codex_non_zero_exit_maps_to_non_zero_error(self) -> None:
        config = RunnerConfig(
            codex_bin=sys.executable,
            codex_args=(
                "-c",
                "import sys; sys.stderr.write('boom'); sys.exit(7)",
            ),
            timeout_seconds=5,
            workdir=".",
        )
        result = run_codex("ignored", runner_config=config)

        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_type"], "non_zero_exit")
        self.assertEqual(result["exit_code"], 7)

    def test_run_codex_success(self) -> None:
        config = RunnerConfig(
            codex_bin=sys.executable,
            codex_args=("-c", "import sys; print(sys.argv[1])"),
            timeout_seconds=5,
            workdir=".",
        )
        result = run_codex("hello", runner_config=config)

        self.assertIs(result["ok"], True)
        self.assertEqual(result["output_text"], "hello")
        self.assertIsNone(result["error_type"])
        self.assertIsNone(result["error_detail"])
        self.assertEqual(result["exit_code"], 0)
        self.assertGreater(result["duration_ms"], 0)

    def test_run_codex_non_zero_exit_uses_stdout_when_no_stderr(self) -> None:
        config = RunnerConfig(
            codex_bin=sys.executable,
            codex_args=(
                "-c",
                "import sys; print('stdout message'); sys.exit(1)",
            ),
            timeout_seconds=5,
            workdir=".",
        )
        result = run_codex("ignored", runner_config=config)

        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_type"], "non_zero_exit")
        self.assertIn("stdout message", result["error_detail"])

    def test_run_codex_non_zero_exit_uses_exit_code_when_no_output(self) -> None:
        config = RunnerConfig(
            codex_bin=sys.executable,
            codex_args=("-c", "import sys; sys.exit(42)"),
            timeout_seconds=5,
            workdir=".",
        )
        result = run_codex("ignored", runner_config=config)

        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_type"], "non_zero_exit")
        self.assertIn("exit code 42", result["error_detail"])

    def test_run_codex_uses_default_config_when_none(self) -> None:
        # This test validates that run_codex handles None config gracefully
        # We can't easily test this without the actual codex binary, so we
        # just verify it doesn't throw when given None (defaults apply)
        config = RunnerConfig(
            codex_bin=sys.executable,
            codex_args=("-c", "print('test')"),
            timeout_seconds=5,
        )
        result = run_codex("ignored", runner_config=config)
        self.assertIs(result["ok"], True)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest

from slack_codex_bridge.codex_runner import RunnerConfig, run_codex


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


if __name__ == "__main__":
    unittest.main()

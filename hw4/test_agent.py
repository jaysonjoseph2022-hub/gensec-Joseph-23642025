"""End-to-end test for the isolated, synthetic-fixture MCP workflow."""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent import _classify_risk, _parse_password_examples, validate_scratch_fixture


AGENT_PATH = Path(__file__).with_name("agent.py")
FIXTURE_CONTENT = (
    "password|synthetic-weak-sample|owl7\n"
    "password|synthetic-strong-sample|Blue!Cedar47Window\n"
).encode("utf-8")


def run_git(repository: Path, *arguments: str) -> str:
    """Run a local Git command against the disposable test repository."""
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class AgentIntegrationTests(unittest.TestCase):
    """Exercise both MCP servers using only a temporary synthetic fixture."""

    def test_read_only_synthetic_fixture_workflow(self) -> None:
        """Check the report, correct hash, and unchanged scratch Git state."""
        with tempfile.TemporaryDirectory(prefix="hw4-mcp-scratch-") as temp_dir:
            repository = Path(temp_dir).resolve()
            fixture = repository / "password-examples.txt"
            fixture.write_bytes(FIXTURE_CONTENT)
            run_git(repository, "init", "--quiet")
            run_git(repository, "add", fixture.name)
            initial_status = run_git(repository, "status", "--porcelain")
            initial_staged_diff = run_git(repository, "diff", "--cached", "--name-only")

            result = subprocess.run(
                [
                    sys.executable,
                    str(AGENT_PATH),
                    "--repository",
                    str(repository),
                    "--fixture",
                    str(fixture),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=240,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            expected_hash = hashlib.sha256(FIXTURE_CONTENT).hexdigest()
            self.assertIn("Synthetic fixture review", result.stdout)
            self.assertIn("Staged additions: 2 synthetic example(s)", result.stdout)
            self.assertIn("synthetic-weak-sample: weak", result.stdout)
            self.assertIn("synthetic-strong-sample: strong", result.stdout)
            self.assertIn(f"SHA-256: {expected_hash}", result.stdout)
            self.assertNotIn("owl7", result.stdout)
            self.assertNotIn("Blue!Cedar47Window", result.stdout)
            self.assertEqual(run_git(repository, "status", "--porcelain"), initial_status)
            self.assertEqual(
                run_git(repository, "diff", "--cached", "--name-only"),
                initial_staged_diff,
            )
            self.assertEqual(initial_staged_diff, fixture.name)

    def test_clean_fixture_baselines_and_staged_unstaged_diffs(self) -> None:
        """Verify a clean fixture, both diff areas, and baseline comparison."""
        with tempfile.TemporaryDirectory(prefix="hw4-mcp-scratch-") as temp_dir:
            repository = Path(temp_dir).resolve()
            fixture = repository / "password-examples.txt"
            staged_content = b"password|synthetic-strong|Blue!Cedar47Window\n"
            fixture.write_bytes(staged_content)
            run_git(repository, "init", "--quiet")
            run_git(repository, "add", fixture.name)
            fixture.write_bytes(staged_content + b"Unstaged synthetic note.\n")

            initial_status = run_git(repository, "status", "--porcelain")
            expected_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
            matching_result = self._run_agent(repository, fixture, expected_hash)

            self.assertEqual(matching_result.returncode, 0, matching_result.stderr)
            for section in (
                "Audit scope",
                "Git status and change summary",
                "Synthetic secret-scan findings",
                "File integrity and hash",
                "Synthetic password assessments",
                "Findings and recommendations",
                "Overall result",
            ):
                self.assertIn(section, matching_result.stdout)
            self.assertIn("git_diff_staged", matching_result.stdout)
            self.assertIn("git_diff_unstaged", matching_result.stdout)
            self.assertIn("Staged: password-examples.txt (+1/-0)", matching_result.stdout)
            self.assertIn("Unstaged: password-examples.txt (+1/-0)", matching_result.stdout)
            self.assertIn("Baseline comparison: match", matching_result.stdout)
            self.assertIn("synthetic-strong: strong", matching_result.stdout)
            self.assertIn("Overall result\n- INFORMATIONAL", matching_result.stdout)

            mismatching_result = self._run_agent(repository, fixture, "0" * 64)
            self.assertEqual(mismatching_result.returncode, 0, mismatching_result.stderr)
            self.assertIn("Baseline comparison: mismatch", mismatching_result.stdout)
            self.assertIn("Overall result\n- MEDIUM", mismatching_result.stdout)
            self.assertEqual(run_git(repository, "status", "--porcelain"), initial_status)

        self.assertFalse(repository.exists(), "Temporary clean repository was not removed.")

    def test_problematic_fixture_is_high_risk_and_redacted(self) -> None:
        """Detect only synthetic patterns and never include their values."""
        api_key_value = "demo_api_key_123456789"
        token_value = "demo_access_token_12345678"
        weak_password = "owl7"
        fixture_content = (
            f"password|synthetic-weak|{weak_password}\n"
            f"API_KEY={api_key_value}\n"
            f"ACCESS_TOKEN={token_value}\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="hw4-mcp-scratch-") as temp_dir:
            repository = Path(temp_dir).resolve()
            fixture = repository / "password-examples.txt"
            fixture.write_bytes(fixture_content)
            run_git(repository, "init", "--quiet")
            run_git(repository, "add", fixture.name)
            initial_status = run_git(repository, "status", "--porcelain")

            result = self._run_agent(repository, fixture)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("API-key-like pattern: line 2, count 1", result.stdout)
            self.assertIn("token-like pattern: line 3, count 1", result.stdout)
            self.assertIn("synthetic-weak: weak", result.stdout)
            self.assertIn("Overall result\n- HIGH", result.stdout)
            self.assertIn("Pattern-based detection only", result.stdout)
            self.assertIn("not a professional security certification", result.stdout)
            for synthetic_value in (api_key_value, token_value, weak_password):
                self.assertNotIn(synthetic_value, result.stdout)
            self.assertEqual(run_git(repository, "status", "--porcelain"), initial_status)

        self.assertFalse(repository.exists(), "Temporary problematic repository was not removed.")

    def test_invalid_paths_and_fixtures_are_rejected(self) -> None:
        """Reject unsafe paths, symlinks, extra files, and malformed examples."""
        with self.assertRaisesRegex(ValueError, "scratch"):
            validate_scratch_fixture(str(Path(__file__).resolve().parent), "test_agent.py")

        with tempfile.TemporaryDirectory(prefix="hw4-mcp-scratch-") as temp_dir:
            repository = Path(temp_dir).resolve()
            fixture = repository / "password-examples.txt"
            fixture.write_text("synthetic-weak|owl7\n", encoding="utf-8")
            run_git(repository, "init", "--quiet")

            fixture.unlink()
            with tempfile.TemporaryDirectory(prefix="hw4-mcp-target-") as target_dir:
                outside_target = Path(target_dir) / "outside.txt"
                outside_target.write_text("synthetic-only", encoding="utf-8")
                fixture.symlink_to(outside_target)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    validate_scratch_fixture(str(repository), fixture.name)

            fixture.unlink()
            fixture.write_text("synthetic-weak|owl7\n", encoding="utf-8")
            extra_file = repository / "unrelated.txt"
            extra_file.write_text("synthetic", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "only the designated fixture"):
                validate_scratch_fixture(str(repository), fixture.name)
            extra_file.unlink()

            unexpected_type = repository / "fixture.py"
            unexpected_type.write_text("synthetic", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "regular .txt"):
                validate_scratch_fixture(str(repository), unexpected_type.name)
            unexpected_type.unlink()

        with self.assertRaisesRegex(ValueError, "Malformed password example"):
            _parse_password_examples("password|missing-value\n")
        self.assertEqual(_parse_password_examples("unlabeled|not-a-password\n"), [])
        with self.assertRaisesRegex(ValueError, "Malformed password example"):
            _parse_password_examples(
                "password|synthetic-duplicate|first\n"
                "password|synthetic-duplicate|second\n"
            )

    def test_deterministic_demo_risk_tiers(self) -> None:
        """Keep informational, low, medium, and high rules deterministic."""
        self.assertEqual(_classify_risk([], [], True)[0], "informational")
        self.assertEqual(
            _classify_risk([], [("synthetic-moderate", "moderate")], None)[0],
            "low",
        )
        self.assertEqual(
            _classify_risk([], [("synthetic-weak", "weak")], None)[0],
            "medium",
        )
        self.assertEqual(_classify_risk([], [], False)[0], "medium")
        self.assertEqual(
            _classify_risk([{"type": "API-key-like", "line": 1, "count": 1}], [], None)[0],
            "high",
        )

    def _run_agent(
        self,
        repository: Path,
        fixture: Path,
        baseline_sha256: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the agent only against this test's temporary fixture repository."""
        command = [
            sys.executable,
            str(AGENT_PATH),
            "--repository",
            str(repository),
            "--fixture",
            str(fixture),
        ]
        if baseline_sha256 is not None:
            command.extend(("--baseline-sha256", baseline_sha256))
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )


if __name__ == "__main__":
    unittest.main()
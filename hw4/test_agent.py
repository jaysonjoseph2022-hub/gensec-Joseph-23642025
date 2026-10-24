"""End-to-end test for the isolated, synthetic-fixture MCP workflow."""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


AGENT_PATH = Path(__file__).with_name("agent.py")
FIXTURE_CONTENT = (
    "weak-sample|owl7\n"
    "strong-sample|Blue!Cedar47Window\n"
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
            self.assertIn("weak-sample: weak", result.stdout)
            self.assertIn("strong-sample: strong", result.stdout)
            self.assertIn(f"SHA-256: {expected_hash}", result.stdout)
            self.assertNotIn("owl7", result.stdout)
            self.assertNotIn("Blue!Cedar47Window", result.stdout)
            self.assertEqual(run_git(repository, "status", "--porcelain"), initial_status)
            self.assertEqual(
                run_git(repository, "diff", "--cached", "--name-only"),
                initial_staged_diff,
            )
            self.assertEqual(initial_staged_diff, fixture.name)


if __name__ == "__main__":
    unittest.main()
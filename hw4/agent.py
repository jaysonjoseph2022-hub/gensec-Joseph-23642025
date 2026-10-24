"""Review one synthetic password fixture with Git and custom MCP tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult


GIT_SERVER_VERSION = "2026.10.19"
GIT_SERVER_TOOLS = {"git_status", "git_diff_staged", "git_diff_unstaged"}
CUSTOM_SERVER_TOOLS = {
	"analyze_password_strength",
	"calculate_sha256",
	"scan_synthetic_secrets",
}
LABEL_PATTERN = re.compile(r"synthetic-[A-Za-z][A-Za-z0-9_-]{0,31}\Z")
ASSESSMENT_PATTERN = re.compile(
	r"\ABasic assessment: (weak|moderate|strong)\.", re.IGNORECASE
)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
MAX_FIXTURE_BYTES = 32_768
PROJECT_DIR = Path(__file__).resolve().parent
CUSTOM_SERVER_PATH = PROJECT_DIR / "mcp-server.py"


@dataclass(frozen=True)
class GitDiffSummary:
	"""Counts and filenames supported by one Git MCP diff result."""

	files: tuple[str, ...]
	additions: int | None
	deletions: int | None


def validate_scratch_fixture(repository: str, fixture: str) -> tuple[Path, Path]:
	"""Require one regular fixture inside a disposable, isolated /tmp repo."""
	repo_path = Path(repository).resolve(strict=True)
	temp_root = Path(tempfile.gettempdir()).resolve()
	if (
		not repo_path.is_relative_to(temp_root)
		or repo_path == temp_root
		or not repo_path.name.startswith("hw4-mcp-scratch-")
	):
		raise ValueError("Repository must be a hw4-mcp-scratch-* directory in the temp area.")
	git_directory = repo_path / ".git"
	if git_directory.is_symlink() or not git_directory.is_dir():
		raise ValueError("The designated scratch directory must be a Git repository.")

	fixture_input = Path(fixture)
	fixture_candidate = fixture_input if fixture_input.is_absolute() else repo_path / fixture_input
	if fixture_candidate.is_symlink():
		raise ValueError("The synthetic fixture cannot be a symlink.")
	fixture_path = fixture_candidate.resolve(strict=True)
	if (
		fixture_path.parent != repo_path
		or not fixture_path.is_file()
		or fixture_path.suffix.lower() != ".txt"
	):
		raise ValueError("Fixture must be a regular .txt file directly inside the scratch repository.")
	if not re.fullmatch(r"[A-Za-z0-9_.-]+", fixture_path.name):
		raise ValueError("Fixture filename must use only letters, digits, dots, underscores, or hyphens.")
	if fixture_path.stat().st_size > MAX_FIXTURE_BYTES:
		raise ValueError("Synthetic fixture is larger than the 32 KiB limit.")

	repository_files = {entry.name for entry in repo_path.iterdir() if entry.name != ".git"}
	if repository_files != {fixture_path.name}:
		raise ValueError("Scratch repository must contain only the designated fixture besides .git.")
	return repo_path, fixture_path


def _server_environment() -> dict[str, str]:
	"""Pass only runtime and certificate settings, not inherited secrets."""
	allowed_names = (
		"PATH",
		"HOME",
		"TMPDIR",
		"SSL_CERT_FILE",
		"SSL_CERT_DIR",
		"LANG",
		"LC_ALL",
	)
	environment = {name: os.environ[name] for name in allowed_names if name in os.environ}
	if "PATH" not in environment:
		raise RuntimeError("PATH is required to launch the isolated Git MCP server.")
	return environment


def _tool_text(result: CallToolResult, tool_name: str) -> str:
	"""Return text from a successful MCP tool result or raise a safe error."""
	if result.isError:
		raise RuntimeError(f"MCP tool {tool_name} returned an error.")
	text = "\n".join(
		item.text for item in result.content if hasattr(item, "text")
	).strip()
	if not text:
		raise RuntimeError(f"MCP tool {tool_name} returned no text.")
	return text


def _parse_password_examples(content: str) -> list[tuple[str, str]]:
	"""Extract explicitly prefixed synthetic password records from fixture text."""
	examples: list[tuple[str, str]] = []
	labels: set[str] = set()
	for line_number, line in enumerate(content.splitlines(), start=1):
		if not line.strip():
			continue
		if not line.lower().startswith("password"):
			continue
		kind, separator, remainder = line.partition("|")
		if not separator or kind != "password":
			raise ValueError(f"Malformed password example on fixture line {line_number}.")
		label, separator, password = remainder.partition("|")
		if (
			not separator
			or not LABEL_PATTERN.fullmatch(label)
			or not password
			or label in labels
		):
			raise ValueError(f"Malformed password example on fixture line {line_number}.")
		labels.add(label)
		examples.append((label, password))
		if len(examples) > 50:
			raise ValueError("Fixture contains more than 50 synthetic examples.")
	return examples


def _summarize_git_diff(diff: str, fixture_name: str, label: str) -> GitDiffSummary:
	"""Count changed lines for the designated file when text diff data permits."""
	files: set[str] = set()
	additions = 0
	deletions = 0
	binary_diff = False
	for line in diff.splitlines():
		if line.startswith("diff --git "):
			match = re.fullmatch(r"diff --git a/([^ ]+) b/([^ ]+)", line)
			if match is None or match.group(1) != match.group(2):
				raise RuntimeError(f"{label} diff contains an unexpected path format.")
			files.add(match.group(1))
		elif line.startswith("Binary files "):
			binary_diff = True
		elif line.startswith("+") and not line.startswith("+++"):
			additions += 1
		elif line.startswith("-") and not line.startswith("---"):
			deletions += 1

	if files - {fixture_name}:
		raise RuntimeError(f"{label} diff includes files outside the designated fixture.")
	if binary_diff:
		return GitDiffSummary(tuple(sorted(files)), None, None)
	return GitDiffSummary(tuple(sorted(files)), additions, deletions)


def _render_diff_summary(label: str, summary: GitDiffSummary) -> str:
	"""Format one diff summary without including fixture contents."""
	if not summary.files:
		return f"{label}: no changes (+0/-0)"
	if summary.additions is None or summary.deletions is None:
		return f"{label}: {', '.join(summary.files)} (binary counts unavailable)"
	return (
		f"{label}: {', '.join(summary.files)} "
		f"(+{summary.additions}/-{summary.deletions})"
	)


def _parse_secret_scan(
	result_text: str, fixture_line_count: int
) -> list[dict[str, int | str]]:
	"""Validate redacted scanner output and reject any unexpected result shape."""
	try:
		result = json.loads(result_text)
	except json.JSONDecodeError as error:
		raise RuntimeError("Secret scanner returned malformed JSON.") from error
	if not isinstance(result, dict) or not isinstance(result.get("findings"), list):
		raise RuntimeError("Secret scanner returned an invalid findings structure.")
	if "pattern-based" not in str(result.get("disclaimer", "")).lower():
		raise RuntimeError("Secret scanner omitted its pattern-based limitation.")

	findings: list[dict[str, int | str]] = []
	for finding in result["findings"]:
		if not isinstance(finding, dict):
			raise RuntimeError("Secret scanner returned an invalid finding.")
		finding_type = finding.get("type")
		line_number = finding.get("line")
		count = finding.get("count")
		if (
			finding_type not in {"API-key-like", "token-like"}
			or type(line_number) is not int
			or not 1 <= line_number <= fixture_line_count
			or type(count) is not int
			or count < 1
		):
			raise RuntimeError("Secret scanner returned an invalid finding.")
		findings.append({"type": finding_type, "line": line_number, "count": count})
	return findings


def _risk_rank(risk: str) -> int:
	"""Return the fixed ordering used to combine demo risk classifications."""
	return {"informational": 0, "low": 1, "medium": 2, "high": 3}[risk]


def _classify_risk(
	secret_findings: list[dict[str, int | str]],
	password_assessments: list[tuple[str, str]],
	baseline_match: bool | None,
) -> tuple[str, list[str], list[str]]:
	"""Apply the documented demo risk rules and return findings and actions."""
	risk = "informational"
	findings: list[str] = []
	recommendations: list[str] = []
	if secret_findings:
		risk = "high"
		for finding in secret_findings:
			findings.append(
				f"High: {finding['type']} pattern on line {finding['line']} "
				f"(count {finding['count']}); matched text is withheld."
			)
		recommendations.append(
			"Review these synthetic matches and validate detection rules; never put real credentials in this fixture."
		)
	for label, assessment in password_assessments:
		if assessment == "weak":
			risk = max((risk, "medium"), key=_risk_rank)
			findings.append(f"Medium: synthetic password example '{label}' assessed weak.")
			recommendations.append("Use stronger synthetic examples when demonstrating password policy.")
		elif assessment == "moderate":
			risk = max((risk, "low"), key=_risk_rank)
			findings.append(f"Low: synthetic password example '{label}' assessed moderate.")
	if baseline_match is False:
		risk = max((risk, "medium"), key=_risk_rank)
		findings.append("Medium: fixture SHA-256 does not match the supplied baseline.")
		recommendations.append("Investigate the difference and verify the baseline through a trusted channel.")
	if not findings:
		findings.append("Informational: no configured synthetic patterns or password concerns were detected.")
	if not recommendations:
		recommendations.append("No action indicated by this teaching/demo model; review changes in context.")
	return risk, findings, recommendations


async def _run_tools(
	repository: Path, fixture: Path, baseline_sha256: str | None
) -> str:
	"""Coordinate read-only Git review and redacted synthetic-fixture analysis."""
	environment = _server_environment()
	uvx_path = shutil.which("uvx", path=environment["PATH"])
	if uvx_path is None:
		raise RuntimeError("uvx was not found; install it separately from hw4's environment.")

	custom_parameters = StdioServerParameters(
		command=sys.executable,
		args=[str(CUSTOM_SERVER_PATH)],
		cwd=str(repository),
		env=environment,
	)
	git_parameters = StdioServerParameters(
		command=uvx_path,
		args=[
			"--from",
			f"mcp-server-git=={GIT_SERVER_VERSION}",
			"mcp-server-git",
			"--repository",
			str(repository),
		],
		cwd=str(repository),
		env=environment,
	)

	async with AsyncExitStack() as stack:
		custom_read, custom_write = await stack.enter_async_context(
			stdio_client(custom_parameters)
		)
		custom_session = await stack.enter_async_context(
			ClientSession(custom_read, custom_write)
		)
		await custom_session.initialize()

		git_read, git_write = await stack.enter_async_context(stdio_client(git_parameters))
		git_session = await stack.enter_async_context(ClientSession(git_read, git_write))
		await git_session.initialize()

		custom_tools = {tool.name for tool in (await custom_session.list_tools()).tools}
		git_tools = {tool.name for tool in (await git_session.list_tools()).tools}
		if not CUSTOM_SERVER_TOOLS <= custom_tools:
			raise RuntimeError("Custom MCP server is missing a required analysis tool.")
		if not GIT_SERVER_TOOLS <= git_tools:
			raise RuntimeError("Official Git MCP server is missing a required read tool.")

		status = _tool_text(
			await git_session.call_tool("git_status", {"repo_path": str(repository)}),
			"git_status",
		)
		staged_diff = _tool_text(
			await git_session.call_tool(
				"git_diff_staged",
				{"repo_path": str(repository), "context_lines": 0},
			),
			"git_diff_staged",
		)
		unstaged_diff = _tool_text(
			await git_session.call_tool(
				"git_diff_unstaged",
				{"repo_path": str(repository), "context_lines": 0},
			),
			"git_diff_unstaged",
		)
		staged_summary = _summarize_git_diff(staged_diff, fixture.name, "Staged")
		unstaged_summary = _summarize_git_diff(unstaged_diff, fixture.name, "Unstaged")

		scan_text = _tool_text(
			await custom_session.call_tool(
				"scan_synthetic_secrets", {"file_path": str(fixture)}
			),
			"scan_synthetic_secrets",
		)
		try:
			fixture_content = fixture.read_text(encoding="utf-8")
		except (OSError, UnicodeDecodeError) as error:
			raise RuntimeError("The designated fixture could not be parsed safely.") from error
		if "\x00" in fixture_content:
			raise RuntimeError("The designated fixture contains binary data.")
		secret_findings = _parse_secret_scan(scan_text, len(fixture_content.splitlines()))
		examples = _parse_password_examples(fixture_content)

		password_assessments: list[tuple[str, str]] = []
		for label, password in examples:
			assessment_text = _tool_text(
				await custom_session.call_tool(
					"analyze_password_strength", {"password": password}
				),
				"analyze_password_strength",
			)
			assessment_match = ASSESSMENT_PATTERN.match(assessment_text)
			if assessment_match is None:
				raise RuntimeError("Password tool returned an unrecognized assessment.")
			password_assessments.append(
				(label, assessment_match.group(1).lower())
			)

		hash_arguments: dict[str, str] = {"file_path": str(fixture)}
		if baseline_sha256 is not None:
			hash_arguments["baseline_sha256"] = baseline_sha256
		digest = _tool_text(
			await custom_session.call_tool(
				"calculate_sha256", hash_arguments
			),
			"calculate_sha256",
		)
		if baseline_sha256 is None:
			if not HASH_PATTERN.fullmatch(digest):
				raise RuntimeError("SHA-256 tool returned an invalid digest.")
			baseline_match = None
			file_hash = digest
		else:
			try:
				hash_result = json.loads(digest)
			except json.JSONDecodeError as error:
				raise RuntimeError("SHA-256 tool returned malformed comparison data.") from error
			file_hash = hash_result.get("sha256") if isinstance(hash_result, dict) else None
			baseline_match = (
				hash_result.get("baseline_match") if isinstance(hash_result, dict) else None
			)
			if not isinstance(file_hash, str) or not HASH_PATTERN.fullmatch(file_hash):
				raise RuntimeError("SHA-256 tool returned an invalid digest.")
			if type(baseline_match) is not bool:
				raise RuntimeError("SHA-256 tool returned an invalid baseline comparison.")

	risk, findings, recommendations = _classify_risk(
		secret_findings, password_assessments, baseline_match
	)
	changed_files = sorted(set(staged_summary.files) | set(unstaged_summary.files))
	secret_lines = [
		f"- {finding['type']} pattern: line {finding['line']}, count {finding['count']}"
		for finding in secret_findings
	]
	password_lines = [
		f"- {label}: {assessment}"
		for label, assessment in password_assessments
	] or ["- No explicitly labeled synthetic password examples."]
	return "\n".join(
		(
			"Synthetic fixture review",
			"Audit scope",
			f"- Disposable repository: {repository.name}",
			f"- Designated fixture: {fixture.name} (bounded UTF-8 text only)",
			"- MCP tools: git_status, git_diff_staged, git_diff_unstaged, scan_synthetic_secrets, calculate_sha256, analyze_password_strength.",
			"- Git MCP repository scope selects a path; it is not a read-only security boundary.",
			"Git status and change summary",
			f"- Status: {status}",
			f"- Changed filenames: {', '.join(changed_files) if changed_files else 'none'}",
			f"- {_render_diff_summary('Staged', staged_summary)}",
			f"- {_render_diff_summary('Unstaged', unstaged_summary)}",
			f"- Staged additions: {len(examples)} synthetic example(s)",
			"- Unexpected file types: none (only the designated .txt fixture is permitted).",
			"Synthetic secret-scan findings",
			*(secret_lines if secret_lines else ["- No configured patterns detected."]),
			"- Pattern-based detection only; this does not guarantee all secrets will be found.",
			"File integrity and hash",
			f"- SHA-256: {file_hash}",
			(
				"- Baseline comparison: not supplied."
				if baseline_match is None
				else f"- Baseline comparison: {'match' if baseline_match else 'mismatch'}."
			),
			"- A matching hash does not prove file authenticity.",
			"Synthetic password assessments",
			*password_lines,
			"- Educational heuristic only; not a guarantee of password security.",
			"Findings and recommendations",
			*(f"- {finding}" for finding in findings),
			*(f"- Recommendation: {recommendation}" for recommendation in recommendations),
			"- Risk levels are a deterministic teaching/demo model, not a professional security certification.",
			"Overall result",
			f"- {risk.upper()}",
		)
	)


async def _async_main(
	repository: str, fixture: str, baseline_sha256: str | None
) -> str:
	"""Validate the target, then run the two MCP servers."""
	repo_path, fixture_path = validate_scratch_fixture(repository, fixture)
	return await _run_tools(repo_path, fixture_path, baseline_sha256)


def main() -> int:
	"""Parse arguments, run the review, and report errors without a traceback."""
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--repository", required=True, help="Disposable scratch Git repository")
	parser.add_argument("--fixture", required=True, help="Single synthetic fixture in that repository")
	parser.add_argument(
		"--baseline-sha256",
		help="Optional trusted SHA-256 baseline for the designated fixture",
	)
	arguments = parser.parse_args()

	try:
		if arguments.baseline_sha256 is not None and not HASH_PATTERN.fullmatch(
			arguments.baseline_sha256
		):
			raise ValueError("Baseline must be exactly 64 lowercase hexadecimal characters.")
		report = asyncio.run(
			_async_main(
				arguments.repository,
				arguments.fixture,
				arguments.baseline_sha256,
			)
		)
	except Exception as error:
		print(f"MCP review failed: {error}", file=sys.stderr)
		return 1
	print(report)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

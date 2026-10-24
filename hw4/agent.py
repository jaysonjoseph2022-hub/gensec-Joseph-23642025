"""Review one synthetic password fixture with Git and custom MCP tools."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import sys
import tempfile
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult


GIT_SERVER_VERSION = "2026.10.19"
GIT_SERVER_TOOLS = {"git_status", "git_diff_staged"}
CUSTOM_SERVER_TOOLS = {"analyze_password_strength", "calculate_sha256"}
LABEL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")
ASSESSMENT_PATTERN = re.compile(
	r"\ABasic assessment: (weak|moderate|strong)\.", re.IGNORECASE
)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
PROJECT_DIR = Path(__file__).resolve().parent
CUSTOM_SERVER_PATH = PROJECT_DIR / "mcp-server.py"


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
	if not (repo_path / ".git").is_dir():
		raise ValueError("The designated scratch directory must be a Git repository.")

	fixture_input = Path(fixture)
	fixture_candidate = fixture_input if fixture_input.is_absolute() else repo_path / fixture_input
	if fixture_candidate.is_symlink():
		raise ValueError("The synthetic fixture cannot be a symlink.")
	fixture_path = fixture_candidate.resolve(strict=True)
	if fixture_path.parent != repo_path or not fixture_path.is_file():
		raise ValueError("Fixture must be a regular file directly inside the scratch repository.")
	if not re.fullmatch(r"[A-Za-z0-9_.-]+", fixture_path.name):
		raise ValueError("Fixture filename must use only letters, digits, dots, underscores, or hyphens.")
	if fixture_path.stat().st_size > 32_768:
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


def _parse_staged_examples(diff: str, fixture_name: str) -> list[tuple[str, str]]:
	"""Extract labeled examples only from additions to the designated fixture."""
	changed_paths: set[str] = set()
	for line in diff.splitlines():
		if line.startswith("diff --git "):
			match = re.fullmatch(r"diff --git a/([^ ]+) b/([^ ]+)", line)
			if match is None or match.group(1) != match.group(2):
				raise RuntimeError("Staged diff contains an unexpected path format.")
			changed_paths.add(match.group(1))
	if changed_paths != {fixture_name}:
		raise RuntimeError("Staged diff must contain only the designated fixture.")

	examples: list[tuple[str, str]] = []
	for line in diff.splitlines():
		if not line.startswith("+") or line.startswith("+++"):
			continue
		entry = line[1:].rstrip("\r")
		if not entry:
			continue
		label, separator, password = entry.partition("|")
		if not separator or not LABEL_PATTERN.fullmatch(label) or not password:
			raise RuntimeError("Fixture additions must be labeled synthetic examples.")
		examples.append((label, password))
		if len(examples) > 50:
			raise RuntimeError("Fixture contains more than 50 synthetic examples.")
	if not examples:
		raise RuntimeError("Staged fixture contains no added synthetic examples.")
	return examples


async def _run_tools(repository: Path, fixture: Path) -> str:
	"""Coordinate read-only Git inspection and custom fixture analysis."""
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
		examples = _parse_staged_examples(staged_diff, fixture.name)

		assessments: list[str] = []
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
			assessments.append(f"- {label}: {assessment_match.group(1).lower()}")

		digest = _tool_text(
			await custom_session.call_tool(
				"calculate_sha256", {"file_path": str(fixture)}
			),
			"calculate_sha256",
		)
		if not HASH_PATTERN.fullmatch(digest):
			raise RuntimeError("SHA-256 tool returned an invalid digest.")

	return "\n".join(
		(
			"Synthetic fixture review",
			f"Fixture: {fixture.name}",
			f"Git status: {status}",
			f"Staged additions: {len(examples)} synthetic example(s)",
			"Password assessments:",
			*assessments,
			f"SHA-256: {digest}",
		)
	)


async def _async_main(repository: str, fixture: str) -> str:
	"""Validate the target, then run the two MCP servers."""
	repo_path, fixture_path = validate_scratch_fixture(repository, fixture)
	return await _run_tools(repo_path, fixture_path)


def main() -> int:
	"""Parse arguments, run the review, and report errors without a traceback."""
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--repository", required=True, help="Disposable scratch Git repository")
	parser.add_argument("--fixture", required=True, help="Single synthetic fixture in that repository")
	arguments = parser.parse_args()

	try:
		report = asyncio.run(_async_main(arguments.repository, arguments.fixture))
	except Exception as error:
		print(f"MCP review failed: {error}", file=sys.stderr)
		return 1
	print(report)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

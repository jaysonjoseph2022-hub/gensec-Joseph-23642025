"""Educational MCP tools for password heuristics and file SHA-256 hashing."""

import hashlib
import hmac
import json
import os
import re
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("hw4-tools")
MAX_FIXTURE_BYTES = 32_768
API_KEY_PATTERN = re.compile(
	r"\b(?:api[_-]?key|secret[_-]?key)\b\s*[:=]\s*['\"]?([A-Za-z0-9._~+/-]{12,})",
	re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(
	r"\b(?:access[_-]?token|auth[_-]?token|token)\b\s*[:=]\s*['\"]?([A-Za-z0-9._~+/-]{12,})",
	re.IGNORECASE,
)


def _read_designated_fixture(file_path: str) -> str:
	"""Read one bounded UTF-8 text file from a disposable hw4 scratch repo."""
	fixture = Path(file_path)
	if fixture.is_symlink():
		raise ValueError("The designated fixture cannot be a symlink.")

	try:
		resolved_fixture = fixture.resolve(strict=True)
		resolved_repo = resolved_fixture.parent
		temp_root = Path(tempfile.gettempdir()).resolve()
		if (
			not resolved_repo.is_relative_to(temp_root)
			or not resolved_repo.name.startswith("hw4-mcp-scratch-")
			or resolved_repo == temp_root
		):
			raise ValueError("Fixture must be inside a hw4-mcp-scratch-* directory in the temp area.")
		git_dir = resolved_repo / ".git"
		if git_dir.is_symlink() or not git_dir.is_dir():
			raise ValueError("The designated fixture must be inside a Git scratch repository.")
		if not resolved_fixture.is_file() or resolved_fixture.suffix.lower() != ".txt":
			raise ValueError("The designated fixture must be a regular .txt file.")
		children = {entry.name for entry in resolved_repo.iterdir() if entry.name != ".git"}
		if children != {resolved_fixture.name}:
			raise ValueError("Scratch repository must contain only the designated fixture besides .git.")
		if resolved_fixture.stat().st_size > MAX_FIXTURE_BYTES:
			raise ValueError("The designated fixture exceeds the 32 KiB size limit.")
		content = resolved_fixture.read_bytes()
	except (OSError, RuntimeError) as error:
		raise ValueError("The designated fixture could not be read safely.") from error

	if b"\x00" in content:
		raise ValueError("The designated fixture must be text, not binary data.")
	try:
		return content.decode("utf-8")
	except UnicodeDecodeError as error:
		raise ValueError("The designated fixture must be valid UTF-8 text.") from error


@mcp.tool()
def analyze_password_strength(password: str) -> str:
	"""Give a basic password-strength estimate without storing or logging it.

	This educational heuristic checks length and character variety. It is not
	a guarantee of security and does not check passwords against known breaches.
	"""
	score = sum(
		(
			len(password) >= 8,
			len(password) >= 12,
			any(char.islower() for char in password)
			and any(char.isupper() for char in password),
			any(char.isdigit() for char in password)
			and any(not char.isalnum() for char in password),
		)
	)

	if score <= 1:
		assessment = "weak"
	elif score <= 2:
		assessment = "moderate"
	else:
		assessment = "strong"

	return (
		f"Basic assessment: {assessment}. "
		"This is an educational heuristic, not a guarantee of security."
	)


@mcp.tool()
def scan_synthetic_secrets(file_path: str) -> str:
	"""Find key/token-like patterns in one bounded synthetic text fixture.

	Returns only pattern type, line number, and match count, never matched values.
	This pattern-based scan is educational and cannot guarantee that all secrets
	will be found. The path must identify the sole .txt fixture in a disposable
	``/tmp/hw4-mcp-scratch-*`` Git repository.
	"""
	content = _read_designated_fixture(file_path)
	findings: list[dict[str, int | str]] = []
	for line_number, line in enumerate(content.splitlines(), start=1):
		for finding_type, pattern in (
			("API-key-like", API_KEY_PATTERN),
			("token-like", TOKEN_PATTERN),
		):
			count = sum(1 for _ in pattern.finditer(line))
			if count:
				findings.append(
					{"type": finding_type, "line": line_number, "count": count}
				)
	return json.dumps(
		{
			"disclaimer": "Pattern-based detection only; this does not guarantee all secrets will be found.",
			"findings": findings,
		},
		separators=(",", ":"),
	)


@mcp.tool()
def calculate_sha256(file_path: str, baseline_sha256: str | None = None) -> str:
	"""Return SHA-256 and optionally compare it with a supplied trusted baseline.

	The baseline is read-only input and is never created or replaced by this tool.
	A matching hash does not prove that a file is authentic.
	"""
	digest = hashlib.sha256()

	try:
		with Path(file_path).open("rb") as file:
			for chunk in iter(lambda: file.read(1024 * 1024), b""):
				digest.update(chunk)
	except FileNotFoundError:
		return "File not found."
	except PermissionError:
		return "Permission denied; the file could not be read."
	except IsADirectoryError:
		return "The path is a directory, not a file."
	except (OSError, ValueError):
		return "The file could not be read."

	file_hash = digest.hexdigest()
	if baseline_sha256 is None:
		return file_hash
	if not re.fullmatch(r"[0-9a-fA-F]{64}", baseline_sha256):
		return "Invalid baseline SHA-256; expected 64 hexadecimal characters."
	return json.dumps(
		{
			"sha256": file_hash,
			"baseline_match": hmac.compare_digest(
				file_hash, baseline_sha256.lower()
			),
			"disclaimer": "A matching hash does not prove file authenticity.",
		},
		separators=(",", ":"),
	)


if __name__ == "__main__":
	mcp.run(transport="stdio")

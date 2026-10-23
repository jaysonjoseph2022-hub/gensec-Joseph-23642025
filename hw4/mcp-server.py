"""Educational MCP tools for password heuristics and file SHA-256 hashing."""

import hashlib
from pathlib import Path

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("hw4-tools")


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
def calculate_sha256(file_path: str) -> str:
	"""Return a file's SHA-256 hash, or a safe message if it cannot be read."""
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

	return digest.hexdigest()


if __name__ == "__main__":
	mcp.run(transport="stdio")

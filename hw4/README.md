# HW4 Multi-Tool Security Audit

## Architecture

`agent.py` coordinates two stdio MCP servers. It launches the custom server in this project's existing uv environment and launches the official Git MCP package, pinned to `2026.10.19`, through `uvx` in an isolated environment. Git MCP supplies status, staged diff, and unstaged diff; the custom server supplies labeled synthetic password assessment, bounded secret-pattern scanning, and SHA-256 hashing with optional baseline comparison.

The audit accepts only a disposable Git repository named `hw4-mcp-scratch-*` under the system temporary directory. It must contain exactly one regular `.txt` fixture besides `.git`, and that fixture is limited to 32 KiB. The agent reads only Git status/diff and uses the custom tools on that fixture. It does not invoke Git write tools.

The Git server's `--repository` option selects a repository path; it is not a read-only sandbox. The server has write-capable tools available, even though this agent calls only read tools. Never point this workflow at the course repository or a repository containing real credentials.

## Prerequisites and setup

- Python and `uv` are installed.
- Run commands from `hw4/` so `uv` uses this project's existing environment and lockfile.
- `uvx` must be available. On first use, it may need network access to download the pinned Git MCP server into its separate tool environment. It does not install that server's MCP SDK 2.x dependencies into the hw4 environment.
- No API keys or credentials are required.

Run the tests with:

```bash
uv run python -m unittest -v
```

## Fixture format and risk rules

Password examples are processed only when explicitly labeled with this format:

```text
password|synthetic-label|invented-value
```

The scanner recognizes API-key-like and token-like text patterns. It reports only finding type, line, and count; it never returns a matched value. Pattern-based scanning can miss secrets and is not a guarantee that all secrets will be found. Use invented values only.

Risk classification is a deterministic teaching/demo model, not a professional security certification:

- **High:** any configured API-key-like or token-like pattern is detected.
- **Medium:** a synthetic password is assessed weak, or a supplied SHA-256 baseline does not match.
- **Low:** a synthetic password is assessed moderate and no higher-level finding exists.
- **Informational:** no configured patterns or concerns are detected.

A matching hash identifies matching bytes relative to the supplied baseline; it does not prove authenticity. The agent never creates or replaces a trusted baseline. Supply `--baseline-sha256` only when you already have a trusted 64-character SHA-256 value.

## Clean demo

From `hw4/`, this creates a temporary repository with a single strong synthetic example, runs the audit, and removes the repository when the shell exits:

```bash
set -e
SCRATCH="$(mktemp -d /tmp/hw4-mcp-scratch-clean-XXXXXX)"
trap 'rm -rf -- "$SCRATCH"' EXIT
git -C "$SCRATCH" init --quiet
printf '%s\n' 'password|synthetic-strong|Blue!Cedar47Window' > "$SCRATCH/password-examples.txt"
git -C "$SCRATCH" add password-examples.txt
uv run python agent.py --repository "$SCRATCH" --fixture password-examples.txt
```

Expected overall result: `INFORMATIONAL`.

## Problematic synthetic demo

This separate fixture has a weak synthetic password and invented key/token-like values. The report should show the pattern types and line numbers, but not the values:

```bash
set -e
SCRATCH="$(mktemp -d /tmp/hw4-mcp-scratch-problem-XXXXXX)"
trap 'rm -rf -- "$SCRATCH"' EXIT
git -C "$SCRATCH" init --quiet
printf '%s\n' \
  'password|synthetic-weak|owl7' \
  'API_KEY=synthetic_api_key_demo_123456789' \
  'ACCESS_TOKEN=synthetic_access_token_demo_123456789' \
  > "$SCRATCH/password-examples.txt"
git -C "$SCRATCH" add password-examples.txt
uv run python agent.py --repository "$SCRATCH" --fixture password-examples.txt
```

Expected overall result: `HIGH` due to the detected synthetic patterns. The weak synthetic password is separately reported as a medium finding.

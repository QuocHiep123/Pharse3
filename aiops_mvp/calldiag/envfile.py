"""Minimal `.env` loader for the CLI and UI entry points (no python-dotenv dependency).

Loaded once at start-up, never inside the pipeline. A variable already set in the shell always
wins over the file. CALLDIAG_ENV_FILE points to another file; set it to an empty string to skip.
"""

import os
from pathlib import Path

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"   # aiops_mvp/.env, whatever the cwd


def env_file_path() -> Path | None:
    override = os.environ.get("CALLDIAG_ENV_FILE")
    if override is None:
        return DEFAULT_ENV_FILE
    return Path(override).expanduser() if override.strip() else None


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def load_env_file(path: Path | None = None) -> list[str]:
    """Set variables from the file that are not set yet; return their names (never the values)."""
    target = path if path is not None else env_file_path()
    if target is None or not target.is_file():
        return []
    loaded = []
    for key, value in parse_env(target.read_text(encoding="utf-8")).items():
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded

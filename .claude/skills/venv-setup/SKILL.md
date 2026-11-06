---
name: venv-setup
description: Create, rebuild, or verify the project's Python virtual environment (.venv) on Windows. Use when starting work, after changing requirements, when imports fail, or when the venv has stale packages.
---

# venv-setup

Project venv lives at `.venv/` (gitignored). Python 3.12.

## Verify
```bash
.venv/Scripts/python --version
.venv/Scripts/python -m pip list
```

## Rebuild clean (stale packages, broken env)
Confirm with the user before deleting `.venv`.
```bash
rm -rf .venv
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
# then install from whichever exists:
.venv/Scripts/python -m pip install -e ".[dev]"      # if pyproject.toml
.venv/Scripts/python -m pip install -r requirements.txt  # else
```

## Rules
- Always call `.venv/Scripts/python -m ...` explicitly; don't rely on activation.
- Add new dependencies to `pyproject.toml` / `requirements.txt` in the same change that uses them.
- Never `pip install` into the global interpreter.

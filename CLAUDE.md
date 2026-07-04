# Repo Conventions

## Python testing

- Every `assert` in a Python test must include an explanatory failure message describing what the assertion verifies (and why it should hold), not just what was compared. Prefer `assert x == y, "why this should be true"` over a bare `assert x == y`.

## Python project layout

- A Python subproject with a dedicated test suite should keep source modules under a `src/` directory, with `tests/` as a sibling directory (e.g. `sim/src/` and `sim/tests/`). Don't mix source modules directly alongside `tests/`, `.env`, `Dockerfile`, `requirements.txt`, etc.

# Repo Conventions

## Python testing

- Every `assert` in a Python test must include an explanatory failure message describing what the assertion verifies (and why it should hold), not just what was compared. Prefer `assert x == y, "why this should be true"` over a bare `assert x == y`.

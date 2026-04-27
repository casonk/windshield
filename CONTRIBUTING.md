# Contributing to Windshield

## Getting Started

1. Clone the repo and install in dev mode:
   ```bash
   pip install -e ".[dev]"
   ```

2. Install pre-commit hooks:
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Development Workflow

1. Create a feature branch from `main`.
2. Make changes following the code style (ruff + black, 100-char line length).
3. Add tests for new functionality.
4. Run local CI:
   ```bash
   pre-commit run --all-files
   pytest -q
   ```
5. Open a PR using the provided template.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation changes
- `test:` — test additions or changes
- `refactor:` — code restructuring without behavior change
- `chore:` — maintenance tasks
- `ci:` — CI/CD changes

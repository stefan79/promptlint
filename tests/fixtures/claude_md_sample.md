# CLAUDE.md

## Project Context

This is a Python web application using FastAPI and PostgreSQL. The codebase follows a hexagonal architecture pattern.

## Code Style

- Use type hints for all function signatures.
- Follow PEP 8 naming conventions.
- Keep functions under 30 lines.
- Prefer composition over inheritance.
- Use dataclasses for value objects.
- Never use global mutable state.

## Testing

- Write pytest tests for all new code.
- Use fixtures instead of setUp/tearDown.
- Mock external services, never hit real APIs in tests.
- Aim for 80% code coverage on new code.
- Always run the test suite before committing.

## Git

- Write commit messages in imperative mood.
- Keep commits atomic — one logical change per commit.
- Never force-push to main.
- Always rebase feature branches before merging.

## Dependencies

- Pin all dependency versions in requirements.txt.
- Prefer stdlib solutions over third-party packages.
- Check licenses before adding new dependencies.

## Security

- Never log sensitive data (passwords, tokens, PII).
- Always validate user input at API boundaries.
- Use parameterized queries, never string concatenation for SQL.
- Never commit secrets or API keys to the repository.
- Always use HTTPS for external API calls.

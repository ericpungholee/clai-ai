# Contributing

Thanks for taking the time to improve Clai.

## Development setup

1. Fork and clone the repository.
2. Copy `.env.example` to `.env`.
3. Run `make dev` for the Docker development stack.
4. Run `make lint` and `make test` before opening a pull request.

Use `make test-postgres` for migration or database constraint changes and `make test-browser` for user-interface behavior. Tests must use the existing fake providers and local fake API; do not add tests that call paid provider endpoints.

Keep pull requests focused. Include a migration when changing persisted data, update the architecture guide when a system boundary changes, and add behavior-focused coverage for regressions.

## Pull requests

- Explain the user-visible problem and the resulting behavior.
- List the validation commands you ran.
- Do not commit credentials, generated artifacts, browser reports, or local environment files.
- Confirm that new dependencies are necessary and recorded in the appropriate lockfile.

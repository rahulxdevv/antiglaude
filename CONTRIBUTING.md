# Contributing to Antiglaude

Thank you for your interest in contributing to **Antiglaude**. Contributions, bug fixes, feature requests, and documentation improvements are welcome.

## Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/antiglaude.git
   cd antiglaude
   ```

2. **Bootstrap dependencies with uv:**
   ```bash
   make setup
   ```

3. **Run test suite:**
   ```bash
   make test
   ```

## Security Best Practices

- Never commit sensitive credentials, private tokens, or SQLite databases.
- The `.gitignore` is configured to prevent credential exposure. Always run `git status` to verify staged changes before committing.

## Submitting Pull Requests

1. Create a feature branch: `git checkout -b feat/your-feature-name`
2. Implement your changes with clean, well-tested code.
3. Verify the test suite passes: `make test`
4. Commit your changes: `git commit -m 'feat: description of change'`
5. Push to your fork: `git push origin feat/your-feature-name`
6. Open a Pull Request against the `main` branch.

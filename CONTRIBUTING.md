# Contributing to Antiglaude Bridge

Thank you for your interest in contributing to **Antiglaude Bridge**! We welcome contributions, bug fixes, feature requests, and documentation improvements.

## 🛠️ Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/antiglaude-bridge.git
   cd antiglaude-bridge
   ```

2. **Set up a Python virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install pytest pytest-asyncio
   ```

3. **Run test suite:**
   ```bash
   python3 -m pytest tests/ -v
   ```

## 🔒 Security Best Practices

- **NEVER commit sensitive credentials**, private tokens, `ya29` keys, or SQLite databases.
- The `.gitignore` is strictly configured to protect user secrets. Always run `git status` and verify staged changes before committing.

## 📝 Submitting Pull Requests

1. Create a feature branch: `git checkout -b feat/your-feature-name`
2. Implement your changes with clean, readable code and tests where applicable.
3. Verify all tests pass: `pytest tests/ -v`
4. Commit your changes: `git commit -m 'feat: description of change'`
5. Push to your fork: `git push origin feat/your-feature-name`
6. Open a Pull Request against the `main` branch.

.PHONY: all setup start run serve stop status claude test tui panel setup-claude daemon-install daemon-status daemon-uninstall build check-dist clean help

PORT ?= 8080
HOST ?= 127.0.0.1
VENV = .venv
PYTHON = $(VENV)/bin/python
UV ?= $(shell which uv 2>/dev/null || echo "uv")

all: start

# Setup virtual environment and dependencies using uv
setup:
	@if ! command -v $(UV) >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment with uv..."; \
		$(UV) venv $(VENV); \
	fi
	@echo "Syncing dependencies with uv..."
	@$(UV) pip install -e . --quiet
	@echo "Dependencies ready."

# Start the gateway server (auto-installs if needed)
start run serve: setup
	@echo "Starting Antiglaude Bridge on http://$(HOST):$(PORT)..."
	@$(PYTHON) -m gateway.cli start --host $(HOST) --port $(PORT)

# Check bridge status & account diagnostics
status: setup
	@$(PYTHON) -m gateway.cli status

# Launch Claude Code directly through the bridge
claude: setup
	@echo "Launching Claude Code connected to http://$(HOST):$(PORT)..."
	@ANTHROPIC_BASE_URL="http://$(HOST):$(PORT)" \
	 ANTHROPIC_API_KEY="test" \
	 CLAUDE_CODE_AUTO_MODE_SERVER="0" \
	 claude $(ARGS)

# Run test suite
test: setup
	@$(UV) pip install pytest pytest-asyncio httpx --quiet
	@$(PYTHON) -m pytest tests/ -v

# Launch interactive Terminal UI (TUI) Control Panel
tui panel: setup
	@$(PYTHON) -m gateway.cli tui

# Configure Claude Code settings.json with default bridge URL & /model picker
setup-claude: setup
	@$(PYTHON) -m gateway.cli setup-claude --host $(HOST) --port $(PORT)

# macOS LaunchAgent daemon management (auto-starts with macOS & Antigravity)
daemon-install: setup
	@$(PYTHON) -m gateway.cli daemon install --port $(PORT)

daemon-status: setup
	@$(PYTHON) -m gateway.cli daemon status

daemon-uninstall: setup
	@$(PYTHON) -m gateway.cli daemon uninstall

# Stop any running bridge process on the configured port
stop:
	@echo "Stopping any bridge process on port $(PORT)..."
	@-lsof -ti :$(PORT) | xargs kill -9 2>/dev/null || true
	@echo "Port $(PORT) freed."

# Build distribution packages (wheel and sdist) with uv
build: setup
	@echo "Building distribution archives with uv..."
	@$(UV) build

# Verify built packages with twine
check-dist: build
	@$(UV) run twine check dist/*

# Clean temporary files and caches
clean:
	@rm -rf $(VENV) .pytest_cache *.egg-info build dist
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned up environment."

help:
	@echo "Antiglaude Bridge Management Commands:"
	@echo "  make start            - Setup dependencies with uv and start the bridge gateway (default)"
	@echo "  make serve            - Alias for make start (serves Anthropic & OpenAI compatible endpoints)"
	@echo "  make tui              - Launch interactive Terminal Control Panel (live quotas, models, logs)"
	@echo "  make setup-claude     - Configure ~/.claude/settings.json with bridge defaults and /model selector"
	@echo "  make daemon-install   - Install macOS LaunchAgent (auto-starts on boot & Antigravity launch)"
	@echo "  make daemon-status    - Check LaunchAgent daemon status and logs"
	@echo "  make daemon-uninstall - Stop and remove the LaunchAgent service"
	@echo "  make claude           - Launch interactive Claude Code session connected to the bridge"
	@echo "  make status           - Check token health and Google Cloud Code account status"
	@echo "  make test             - Run automated unit and protocol tests"
	@echo "  make build            - Build wheel and sdist distributions with uv"
	@echo "  make check-dist       - Build and validate distribution archives with twine"
	@echo "  make stop             - Stop the gateway running on port $(PORT)"
	@echo "  make clean            - Remove virtual environment and build caches"


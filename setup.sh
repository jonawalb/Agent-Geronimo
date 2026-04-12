#!/bin/bash
# Agent Geronimo Setup Script
# Run this once to install dependencies and configure the alias

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "╔══════════════════════════════════════════════╗"
echo "║       Agent Geronimo — Setup                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not found."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi

# Activate
source "$SCRIPT_DIR/.venv/bin/activate"

# Install dependencies
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

# Install Playwright browsers (for advanced scraping)
echo "Installing Playwright browsers (this may take a moment)..."
python -m playwright install chromium 2>/dev/null || echo "  (Playwright browser install skipped — not critical)"

# Create .env from template if not exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.template" "$SCRIPT_DIR/.env"
    echo "Created .env file — edit it to add API keys (optional)"
fi

# Create output and cache directories
mkdir -p "$SCRIPT_DIR/output" "$SCRIPT_DIR/cache" "$SCRIPT_DIR/output/logs"

# Make geronimo.py executable
chmod +x "$SCRIPT_DIR/geronimo.py"

# Add shell alias
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

ALIAS_LINE="alias geronimo='cd $SCRIPT_DIR && source .venv/bin/activate && python geronimo.py run'"
ALIAS_LINE_2="alias run-agent-geronimo='cd $SCRIPT_DIR && source .venv/bin/activate && python geronimo.py run'"

if [ -n "$SHELL_RC" ]; then
    # Remove old aliases if they exist
    grep -v "alias geronimo=" "$SHELL_RC" > "$SHELL_RC.tmp" 2>/dev/null || true
    grep -v "alias run-agent-geronimo=" "$SHELL_RC.tmp" > "$SHELL_RC" 2>/dev/null || true
    rm -f "$SHELL_RC.tmp"

    # Add new aliases
    echo "" >> "$SHELL_RC"
    echo "# Agent Geronimo" >> "$SHELL_RC"
    echo "$ALIAS_LINE" >> "$SHELL_RC"
    echo "$ALIAS_LINE_2" >> "$SHELL_RC"
    echo "Added shell aliases to $SHELL_RC"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║       Setup Complete!                        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Run Agent Geronimo with any of:"
echo "  cd $SCRIPT_DIR && source .venv/bin/activate && python geronimo.py run"
echo "  geronimo           (after restarting shell)"
echo "  run-agent-geronimo (after restarting shell)"
echo ""
echo "Optional: Edit .env to add API keys for expanded coverage:"
echo "  SAM_GOV_API_KEY   — Free from api.sam.gov (recommended)"
echo "  GOOGLE_API_KEY    — For broader web search coverage"
echo ""

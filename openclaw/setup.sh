#!/usr/bin/env bash
# One-command DSC setup for OpenClaw
# Usage: curl -sSL https://raw.githubusercontent.com/ybj91/decision-structure-compiler/main/openclaw/setup.sh | bash

set -e

echo "=== DSC + OpenClaw Setup ==="
echo ""

# 1. Check Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "Error: Python 3.11+ is required. Install it first."
  exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo "Using Python: $($PYTHON --version)"

# 2. Install DSC
echo ""
echo "Installing DSC..."
$PYTHON -m pip install git+https://github.com/ybj91/decision-structure-compiler.git --quiet

# Verify
if ! command -v dsc &>/dev/null; then
  echo "Warning: 'dsc' not on PATH. You may need to add ~/.local/bin to PATH."
  echo "Trying: $PYTHON -m dsc.cli.main --help"
  $PYTHON -m dsc.cli.main --help >/dev/null 2>&1 && echo "OK — use 'python -m dsc.cli.main' instead of 'dsc'"
else
  echo "DSC installed: $(dsc --version 2>/dev/null || echo 'OK')"
fi

# 3. Copy plugin files
echo ""
echo "Setting up OpenClaw plugin..."

PLUGIN_DIR="${OPENCLAW_PLUGIN_DIR:-./openclaw-plugins/dsc-compiler}"
mkdir -p "$PLUGIN_DIR"

# Download plugin files from GitHub
BASE_URL="https://raw.githubusercontent.com/ybj91/decision-structure-compiler/main/openclaw/plugin"
curl -sSL "$BASE_URL/openclaw.plugin.json" -o "$PLUGIN_DIR/openclaw.plugin.json"
curl -sSL "$BASE_URL/package.json" -o "$PLUGIN_DIR/package.json"

mkdir -p "$PLUGIN_DIR/src"
curl -sSL "$BASE_URL/src/evaluator.ts" -o "$PLUGIN_DIR/src/evaluator.ts"
curl -sSL "$BASE_URL/src/index.ts" -o "$PLUGIN_DIR/src/index.ts"
curl -sSL "$BASE_URL/src/loader.ts" -o "$PLUGIN_DIR/src/loader.ts"

# 4. Create compiled artifacts directory
mkdir -p ./compiled

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Analyze your agent:  dsc analyze code ./your-agent/ --output report.json"
echo "  2. Review the report:   cat report.json | python -m json.tool"
echo "  3. Compile:             dsc init 'My Agent' && dsc analyze apply report.json <project-id>"
echo "  4. Export:              dsc export openclaw <project-id> --output ./compiled/"
echo "  5. Plugin installed at: $PLUGIN_DIR"
echo ""

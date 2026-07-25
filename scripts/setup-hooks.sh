#!/usr/bin/env bash
# Enable this repo's committed git hooks. Run once after cloning:
#   ./scripts/setup-hooks.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

echo "✓ git hooks enabled (core.hooksPath=.githooks)"
echo "  commit-msg guard active — AI-assistant attribution will be rejected."

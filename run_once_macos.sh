#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_PATH="${1:-$SCRIPT_DIR/config.yaml}"

python3 "$SCRIPT_DIR/szu_board_sync.py" --config "$CONFIG_PATH"

#!/usr/bin/env bash
# Career Radar 的 Linux cron 入口。配置路径和虚拟环境都基于脚本位置解析。
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONFIG_PATH="${1:-$PROJECT_DIR/config.yaml}"

cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" -m career_radar run --config "$CONFIG_PATH"


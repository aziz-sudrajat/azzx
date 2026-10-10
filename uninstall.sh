#!/usr/bin/env bash
set -Eeuo pipefail
APP_SLUG="azzatssins-lite-agent"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${APP_SLUG}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/${APP_SLUG}"
if [[ -n "${TERMUX_VERSION:-}" || "${PREFIX:-}" == *"com.termux"* ]]; then
  LAUNCHER="${PREFIX:-/data/data/com.termux/files/usr}/bin/azzx"
else
  LAUNCHER="$HOME/.local/bin/azzx"
fi
rm -f "$LAUNCHER"
rm -rf "$APP_DIR"
echo "AZZX application files removed."
if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$CONFIG_DIR"
  echo "Configuration, API keys, workspace registry and global tools were also removed."
else
  echo "Configuration was kept at: $CONFIG_DIR"
  echo "Use ./uninstall.sh --purge to remove it too."
fi

#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="AZZATSSINS LITE AGENT"
APP_SLUG="azzatssins-lite-agent"
APP_VERSION="10.0.0"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${APP_SLUG}"
VENV_DIR="$APP_DIR/venv"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/${APP_SLUG}"
NO_SYSTEM_DEPS=0
NO_CRYPTO=0
CHECK_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --no-system-deps) NO_SYSTEM_DEPS=1 ;;
    --no-crypto) NO_CRYPTO=1 ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help)
      cat <<HELP
$APP_NAME v$APP_VERSION installer

Usage: ./install.sh [--no-system-deps] [--no-crypto]

  --no-system-deps   Do not invoke apt/pacman/pkg/dnf/etc.
  --no-crypto        Skip optional encrypted-vault dependency.
  --check            Only detect the OS, package manager and prerequisites.
HELP
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

C_RESET='\033[0m'; C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YELLOW='\033[33m'; C_RED='\033[31m'; C_BOLD='\033[1m'
log(){ printf "%b\n" "$*"; }
info(){ log "${C_CYAN}::${C_RESET} $*"; }
ok(){ log "${C_GREEN}✓${C_RESET} $*"; }
warn(){ log "${C_YELLOW}!${C_RESET} $*"; }
die(){ log "${C_RED}ERROR:${C_RESET} $*" >&2; exit 1; }

IS_TERMUX=0
DISTRO="generic"
PKG_MANAGER=""
PYTHON_BIN=""

if [[ -n "${TERMUX_VERSION:-}" || "${PREFIX:-}" == *"com.termux"* || -d "/data/data/com.termux" ]]; then
  IS_TERMUX=1
  DISTRO="termux"
  PKG_MANAGER="pkg"
elif [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  DISTRO="${ID:-linux}"
  if command -v apt-get >/dev/null 2>&1; then PKG_MANAGER="apt"
  elif command -v pacman >/dev/null 2>&1; then PKG_MANAGER="pacman"
  elif command -v dnf >/dev/null 2>&1; then PKG_MANAGER="dnf"
  elif command -v yum >/dev/null 2>&1; then PKG_MANAGER="yum"
  elif command -v zypper >/dev/null 2>&1; then PKG_MANAGER="zypper"
  elif command -v apk >/dev/null 2>&1; then PKG_MANAGER="apk"
  elif command -v xbps-install >/dev/null 2>&1; then PKG_MANAGER="xbps"
  elif command -v emerge >/dev/null 2>&1; then PKG_MANAGER="emerge"
  fi
fi

banner(){
  printf "\n%b\n" "${C_BOLD}${C_CYAN}${APP_NAME} v${APP_VERSION}${C_RESET}"
  printf "%s\n" "Universal Termux / Linux installer"
  printf "%s\n\n" "----------------------------------------"
}

sudo_run(){
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  elif command -v doas >/dev/null 2>&1; then doas "$@"
  else die "Root privileges are required for system packages. Install dependencies manually or rerun with --no-system-deps."
  fi
}

install_system_deps(){
  [[ "$NO_SYSTEM_DEPS" -eq 1 ]] && { warn "Skipping system package installation."; return 0; }
  info "Detected environment: $DISTRO (${PKG_MANAGER:-unknown package manager})"
  case "$PKG_MANAGER" in
    pkg)
      pkg update -y || true
      pkg install -y python git ripgrep openssh
      ;;
    apt)
      sudo_run apt-get update
      sudo_run apt-get install -y python3 python3-venv python3-pip git ripgrep openssh-client ca-certificates
      ;;
    pacman)
      sudo_run pacman -S --needed --noconfirm python python-pip git ripgrep openssh ca-certificates
      ;;
    dnf)
      sudo_run dnf install -y python3 python3-pip git ripgrep openssh-clients ca-certificates
      ;;
    yum)
      sudo_run yum install -y python3 python3-pip git ripgrep openssh-clients ca-certificates
      ;;
    zypper)
      sudo_run zypper --non-interactive install python3 python3-pip git ripgrep openssh ca-certificates
      ;;
    apk)
      sudo_run apk add python3 py3-pip git ripgrep openssh-client ca-certificates
      ;;
    xbps)
      sudo_run xbps-install -Sy python3 python3-pip python3-virtualenv git ripgrep openssh ca-certificates
      ;;
    emerge)
      warn "Gentoo detected; installing common packages with emerge."
      sudo_run emerge --noreplace dev-lang/python dev-vcs/git sys-apps/ripgrep net-misc/openssh
      ;;
    *)
      warn "Unknown package manager. Continuing if Python 3.10+ is already installed."
      ;;
  esac
}

find_python(){
  if [[ -n "${AZZX_PYTHON:-}" && -x "${AZZX_PYTHON}" ]]; then
    PYTHON_BIN="$AZZX_PYTHON"
    return 0
  fi
  local p
  for p in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$p" >/dev/null 2>&1; then
      if "$p" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3,10) else 1)
PY
      then PYTHON_BIN="$(command -v "$p")"; return 0; fi
    fi
  done
  return 1
}

ensure_path(){
  local bin_dir="$1"
  case ":$PATH:" in *":$bin_dir:"*) return 0;; esac
  local line="export PATH=\"$bin_dir:\$PATH\""
  local rc=""
  case "${SHELL:-}" in
    */zsh) rc="$HOME/.zshrc" ;;
    */fish)
      mkdir -p "$HOME/.config/fish"
      local fishrc="$HOME/.config/fish/config.fish"
      if ! grep -Fq "$bin_dir" "$fishrc" 2>/dev/null; then echo "fish_add_path $bin_dir" >> "$fishrc"; fi
      warn "Added $bin_dir to Fish PATH. Open a new shell."
      return 0
      ;;
    *) rc="$HOME/.profile" ;;
  esac
  touch "$rc"
  if ! grep -Fq "$bin_dir" "$rc"; then printf '\n# AZZATSSINS LITE AGENT\n%s\n' "$line" >> "$rc"; fi
  warn "Added $bin_dir to PATH in $rc. Open a new terminal or run: export PATH=\"$bin_dir:\$PATH\""
}

main(){
  banner
  [[ -f "$SOURCE_DIR/azzx_cli.py" ]] || die "azzx_cli.py is missing."
  [[ -f "$SOURCE_DIR/requirements.txt" ]] || die "requirements.txt is missing."
  [[ -d "$SOURCE_DIR/azzx" ]] || die "azzx/ package directory is missing (required for v10)."

  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    find_python || true
    info "Environment : $DISTRO"
    info "Package mgr : ${PKG_MANAGER:-unknown}"
    info "Python      : ${PYTHON_BIN:-not found}"
    info "Git         : $(command -v git 2>/dev/null || echo not found)"
    info "Ripgrep     : $(command -v rg 2>/dev/null || echo optional/not found)"
    info "SSH         : $(command -v ssh 2>/dev/null || echo optional/not found)"
    exit 0
  fi

  if ! find_python; then
    install_system_deps
    find_python || die "Python 3.10+ was not found after dependency installation."
  else
    info "Python found: $($PYTHON_BIN --version 2>&1)"
    if [[ "$NO_SYSTEM_DEPS" -eq 0 ]] && { ! command -v git >/dev/null 2>&1 || ! command -v rg >/dev/null 2>&1; }; then
      install_system_deps
      find_python || die "Python 3.10+ is unavailable."
    fi
  fi

  mkdir -p "$APP_DIR" "$CONFIG_DIR"
  chmod 700 "$CONFIG_DIR" 2>/dev/null || true
  cp "$SOURCE_DIR/azzx_cli.py" "$APP_DIR/azzx_cli.py"
  cp "$SOURCE_DIR/requirements.txt" "$APP_DIR/requirements.txt"
  for f in README.md README_ID.md INSTALL.md CHANGELOG.md VERSION; do
    [[ -f "$SOURCE_DIR/$f" ]] && cp "$SOURCE_DIR/$f" "$APP_DIR/$f"
  done

  # v10 modular package (toolkit, workflow, device, plugins, agent)
  if [[ -d "$SOURCE_DIR/azzx" ]]; then
    info "Installing azzx Python package..."
    rm -rf "$APP_DIR/azzx"
    cp -a "$SOURCE_DIR/azzx" "$APP_DIR/azzx"
    # drop bytecode if any
    find "$APP_DIR/azzx" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
  else
    warn "Package directory azzx/ missing — v7–v10 toolkit/mirror commands will not work."
  fi

  # optional examples for plugin demos
  if [[ -d "$SOURCE_DIR/examples" ]]; then
    rm -rf "$APP_DIR/examples"
    cp -a "$SOURCE_DIR/examples" "$APP_DIR/examples"
  fi

  info "Creating isolated Python environment..."
  rm -rf "$VENV_DIR"
  if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    if [[ "$PKG_MANAGER" == "apt" && "$NO_SYSTEM_DEPS" -eq 0 ]]; then
      sudo_run apt-get install -y python3-venv
      "$PYTHON_BIN" -m venv "$VENV_DIR" || die "Could not create Python virtual environment."
    else
      die "Could not create a venv. Install your distro's Python venv/virtualenv package and rerun."
    fi
  fi

  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
  info "Installing lightweight core dependencies..."
  "$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

  if [[ "$NO_CRYPTO" -eq 0 ]]; then
    info "Trying optional encrypted-vault support..."
    if "$VENV_DIR/bin/python" -m pip install 'cryptography>=42' >/dev/null 2>&1; then
      ok "Encrypted local API-key vault enabled."
    else
      warn "cryptography could not be installed. AZZX will use a permission-protected 0600 secret file instead."
    fi
  fi

  local launcher_dir launcher
  if [[ "$IS_TERMUX" -eq 1 ]]; then
    launcher_dir="${PREFIX:-/data/data/com.termux/files/usr}/bin"
  else
    launcher_dir="$HOME/.local/bin"
    mkdir -p "$launcher_dir"
    ensure_path "$launcher_dir"
  fi
  launcher="$launcher_dir/azzx"

  cat > "$launcher" <<LAUNCHER
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$APP_DIR/azzx_cli.py" "\$@"
LAUNCHER
  chmod +x "$launcher"
  chmod +x "$APP_DIR/azzx_cli.py" 2>/dev/null || true

  # Verify v10 package is importable from install location (catches missing azzx/)
  if ! "$VENV_DIR/bin/python" -c "import sys; sys.path.insert(0, r'$APP_DIR'); import azzx; assert azzx.__version__" 2>/dev/null; then
    die "Installed files are incomplete: package 'azzx' could not be imported from $APP_DIR. Re-extract the release zip and ensure the azzx/ folder is present."
  fi


  ok "$APP_NAME v$APP_VERSION installed."
  log ""
  log "Command : ${C_BOLD}azzx${C_RESET}"
  log "App     : $APP_DIR"
  log "Config  : $CONFIG_DIR"
  log "Launcher: $launcher"
  log ""
  if [[ "$IS_TERMUX" -eq 1 || ":$PATH:" == *":$launcher_dir:"* ]]; then
    log "Run now: ${C_CYAN}azzx${C_RESET}"
  else
    log "Open a new terminal, then run: ${C_CYAN}azzx${C_RESET}"
  fi
}

main "$@"

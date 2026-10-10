#!/usr/bin/env bash
set -Eeuo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python

echo "[1/7] Python compile"
"$PYTHON" -m py_compile "$DIR/azzx_cli.py"
echo "[2/7] CLI parser"
"$PYTHON" "$DIR/azzx_cli.py" --version
"$PYTHON" "$DIR/azzx_cli.py" --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" task --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" mcp --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" factory --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" permissions --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" install --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" app --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" app system >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" agent --roles >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" queue --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" schedule --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" recall --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" trace --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" session --help >/dev/null
"$PYTHON" "$DIR/azzx_cli.py" skills --help >/dev/null
echo "[3/7] Shell syntax + installer detection"
bash -n "$DIR/install.sh" "$DIR/uninstall.sh" "$DIR/update-local.sh"
CHECK_OUT="$($DIR/install.sh --check)"
printf '%s\n' "$CHECK_OUT" | grep -F "AZZATSSINS LITE AGENT v$(cat "$DIR/VERSION")" >/dev/null
TERMUX_OUT="$(TERMUX_VERSION=test PREFIX=/tmp/fake-com.termux "$DIR/install.sh" --check)"
printf '%s\n' "$TERMUX_OUT" | grep -F 'Environment : termux' >/dev/null
echo "[4/7] Offline unit tests"
PYTHONPATH="$DIR" "$PYTHON" -m unittest discover -s "$DIR/tests" -p 'test_*.py' -v
echo "[5/7] Mock AI integration"
# Sandboxed CI runners may export proxy variables (including bracketed IPv6
# no_proxy entries) that break httpx's localhost connections. The mock AI
# server is local, so bypass proxies for this step only.
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u ALL_PROXY -u all_proxy -u NO_PROXY -u no_proxy \
    PYTHONPATH="$DIR" "$PYTHON" "$DIR/tests/integration_mock_ai.py"
echo "[6/7] Sensitive patterns"
if grep -RIE --exclude='test_core.py' --exclude='README*' '(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,})' "$DIR"; then
  echo "Potential embedded API key detected" >&2
  exit 1
fi
echo "[7/7] Done"
echo "AZZX v10 self-test PASSED"

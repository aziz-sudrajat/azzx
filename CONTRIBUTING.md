# Contributing to AZZX

Thanks for helping improve AZZATSSINS LITE AGENT.

## Before opening a pull request

1. Keep changes compatible with Python 3.10+ and Termux where practical.
2. Never commit API keys, `.env` files, user config, or real personal data.
3. Prefer registered tools and explicit capability checks over arbitrary shell execution.
4. Add offline tests for bug fixes and new behavior.
5. Run `bash -n install.sh uninstall.sh update-local.sh selftest.sh`.
6. Run `PYTHONPATH=. python -m unittest discover -s tests -p 'test_*.py' -v`.
7. Run `PYTHONPATH=. python tests/integration_mock_ai.py`.

## Bug reports

Include AZZX version, Python version, OS/Termux environment, the exact command,
expected behavior, actual behavior, and a sanitized traceback. Remove API keys,
tokens, hostnames, and personal paths before posting logs.

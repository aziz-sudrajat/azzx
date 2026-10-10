# GitHub push guide — AZZX v10.4.0

Target: `https://github.com/aziz-sudrajat/azzx.git`
Archive: `AZZX_v10_NEXT_READY_TO_PUSH.zip` (contents verified, see §1)

> The ZIP contains no `.git/` history, no secrets, no caches. You push it
> yourself — nothing here pushes automatically.

## 1. Inspect and verify the archive

```bash
mkdir -p /tmp/azzx-review && cd /tmp/azzx-review
unzip -q ~/AZZX_v10_NEXT_READY_TO_PUSH.zip
ls                      # azzx/  azzx_cli.py  tests/  install.sh  README.md  ...
cat VERSION             # 10.4.0
# Verify integrity:
sha256sum -c SHA256SUMS.txt
# Confirm no secrets / junk:
grep -RIE --exclude='test_core.py' --exclude='README*' \
  '(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,})' . && echo "LEAK?" || echo "clean"
find . -name '__pycache__' -o -name '*.pyc' -o -name '.git' | head
```

## 2. Prepare your local clone (safe — preserves remote history)

```bash
git clone https://github.com/aziz-sudrajat/azzx.git azzx-push
cd azzx-push
git status              # should be clean
git log --oneline -5    # confirm the history you expect
git checkout -b release/v10.4.0
```

## 3. Replace the tree with the release contents

```bash
# Remove everything except .git, then unpack the release:
find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
unzip -q ~/AZZX_v10_NEXT_READY_TO_PUSH.zip
git add -A
git status --short | head -40
```

## 4. Sanity checks before committing

```bash
python3 -m py_compile azzx_cli.py
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' 2>&1 | tail -3
bash -n install.sh uninstall.sh update-local.sh selftest.sh
```

## 5. Commit and push (no force, no history rewrite)

```bash
git commit -m "Release AZZX v10.4.0: unified native agent

- Remove the separate 'azzx hermes' mode; capabilities are native now:
  azzx agent / queue / schedule / recall / trace / session / skills
- Real provider-backed multi-agent roles (planner/researcher/coder/
  reviewer/tester/security); typed provider errors, bounded retries,
  cancellation
- Memory: dedup, secret refusal, shared/private boundaries, project scope
- Tasks: cancel/interrupted/resume, approval-gated background runs
- Sessions: end/resume/stale; native trust-gated skill registry
- Security: deny-first permissions, secret redaction in traces,
  0600 agent state files
See AUDIT_REPORT.md and CHANGELOG.md."

git push -u origin release/v10.4.0
```

Then open a pull request `release/v10.4.0` → `main` on GitHub and merge it
there. This keeps `main`'s history intact and reviewable.

### If you prefer updating `main` directly (safe variant)

```bash
git checkout main
git pull --ff-only origin main     # fail if remote moved; never force
git merge --no-ff release/v10.4.0 -m "Merge release v10.4.0"
git push origin main
```

Never `push --force`, never delete remote branches.

## 6. Tag the release (optional)

```bash
git tag -a v10.4.0 -m "AZZX v10.4.0 — unified native agent"
git push origin v10.4.0
```

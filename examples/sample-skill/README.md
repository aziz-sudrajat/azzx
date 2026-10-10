# Sample skill: `shout`

Minimal example of a native AZZX skill.

- `skill.json` — validated manifest: stable id, semver version, JSON-schema
  input, `handler` as `module:function`, declared permissions, tags.
- `handler.py` — the `main(text)` entry point. Keep handlers small,
  deterministic, and free of secrets.

Lifecycle (trust-gated — third-party code never runs until you approve it):

```bash
azzx skills install examples/sample-skill   # untrusted + disabled
azzx skills find "uppercase"
azzx skills trust shout && azzx skills enable shout
azzx skills invoke shout --args '{"text":"hello world"}'
```

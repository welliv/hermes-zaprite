# Portable stub

Not an install path.

Hermes loads the native plugin from the repo root (`plugin.yaml`, `__init__.py`). This folder is a placeholder for a later Agent Plugins v1 package. `mcp.json` has no servers. Enabling it will not get you paid.

When a real stdio server exists, declare `ZAPRITE_API_KEY` as `"${ZAPRITE_API_KEY}"` and set Hermes trust to `untrusted` so every write waits for a person and fails closed in cron. Do not paste the key into the file.

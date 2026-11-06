# Verification record

What was actually run against this tree, on what, and what it returned. Re-run it yourself with the
commands below; anything not listed here was not verified.

Environment: Hermes `v0.23.0+91.ga2db0ef` on Linux, Python 3.14.9 host interpreter, plugin `0.1.0`,
tree `708cf08`.

## Local suite

```
$ pytest -q
68 passed in 0.33s

$ pytest -q   # with socket.socket.connect patched to raise
68 passed in 0.18s
```

The second run is the guarantee that the suite is fully mocked: no test reaches `api.zaprite.com`.

## Admission gate

```
$ hermes plugins validate .
✓ manifest … ✓ declared tools — matches registrations
✓ declared hooks — matches registrations
✓ built-in tool collisions — no collisions
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
✓ desktop surface — stays inside the plugin SDK surface
Validation passed.
```

## Money safety, exercised directly

| Check | Call | Result |
|---|---|---|
| Interactive write escalates | `pre_tool_call("zaprite_create_order", {...})` | `approve` |
| Cron write refused | same, `unattended=True` | `block` |
| Cron read allowed | `pre_tool_call("zaprite_get_order", ...)` | `None` |
| Skipped prompt refused before HTTP | `HANDLERS["zaprite_create_order"]({...})` with no recorded approval | `ok: False` — "needs a fresh human approval for this exact call" |

## Live API

```
$ hermes zaprite doctor
ok: true | key_mode: full | org: <redacted> | orders: 9
```

A real API order was created through `ZapriteClient` and re-fetched by `externalUniqId`
(`od_gbNcl5dYsB`, PENDING, 250 cents), and an invoice was created with a contact and invoice number
returned by the API. Payment completion was **not** exercised: that needs a payer, or a sandbox org
with the Test Payment plugin.

## CI

```
release tree 1590829  pytest (3.11)  success
release tree 1590829  pytest (3.12)  success
release tree 1590829  pytest (3.13)  success
release tree 1590829  no-network     success
```

This job found a real defect the local run could not: the docs test pins `README.md` and `setup.md`
to the catalog SHA, and a SHA bump that did not move the docs failed on all three interpreters.

## Catalog entry

```
$ python3 scripts/validate_plugin_catalog.py catalog/zaprite.yaml
OK: 1 file(s) valid
```

## Not verified

- **Sandbox organisation.** No sandbox org was created for this record, so the simulated-payment
  path (Test Payment plugin → PENDING → PAID) is untested. The `watch_order` loop was exercised
  against PENDING orders only.
- **A completed payment.** No funds were moved. `PAID`/`OVERPAID` handling is covered by mocked
  tests, not by a live settlement.
- **Platforms other than Linux.** CI runs the suite on Python 3.11–3.13 but only on Ubuntu.

## Reproduce

```bash
pip install "httpx>=0.27,<0.29" "pytest>=8.2,<10"
pytest -q
hermes plugins validate . --install-deps
ZAPRITE_API_KEY=<your key> hermes zaprite doctor
```

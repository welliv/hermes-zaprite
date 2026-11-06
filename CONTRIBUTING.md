# Contributing

Thanks for looking. This plugin talks to a payments API, so the bar for changes is higher than
"it works on my machine": a change that can move money has to prove it fails closed.

## Get set up

```bash
git clone https://github.com/welliv/zaprite-hermes
cd zaprite-hermes
pip install "httpx>=0.27,<0.29" "pytest>=8.2,<10"
pytest -q
hermes plugins validate . --install-deps
```

The test suite is fully mocked — it never calls `api.zaprite.com` and needs no API key. If a test
needs the network, that is a bug in the test.

## What a pull request must include

1. **A test that fails before the change.** Money paths (`tools.py`, `policy.py`, `service.py`)
   need a test that reproduces the defect, not just one that passes afterwards.
2. **`pytest -q` and `hermes plugins validate .` output in the description.** Both must pass.
3. **If you touched these, say so explicitly:**
   - `plugin.yaml` — tools, hooks, `requires_env`, or `config_schema`
   - `policy.py` — approval, cron, spend limit, read-only handling
   - `catalog/zaprite.yaml` — the pinned SHA and the declared capabilities
4. **A disclosure line** for anything new the plugin does: a new host it calls, a file it reads, a
   shell command, stored state. Reviewers read this list before merging.

## Rules that will get a PR declined

- Reading or writing credentials outside `requires_env` and `config_schema`.
- Auto-approving anything. `{"action": "approve"}` escalates to Hermes' human gate; it must never
  become a grant.
- Letting a write through when nobody can answer (cron, timeout, skipped prompt).
- Fetching or replacing the plugin's own files at runtime — the pinned SHA is the trust model.
- Rebinding Hermes core functions or reaching into another plugin's state.
- Unbounded dependency floors (`>=X` with no upper bound).

## Adding a tool

1. Add the schema to `zaprite_core/schemas.py`.
2. Add the name to `TOOL_NAMES`, and to `WRITE_TOOLS`/`GATED_TOOLS` in `constants.py` if it changes
   anything at Zaprite.
3. Implement the handler in `zaprite_core/tools.py` and the call in `service.py`.
4. Declare it in `plugin.yaml` under `provides_tools`.
5. Add a test in `tests/` covering the success path **and** the failure path.

`hermes plugins validate` fails if `provides_tools` and the actual registrations disagree, so step 4
is not optional.

## Release and pin

- `version` in `plugin.yaml` and `catalog/zaprite.yaml` must match the code being pinned.
- Bumping the catalog pin is a separate commit that changes `sha` and `version` together.
- Catalog entries live in `NousResearch/hermes-agent`; this repo only carries the file to copy there.

## Reporting something

Bugs and feature requests: open an issue with the template. Security issues: see
[SECURITY.md](SECURITY.md) — do not open a public issue for a credential leak.

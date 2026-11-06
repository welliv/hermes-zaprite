# Pin this into the Hermes catalog

`zaprite.yaml` is the file to add at `plugin-catalog/zaprite.yaml` in `NousResearch/hermes-agent`.

## This pin

| Field | Value |
| --- | --- |
| repo | https://github.com/welliv/hermes-zaprite |
| docs_url | https://github.com/welliv/hermes-zaprite |
| homepage | https://github.com/welliv/hermes-zaprite |
| maintainer | welliv |
| sha | `af7b7554b1fa8b25827af5ba9d242d737094a2a8` |

`sha` is `git rev-parse HEAD` of the commit that landed this tree on `main`. Hermes checks out that commit. It is not this pin commit. `version: "0.1.0"` matches `plugin.yaml` on that tree commit. Catalog install clones this GitHub repository, so the repository will be public before that install. This pin does not publish it.

## Submit

When a catalog PR is wanted, add only `plugin-catalog/zaprite.yaml` (the contents of `catalog/zaprite.yaml` on `main`) to `NousResearch/hermes-agent`. Repeat the README disclosures in the PR body: network calls to `api.zaprite.com`, checkouts customers can pay, optional receipt email, saved-profile charges, ticket fees, unsigned id-only webhooks with a mandatory re-fetch, local `plugin_db`, no browser automation, human approval (`{"action":"approve"}` escalates and does not auto-approve; `post_approval_response` records a fresh yes and a session answer does not carry), `/zaprite kill` pauses writes, cron fail-closed. Do not open that catalog PR until the repository is public and someone asks.

## Checks

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
pytest
```

`provides_tools` and `requires_env` in the catalog entry match `plugin.yaml`, which matches `register()`.

## Do not

- Ship a self-updater in the pinned tree.
- Bump the SHA without a new PR.
- Set `tier` to `verified` or `official`.
- Commit an API key.

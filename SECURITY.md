# Security

This plugin holds a credential that can create real payment orders. Treat a suspected leak as urgent.

## Report privately

Do **not** open a public issue. Email the maintainer at the address on the GitHub profile, or use
GitHub's [private vulnerability reporting](https://github.com/welliv/hermes-zaprite/security/advisories/new).

Include:

- what an attacker could do with it (read orders? create orders? charge a saved profile?)
- the version or commit you tested
- reproduction steps, and whether an API key was exposed in logs, output, or an error message

## What is in scope

- The API key leaking into tool output, logs, error text, or the local order store.
- Any path where a gated write runs without a fresh human approval.
- Any path where a write runs during an unattended run (cron, timeout, skipped prompt).
- Approval directives that could be turned into a grant.
- Reading credentials the plugin was not configured with.
- A dependency that introduces a network call other than `api.zaprite.com`.

## What is not in scope

- Zaprite's own API behaviour, or limits documented in `README.md` (unsigned webhooks, no
  connections API, no invoice email).
- A user pasting their key into a chat message.
- Test orders created with a live key during testing.

## Response

The maintainer aims to acknowledge within 72 hours. Fixes are released as a new tag plus a catalog
SHA bump; the old pin is not modified.

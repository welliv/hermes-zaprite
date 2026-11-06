# Zaprite agent setup

Complete all of the following steps yourself. Do not ask the person to run a command you can run. Do not ask them to paste an API key into the chat.

One step stays human: they create the Zaprite org, connect the rails they want (card, bank, Lightning, on-chain bitcoin, stablecoins), and create the key at https://app.zaprite.com/org/default/settings/api. Hermes prompts for `ZAPRITE_API_KEY` and stores it. You only read it through Hermes.

## Goal

- The native Zaprite plugin is installed and enabled.
- `/zaprite doctor` has been run.
- You can create an order, return `checkoutUrl`, and re-fetch until Paid.

## Hermes

From the directory that contains `plugin.yaml`:

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
hermes plugins install "$PWD" --yes-deps
hermes plugins enable zaprite
```

If this repo is already in the catalog under a reviewed pin:

```bash
hermes plugins install zaprite --yes-deps
hermes plugins enable zaprite
```

Do not use a raw MCP block in `~/.hermes/config.yaml` for this version. `portable/mcp.json` is an empty stub. The tools are the native plugin.

Tell the person to restart Hermes if this session started before the install. Then call `zaprite_doctor`, or have them type `/zaprite doctor`.

- `key_mode: full` — you can get paid. Money tools still wait for their approval.
- `key_mode: read_only` — reports only. Stop before any create.
- `key_mode: missing` — send them to the API-key URL above. Do not invent a key.

`org_slug_discovered` is false because `default` is the documented fallback, not a discovered org. Doctor and bridge use `/org/{orgId}/` once an orgId is stored. A first run or a missing key still uses `/org/default/` until then. You cannot list connections.

Logo, accent color, and display name are Settings → Profile (`deep_links.profile`, or `https://app.zaprite.com/org/default/settings/profile` before an orgId is stored). API-created invoices and checkouts inherit them. You cannot set a logo or a color. Guide: https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/. If they say "add my logo", call `zaprite_bridge_handoff` with gap `branding_profile`. After they save Profile, create an order and open `checkoutUrl` to preview. That gap name is `branding_profile`. A logo or color sentence on gap `other` resolves to the same Profile handoff.

Optional, and only if they ask for a daily check: the blueprint `zaprite-paid-digest` is read-only. It may call `zaprite_report` and `zaprite_list_overdue`. It must not create, charge, email, or mark complete.

## Other harnesses

Hermes is the install that gates a charge and fails closed in cron. Everywhere else, read `skills/zaprite/SKILL.md` and `AGENTS.md`, then call `https://api.zaprite.com/v1` with `Authorization: Bearer`. Keep the key in that harness's secret store.

On any webhook, ignore the body as proof. `GET /v1/orders/{id}`. Payloads are id-only and unsigned.

Do not call a connections, branding, checkout, payment-link, recurring-invoice, or refund route. Those routes are not in the API. `docs/api-gaps.md` lists them.

When the repository is public and the harness uses the skills CLI:

```bash
npx -y skills add <owner>/<repo> --skill zaprite --yes
```

Skip that command until the public repository exists. Replace `<owner>/<repo>` with it. Do not guess.

## Done

Print this, then stop:

```text
┌─ Zaprite agent setup ────────────────────────────┐
│  Plugin   zaprite (native Hermes)                │
│  Secret   ZAPRITE_API_KEY via Hermes             │
│  Doctor   /zaprite doctor                        │
│  Next     connect rails once, then ask to invoice│
│  Restart  if this session predates the install   │
└──────────────────────────────────────────────────┘
```

Re-read this file from the plugin repo (`prompt.md`) if you need to check it again. After the catalog pin lands, the page is `https://hermes-agent.nousresearch.com/docs/plugins/zaprite`.

# Share an invoice from chat

1. Ask for recipient name, email, service/description, and cost (currency + amount in major units; convert to smallest unit for the API).
2. `zaprite_doctor` if the key or mode is unclear (sandbox vs live = which org key).
3. `zaprite_create_contact` → `zaprite_create_invoice`.
4. Give the person `checkoutUrl`. Creating an invoice may mark it SENT; Zaprite does not reliably email it from the API. They can also send from the dashboard. There is no send-invoice email endpoint.
5. `zaprite_watch_order` until Paid → deliver work → optional `zaprite_update_order` status `COMPLETE`.

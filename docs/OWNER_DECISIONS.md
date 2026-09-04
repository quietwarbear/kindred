# Kindred — Outstanding owner decisions (pre-launch)

Everything engineering can decide is decided; these are the calls that need the
owner. Each has a recommendation so it's a yes/no, not an open question.

## 1. Pricing — verify providers (in-code pricing is already reconciled)

The old web-vs-app mismatch is fixed in this codebase: `backend/pricing.py` holds
the canonical amounts (Sapling $9.99/$89.99, Oak $19.99/$179.99, Redwood
$39.99/$359.99) and the frontend Pricing page reads them live from the API — web
and app agree.

- [ ] **Verify each Stripe Price** is active, USD, correct amount/interval
      (needs read-only Stripe access).
- [ ] **Verify all six RevenueCat/StoreKit product prices** on an authorized
      device/console.
- Reference: `docs/COMMERCIAL_READINESS_DECISIONS.md` (items 3–4).

## 2. `PLATFORM_ADMIN_EMAIL` (blocks the admin surfaces)

- [ ] Set `PLATFORM_ADMIN_EMAIL` in prod to the admin's email. Admin authority
      (pilot cohort page, digest `run-all`) is derived from it server-side; until
      it's set, those admin surfaces correctly deny everyone. **Recommendation:**
      set it as part of the deploy.

## 3. Outbox `invite_id` sign-off (from the R14 privacy review)

The first-send delivery outbox stores the raw `invite_id` (a bearer credential)
**server-side only** — never logged, never returned to any client, same trust
boundary as the events collection it already lives in. The privacy review flagged
it as the one spot the new code persists the credential in cleartext.

- [ ] **Decision:** accept as-designed (recommended — it's server-internal and
      required to map a provider delivery callback back to the invite), or ask
      for an opaque-mapping redesign (more work, matches the rotation module's
      pattern). **Recommendation:** accept as-designed; it never leaves the server.

## 4. Support identity — resolved

- [x] `support@heykindred.org` was created, verified as monitored, and centralized in the public application configuration. Store-console publication remains a separate approval-gated action.

## 5. Elder Grove tier wording & eligibility

Code treats it as custom/contact pricing (technical cap 9,999, public wording
"above 100 members").

- [ ] Confirm the sales language, nonprofit eligibility, and real capacity.

## 6. Privacy declarations & data map

- [ ] Complete the confirmations in `docs/APP_STORE_PRIVACY_DECLARATIONS.md` and
      `docs/PRIVACY_DATA_MAP.md` before submitting either store listing. Apple
      currently discloses several categories as Data Not Linked to You, while
      the engineering map identifies account, content, purchase, device, and
      usage categories that are linked to identity. Reconcile that linkage and
      the pending Google Data Safety declaration before submission.

## 7. Subscription recovery — stays paused (no action unless you choose)

Checkout returns HTTP 410; RevenueCat billing is not restored. This is a
deliberate separate workstream. **Recommendation:** leave paused for the pilot —
a free small tier gets the group in; monetize after the habit forms.

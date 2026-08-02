# Kindred — Launch runbook (deploy, enable, smoke-test)

This is the operator checklist to take the built pilot software live. It exists
because the remaining "critical path" and "enablement" work is gated on
deploy access and provider secrets that only the owner holds — every step below
is one you run, in order. Nothing here is automated; the code is ready and
disabled-by-default.

Deploy topology: **Vercel** (frontend) + **Railway** (backend), MongoDB. The app
serves from `https://www.heykindred.org`.

---

## 0. Merge order (draft PRs, currently unmerged)

Merge in this order so stacked work applies cleanly:

1. **#34** — R15 reminders + follow-up loop.
2. **#35** — pre-pilot polish (Memory Vault nav, retire orphaned page, unify AI name).
3. **#36** — R16 activation funnel (**stacked on R15**, merge after #34).
4. **#37** — R17 pilot consent & cohort (independent).

Each is draft/adversarially-reviewed. After merge, `main` carries all of the
above; deploy from `main`.

## 1. Deploy (Tier 1 goes live; everything else stays dormant)

- [ ] Deploy `main` to Railway (backend) and Vercel (frontend). Confirm both are
      **READY at the same commit**.
- [ ] On deploy, **Tier 1 activation signals go live** (organizer activation
      signal, `opened_at` on public RSVP resolve, the activation funnel + nudge,
      the pilot cohort admin page). These are safe: content-free, no sends.
- [ ] Confirm the gated features are still **off** (their env flags unset — see §3).

### Required base environment (should already be set)
`MONGO_URL`, `DB_NAME`, `APP_URL=https://www.heykindred.org`, `CORS_ORIGINS`,
`UBUNTU_SSO_SECRET`, Stripe keys (`sk_`, `whsec_` — backend only), RevenueCat.

### New for this launch
- [ ] **`PLATFORM_ADMIN_EMAIL`** — set to the admin's email. Required for the
      pilot cohort admin page **and** the digest `run-all` endpoint to work
      (admin authority is derived from this, never a stored flag).

## 2. Post-deploy containment smoke (synthetic only — no real customer data)

Run these read-only checks against production:

- [ ] `GET /api/` returns the health message.
- [ ] `GET /api/public/rsvp` with **no** Authorization header → **HTTP 401**.
- [ ] There is **no** backend `/rsvp/:token` path-token API route (header-only).
- [ ] Subscription checkout returns **HTTP 410** `subscription_checkout_migrating`
      (kill switch intact; subscription recovery stays paused).
- [ ] The web/app pricing match (both read the canonical catalog — Sapling
      $9.99/$89.99, Oak $19.99/$179.99, Redwood $39.99/$359.99).

### Disposable-Mongo verification (reproducible; run before trusting a release)
The concurrency proofs run against a **local throwaway replica set** — never a
production or cloud cluster (the tests refuse any DB not named
`kindred_disposable_*`). Proven recipe:

```bash
docker run --rm -d -p 27017:27017 --name kindred-tw mongo:7 --replSet rs0 --bind_ip_all
docker exec kindred-tw mongosh --quiet --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"127.0.0.1:27017"}]})'
# then, per campaign file, each in its OWN process (Motor event-loop isolation),
# with BOTH env vars set to the same disposable URL:
U="mongodb://127.0.0.1:27017/?replicaSet=rs0"
KINDRED_DISPOSABLE_MONGO_URL="$U" MONGO_URL="$U" DB_NAME="kindred_disposable_r14" \
  python -m pytest backend/tests/test_release14_activation_signals_disposable_db.py::test_share_signal_and_rsvp_both_persist_under_contention -q
docker rm -f kindred-tw
```

## 3. Enable the gated features (only when you're ready, each after its review)

All default **off**. Each needs its provider configured and its own review
accepted before flipping on. Enable one at a time and re-run the synthetic smoke.

### First-send invitation delivery (R14)
- [ ] Configure Resend: `RESEND_API_KEY`, `INVITATION_FROM_ADDRESS` (a verified
      sender), `INVITATION_VERIFIED_DOMAIN`.
- [ ] Set `INVITATION_FIRST_SEND_WEBHOOK_SECRET` and point a Resend webhook at
      `POST /api/provider/resend/invitation-first-send`.
- [ ] Flip `INVITATION_FIRST_SEND_ENABLED=true`.
- [ ] Smoke: an organizer "send" to a **synthetic** invite → provider accepts →
      the signed callback stamps `delivered_at`; the response carries only
      content-free counts.

### Reminders (R15)
- [ ] Same provider + webhook as first-send (the reminder callback reuses it).
- [ ] Flip `INVITATION_REMINDERS_ENABLED=true`.
- [ ] Smoke: `send-reminders` on a synthetic gathering delivers once per invite
      per day (claim-before-send dedupe); the callback stamps `reminder_delivered_at`.

### Push notifications (R14/R15)
Push is routed per platform: **Android/web → FCM**, **iOS → APNs**. The single
`PUSH_NOTIFICATIONS_ENABLED` flag gates both; each transport also stays inert
until its own credentials are present.

Android/web (FCM):
- [ ] Configure FCM: `FCM_SERVICE_ACCOUNT_JSON` (or `FCM_PROJECT_ID` +
      `FCM_CLIENT_EMAIL` + `FCM_PRIVATE_KEY`).
- [ ] Place `google-services.json` in `frontend/android/app/` **before** the
      release build (it is gitignored; without it the build silently ships with
      push disabled).

iOS (APNs, direct — no Firebase on iOS):
- [ ] In the Apple Developer portal, enable the **Push Notifications**
      capability for App ID `com.ubuntumarket.kindred` and regenerate the
      distribution provisioning profile. (`aps-environment=production` is
      already in `App.entitlements`.)
- [ ] Create an **APNs Auth Key** (.p8) under Keys; note the Key ID and your
      Team ID. Set on the backend: `APNS_AUTH_KEY` (the .p8 contents; `\n`
      line breaks are accepted), `APNS_KEY_ID`, `APNS_TEAM_ID`. Optional:
      `APNS_TOPIC` (defaults to the bundle id), `APNS_ENVIRONMENT`
      (`production` default; `sandbox` for a dev build).

Then:
- [ ] Flip `PUSH_NOTIFICATIONS_ENABLED=true`.
- [ ] Smoke on **both** platforms: a synthetic RSVP triggers a content-free push
      to the organizer's own device; a dead token is pruned; nothing
      customer-identifying is sent. iOS tokens route to APNs, Android to FCM.

### Weekly digest (already built)
- [ ] Set `DIGEST_CRON_KEY` and point a weekly external trigger at
      `POST /api/digest/cron` with header `X-Digest-Cron-Key`.
- [ ] Optionally `PUBLIC_BACKEND_URL` for unsubscribe links.

### Legacy Table recipe transfer (Stage 12B) — separate, still gated
- [ ] Follow `docs/STAGE_12B_LEGACY_TABLE_DELIVERY_BRIDGE.md` deployment order;
      keep `LEGACY_TABLE_TRANSFER_ENABLED` off until its own preflight is green.

## 4. Real pilot go-live gate (per the Release 13 checklist)

- [ ] Use the **pilot cohort admin page** to enroll the community and **record
      the organizer's explicit consent** (only after that conversation actually
      happened — see `docs/RELEASE_17_PILOT_COHORT.md`).
- [ ] Complete `docs/RELEASE_13_PRODUCTION_LAUNCH_CHECKLIST.md` (provenance,
      synthetic smoke, real-pilot decision gate, rollback conditions).
- [ ] Only then create the real event; never put real names/contacts/links in
      engineering evidence.

## 5. Rollback

- Record the prior known-good Vercel/Railway commits before launch.
- Rollback must not restore a path-token RSVP API or a stale token-bearing
  service-worker cache.
- If deployment provenance, transport, provider preflight, concurrency, or count
  reconciliation fails: stop, send nothing, restore containment.
- Suspected credential exposure: follow the invitation incident runbook; do not
  manually rotate.

# Commercial readiness review

Date: 2026-07-24
Reviewed commit: `0f0e3496786bbf5a4f3feca90c22996ebcfce1d5`
Status: local changes only; not committed, pushed, deployed, or submitted to a store

## Verified findings

1. Pricing was modeled as one pair of fields per tier, which fabricated a $0 annual value for Seedling and encouraged monthly-first assumptions. The catalog is now a plan × billing-interval matrix: Seedling has only a non-recurring free option; Sapling, Oak, and Redwood each have monthly and annual options; Elder Grove remains custom.
2. The current live public plans API and backend configuration agree on paid amounts: Sapling $9.99/month and $89.99/year; Oak $19.99/month and $179.99/year; Redwood $39.99/month and $359.99/year. The live API still uses the legacy field shape, so the frontend normalizes it during a staged rollout without inventing amounts.
3. Live RevenueCat offerings confirm monthly and annual packages for each paid plan and the configured product IDs. The public offering response does not expose localized StoreKit prices. The repository has six Stripe Price IDs, but no authorized Stripe secret was available to retrieve the remote objects. Provider amount verification is therefore explicitly pending rather than assumed.
4. “See all plans” linked to the protected `/subscription` application route, so anonymous visitors were redirected to login. There was no public pricing route.
5. “Explore the strategy deck” linked to `/strategy`, which was not a public route and fell into authentication. The deck also contains venture, naming, competitive, and roadmap content unsuitable for the consumer journey.
6. The policy named Stripe, RevenueCat, Google OAuth, and Gemini, but omitted active Google Analytics/GTM, PostHog, Resend, OpenAI/Whisper/LiteLLM paths, push infrastructure, MongoDB/media storage behavior, and cross-product SSO. It also made unverified claims about provider storage, encryption, and complete deletion.
7. Store documentation still used `kindred.ubuntumarket.com`, while the live site, canonical metadata, sitemap, app links, and email URLs use `www.heykindred.org`.
8. Support surfaces used `support@ubuntu-village.org`, while one subscription message used `hello@kindred.community`. No evidence proves a working branded `@heykindred.org` mailbox.
9. RevenueCat's `elder_grove` entitlement mapped to the non-existent internal ID `elder_grove` instead of `elder-grove`; its stored records also used `tier` without the `plan_id` and `community_id` fields consumed by the canonical subscription path.
10. The RevenueCat webhook read a secret from configuration but did not enforce it. Stripe checkout did not verify that a configured remote Price's amount/interval/metadata matched the published catalog.
11. The public-route prerender script could snapshot the wrong page when another service occupied IPv6 localhost port 3000 and when earlier route output replaced the CSR shell.
12. Native subscription cards used backend USD amounts rather than StoreKit-localized package prices and savings.
13. Paid access and webhook handling did not consistently preserve access through a cancellation/grace period or reject duplicate and out-of-order provider events.
14. Browser-captured prerender output was treated as exact React SSR markup, producing hydration mismatch errors in production.

## Implementation

- `backend/pricing.py` — canonical plan/interval matrix, exact USD charges, computed savings, Stripe and RevenueCat mappings, provider expectations, reverse resolvers, and import-time fail-closed invariants.
- `backend/dependencies.py` and `backend/subscription_lifecycle.py` — import the canonical catalog, preserve paid access through a verified cancellation/grace period, expire provider-backed access at its authoritative end date, and centralize provider event ordering.
- `backend/setup_stripe_subscriptions.py` — creates Stripe products/prices from the canonical catalog.
- `backend/routes/subscriptions.py` — fails closed when Stripe is unconfigured and verifies active flag, USD amount, interval, tier metadata, and billing-cycle metadata before checkout.
- `backend/routes/revenuecat.py` — resolves the purchased product to plan and interval, requires the matching entitlement and expiration, stores canonical billing fields, preserves cancellation/grace access, and rejects unknown, stale, duplicate, or contradictory native purchase state.
- `backend/routes/finance.py` — verifies Stripe signatures and environment, resolves each subscription Price back to a canonical plan/interval, and applies subscription events idempotently in provider timestamp order.
- `backend/server.py` — replaces the stray `heykindred.com` URL with the canonical public origin.
- `backend/tests/test_subscriptions.py` — corrects obsolete price expectations.
- `backend/tests/test_commercial_readiness_static.py` — covers every paid plan × interval mapping and rejects missing intervals, crossed entitlements, duplicated identifiers, unsupported claims, and contradictory Stripe expectations.
- `frontend/src/hooks/usePublicPlans.js` — loads public plan data from the unauthenticated API with no hard-coded price fallback.
- `frontend/src/components/PublicPlanCards.jsx` — displays both complete paid charges and calculated annual savings; Seedling is explicitly free with no recurring interval.
- `frontend/src/components/PricingPage.jsx` — adds anonymous pricing with all plans, annual options, features, and a clear separation from signed-in management.
- `frontend/src/components/LandingPage.jsx` — removes old price literals and the consumer strategy link; uses live plan data; sends anonymous “fits your circle” and “See all plans” CTAs to public pricing.
- `frontend/src/App.js` — registers `/pricing` outside the protected app and centralizes the invite origin.
- `frontend/src/lib/pricing.js` — normalizes legacy live API fields into the new matrix for a staged rollout while retaining API-sourced amounts.
- `frontend/src/lib/revenuecat.js` and `frontend/src/components/SubscriptionPage.jsx` — fail closed on missing mappings, require the selected RevenueCat package interval and entitlement, display StoreKit's localized complete charge on native, calculate native savings only from same-currency localized package amounts, and remove equivalent-monthly/approximate-savings/trial claims.
- `frontend/src/index.js` — replaces browser-captured prerender snapshots with a fresh client tree instead of incorrectly hydrating them as exact SSR markup.
- `frontend/src/config/publicIdentity.js` — centralizes canonical origin/company/current support email.
- `frontend/src/components/PrivacyPolicyPage.jsx` — replaces the incomplete policy with code-backed categories, purposes, vendors, AI paths, retention limits, deletion behavior, and controls.
- `frontend/src/components/SupportPage.jsx`, `TermsOfServicePage.jsx`, and `ShareInviteDialog.jsx` — centralize identity and remove misleading privacy/support statements.
- `frontend/src/lib/api.js` — replaces the obsolete-domain fallback with the production API host.
- `frontend/STORE_LISTINGS.md` and `SUBMISSION_CHECKLIST.md` — standardize public URLs and remove “no data harvesting.”
- `frontend/public/sitemap.xml` — publishes the public pricing URL.
- `frontend/scripts/prerender.js` — includes pricing; isolates IPv4 localhost; preserves the CSR shell for every route; blocks service-worker interference; snapshots live plan data; fails on route HTTP errors.
- `frontend/scripts/verify-commercial-readiness.js` — repeatable desktop/mobile anonymous route smoke test and screenshot capture using the live plans response.
- `docs/PRIVACY_DATA_MAP.md` — complete engineering data/vendor map with retention, deletion, controls, and confirmations.
- `docs/APP_STORE_PRIVACY_DECLARATIONS.md` — owner worksheet for Apple App Privacy and Google Play Data Safety.
- `docs/COMMERCIAL_READINESS_DECISIONS.md` — implemented decisions and owner confirmations.
- `docs/screenshots/*.png` — desktop/mobile pricing and navigation evidence.

## Provider mapping audit

| Plan | Interval | Canonical charge | Stripe Price ID (configured) | RevenueCat product (live offering) | Native entitlement |
|---|---|---:|---|---|---|
| Sapling | Monthly | $9.99/month | `price_1TCNAdAk1UyEdCJUIlI3clyU` | `com.kindred.sapling.monthly` (`$rc_monthly`) | `sapling` |
| Sapling | Annual | $89.99/year | `price_1TCMNIAk1UyEdCJUHIFvOqex` | `com.kindred.sapling.annual` (`$rc_annual`) | `sapling` |
| Oak | Monthly | $19.99/month | `price_1TCN7VAk1UyEdCJU3LdlXY14` | `com.kindred.oak.monthly` (`$rc_monthly`) | `oak` |
| Oak | Annual | $179.99/year | `price_1TCMQRAk1UyEdCJU8yS5hdLe` | `com.kindred.oak.annual` (`$rc_annual`) | `oak` |
| Redwood | Monthly | $39.99/month | `price_1TCN3XAk1UyEdCJUuhFERcuD` | `com.kindred.redwood.monthly` (`$rc_monthly`) | `redwood` |
| Redwood | Annual | $359.99/year | `price_1TCMVYAk1UyEdCJUJqhBRIFc` | `com.kindred.redwood.annual` (`$rc_annual`) | `redwood` |

“Configured” does not mean the remote Stripe object was independently verified. Authorized retrieval remains required. RevenueCat product and package associations were read from the live offering; localized store amounts were not present in that response.

RevenueCat webhook resolution uses the documented top-level `product_id`, `entitlement_ids`, and `expiration_at_ms` fields. A `PRODUCT_CHANGE` alone does not activate a new tier because it may represent a deferred change; activation waits for the accompanying effective purchase or renewal event. Cancellation retains access until the expiration event.

RevenueCat `TRANSFER` and `TEMPORARY_ENTITLEMENT_GRANT` events remain deliberately non-activating. Before external release, exercise transfer, refund/revocation, grace-period recovery, and temporary-entitlement behavior in an authorized sandbox and decide whether `TRANSFER` should trigger an immediate provider reconciliation. Provider-backed records now fail closed after their authoritative end date even if a terminal event is missed.

## Verification results

- Live `GET /api/subscriptions/plans`: HTTP 200; all six paid amounts match the canonical catalog.
- Live RevenueCat offering: all six product identifiers and `$rc_monthly`/`$rc_annual` package associations match the canonical provider matrix.
- Stripe remote object retrieval: **not run** because no authorized Stripe API secret is present. Checkout retrieves each object and rejects inactive, non-USD, wrong-amount, wrong-interval, or contradictory metadata at runtime.
- `python3 -m py_compile` on all changed backend Python modules: pass.
- `pytest backend/tests/test_commercial_readiness_static.py -q`: **13 passed**.
- `yarn test --watchAll=false src/lib/pricing.test.js`: **3 passed**.
- `yarn build`: **pass**, no compile warnings.
- Prerender: `/`, `/pricing`, `/privacy`, `/terms`, `/support` all produced substantive HTML.
- Browser smoke: keyboard-activated anonymous home → pricing link, five live plans, privacy, terms, and support at desktop/mobile widths with no console or page errors: **pass**.
- Desktop viewport: 1440×1000. Mobile viewport: 390×844.
- `git diff --check`: pass.
- Full legacy backend integration suite was not run because it requires a configured external API, creates accounts/content, and exercises checkout; running it against production would create external state. The targeted offline suite covers these changes without production writes.

## Unresolved owner / legal decisions

1. Confirm or create a branded support mailbox. The current verified identity remains `support@ubuntu-village.org`; a nonexistent address was not guessed.
2. Confirm Elder Grove capacity, eligibility, nonprofit language, and sales process.
3. Confirm remote Stripe objects and localized Apple/Google prices with authorized provider access. Product identifiers are mapped, but provider amounts cannot be certified from repository configuration alone.
4. Run authorized Stripe and RevenueCat sandbox lifecycle scenarios, including duplicate/out-of-order delivery, cancellation, renewal, billing failure and grace recovery, product change, refund/revocation, transfer, and temporary entitlement.
5. Confirm the production AI provider/model and its retention/no-training contract.
6. Confirm hosting/database region, encryption at rest, backups, logs, and deletion timeframes.
7. Inspect live GTM/PostHog settings and obtain counsel on consent, tracking, sale/share, children, retention, and deletion disclosures.
8. Decide whether to expand deletion to subscriptions, care circles, newer collections, analytics/provider records, logs, and backups.

## Store disclosure action

Use `docs/APP_STORE_PRIVACY_DECLARATIONS.md` to update Apple App Privacy and Google Play Data Safety. The major correction is to answer that Kindred **does collect data** and disclose account/contact data, user content (including photos/audio), identifiers/device tokens, purchase history, product interaction analytics, messages/files, and applicable diagnostics. Purposes, sharing/processor cautions, tracking confirmation, deletion behavior, security confirmation, and exact URLs are specified there.

## Rollback

No external rollback is required because nothing was deployed or submitted.

For code review rollback:

1. Revert the local commercial-readiness change set as one reviewed unit; do not alter the separate damaged legacy checkout.
2. If selectively reverting public pricing, revert `PricingPage`, `PublicPlanCards`, `usePublicPlans`, the `/pricing` route, and the landing/prerender/sitemap changes together so no CTA points to a missing route.
3. If selectively reverting canonical pricing, revert the backend pricing matrix, public API payload, frontend normalization/rendering, Stripe validation/resolution, RevenueCat resolution, and all pricing tests together. Do not retain a provider mapping without its corresponding interval or revert Seedling to fabricated monthly/annual values.
4. If selectively reverting identity/privacy, revert the identity config, policy/support/terms/store-doc changes, and privacy worksheets together to avoid contradictory disclosures.
5. Re-run the backend and frontend pricing regression tests, production build, prerender, and browser smoke before approving any rollback.

# Commercial readiness decisions

## Verified decisions implemented

- **Canonical pricing shape:** pricing is a plan × billing-interval matrix. Seedling has one explicit non-recurring free option and no annual option. Sapling, Oak, and Redwood each have monthly and annual recurring options. Elder Grove has no self-serve interval because its price is custom.
- **Canonical amounts:** Sapling is $9.99 billed monthly or $89.99 billed annually; Oak is $19.99 billed monthly or $179.99 billed annually; Redwood is $39.99 billed monthly or $359.99 billed annually.
- **Calculated annual savings:** Sapling saves $29.89 (24.9%), Oak saves $59.89 (25.0%), and Redwood saves $119.89 (25.0%) compared with twelve monthly charges. These figures are computed from canonical amounts, not entered as marketing claims.
- **Native localization:** native purchase cards use RevenueCat/StoreKit `priceString` for the complete charge. Native savings appear only when both localized package amounts are present in the same currency; USD web savings are never substituted.
- **Lifecycle policy:** cancellation preserves access only through the provider-authoritative period end; billing issues preserve access only through a known grace/period end; expiration/revocation removes paid access; duplicate and older provider events cannot overwrite newer state. Deferred RevenueCat product changes do not activate until an effective purchase or renewal event.
- **Evidence boundary:** the backend catalog, current live `/api/subscriptions/plans`, store documents, and repository configuration agree on the amounts. The RevenueCat live offering confirms all six iOS product/package mappings, but its public response does not expose localized StoreKit prices. The six configured Stripe Price IDs are present in backend configuration, but their remote objects could not be read without a Stripe secret. Those two provider-amount confirmations remain required before external release.
- **Canonical public domain:** `https://www.heykindred.org`. The live site, canonical/OG tags, sitemap, robots file, email defaults, iOS associated domains, and Android app links agree.
- **Strategy deck:** removed from the unauthenticated consumer journey. It contains venture/naming/roadmap material and remains available only through the existing authenticated admin route.

## Owner confirmation required

1. **Support identity:** the current policy, terms, and support page consistently use `support@ubuntu-village.org`, now centralized in frontend configuration. Confirm whether to create and migrate to a branded address such as `support@heykindred.org`; no unverified mailbox was published.
2. **Elder Grove wording and eligibility:** code treats it as custom/contact pricing with a technical cap of 9,999 and public wording “above 100 members.” Confirm sales language, nonprofit eligibility, and real capacity.
3. **Provider price equality:** with authorized read-only Stripe access, verify each configured Price is active, USD, and has the expected amount, interval, and metadata. On an App Store Connect/StoreKit-authorized device or console, confirm all six localized RevenueCat product prices. Checkout now fails closed when Stripe fields disagree, and native purchase resolution requires the expected product, package interval, and plan entitlement.
4. **Lifecycle sandbox gate:** exercise Stripe and RevenueCat cancellation, expiry, renewal, billing failure/grace recovery, product change, refund/revocation, duplicate/out-of-order, transfer, and temporary-entitlement cases. `TRANSFER` and `TEMPORARY_ENTITLEMENT_GRANT` are deliberately non-activating pending this provider-authoritative test.
5. **Provider/retention/legal decisions:** complete the confirmations in `PRIVACY_DATA_MAP.md` and `APP_STORE_PRIVACY_DECLARATIONS.md`.

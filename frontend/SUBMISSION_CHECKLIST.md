# Kindred — App Store Submission Checklist

**Release 3.1.2 review date:** September 20, 2026
**Prior Rejection:** March 23, 2026 (Apple Guideline 3.1.2(c))

---

## CODE FIX APPLIED

- [x] **SubscriptionPage.jsx** — Added auto-renewal disclosure with Apple/Google/web cancellation instructions and links to Terms of Service and Privacy Policy

---

## iOS APP STORE

### App Store Connect

1. **App Store Description**
   - [ ] Replace description with updated copy from `STORE_LISTINGS.md` (iOS section)
   - [ ] Confirm event-first product name, subtitle, description, keywords, categories, and release notes
   - [ ] Verify Privacy Policy and Terms URLs at the bottom

2. **Subscription Metadata (Subscriptions section)**
   - [ ] Sapling Monthly: $9.99/mo — Display Name + Description filled in
   - [ ] Sapling Annual: $89.99/yr — Display Name + Description filled in
   - [ ] Oak Monthly: $19.99/mo — Display Name + Description filled in
   - [ ] Oak Annual: $179.99/yr — Display Name + Description filled in
   - [ ] Redwood Monthly: $39.99/mo — Display Name + Description filled in
   - [ ] Redwood Annual: $359.99/yr — Display Name + Description filled in

3. **License Agreement (EULA)**
   - [ ] Consider uploading a custom EULA with subscription-specific terms (same pattern as Ile Ubuntu)

4. **URLs**
   - [ ] Privacy Policy: `https://www.heykindred.org/privacy` — verify loads publicly
   - [ ] Terms: `https://www.heykindred.org/terms` — verify loads publicly
   - [ ] Support: `https://www.heykindred.org/support`

5. **Build & Upload**
   - [x] Production frontend build completed and prerendered successfully
   - [x] `npx cap sync ios` completed successfully
   - [x] Version/build set to 3.1.2 (67)
   - [x] Xcode 27 generic iOS archive completed successfully after updating the RevenueCat Capacitor bridge to 13.6.0
   - [x] iPhone 17 simulator build, installation, and launch smoke test completed successfully
   - [ ] Reconnect the physical iPhone and complete a final device smoke test
   - [ ] Upload the archive through an authenticated Apple distribution session
   - [ ] Select new build in App Store Connect

6. **Submit**
   - [ ] Verify test credentials are current
   - [ ] Obtain the owner's explicit final approval at the Submit for Review action
   - [ ] Submit for Review

---

## GOOGLE PLAY

### Google Play Console

1. **Store Listing**
   - [ ] Use updated copy from `STORE_LISTINGS.md` (Google Play section)
   - [ ] Verify Google Play-specific cancellation instructions (not Apple)

2. **In-App Products / Subscriptions**
   - [ ] Sapling Monthly: $9.99/mo
   - [ ] Sapling Annual: $89.99/yr
   - [ ] Oak Monthly: $19.99/mo
   - [ ] Oak Annual: $179.99/yr
   - [ ] Redwood Monthly: $39.99/mo
   - [ ] Redwood Annual: $359.99/yr

3. **Privacy & Data Safety**
   - [ ] Privacy Policy URL set
   - [ ] Replace the incorrect “No data collected” answer using `docs/STORE_PRIVACY_DECLARATION_MATRIX.md`
   - [ ] Obtain the production and legal confirmations listed in the matrix before submitting

4. **Store creative**
   - [ ] Use the five ordered Google phone exports from `store-assets/google/phone`
   - [ ] Confirm dimensions, no alpha channel, synthetic-only source data, and sensitive-marker scan
   - [ ] Confirm no desktop framing, watermarks, reviewer/demo labels, credentials, or production data

5. **Build & Upload**
   - [ ] `cd frontend && npm install && GENERATE_SOURCEMAP=false npm run build`
   - [ ] `npx cap sync android`
   - [ ] Build signed AAB (see NATIVE_DEPLOY.md)
   - [ ] Upload to Google Play Console

6. **Submit**
   - [ ] Submit for review

---

## RELEASE 2 PUBLICATION BOUNDARY

- [ ] Do not publish Apple metadata, privacy answers, screenshots, or listing changes without separate approval.
- [ ] Do not publish Google metadata, Data Safety answers, screenshots, or listing changes without separate approval.
- [ ] Use the verified `support@heykindred.org` mailbox, but do not publish the console identity change without separate approval.
- [ ] Keep RevenueCat Billing web subscriptions enabled and verify the production
      public web key, canonical web catalog, and signed webhook end to end with
      synthetic evidence. The HTTP 410 `subscription_checkout_migrating`
      boundary applies only to the retired direct-Stripe subscription endpoint.

---

## KEY DIFFERENCE FROM MARCH 23 REJECTION

The March rejection was for Apple Guideline 3.1.2(c) — the same issue that Ile Ubuntu had. The fix applied today adds the required auto-renewal disclosure, pricing info, and Terms/Privacy links directly in the subscription purchase flow (SubscriptionPage.jsx). The privacy and terms pages were already public routes.

---

## RELEASE 3.1.2 VERIFICATION SNAPSHOT

- [x] 18 frontend suites and 119 tests passed
- [x] RevenueCat native purchase unit tests passed on the 13.6.0 bridge
- [x] Android debug assembly passed after the RevenueCat update
- [x] iOS signed archive passed for bundle `com.ubuntumarket.kindred`
- [x] Five iPhone, five iPad, and five Google phone screenshots passed the deterministic generator and manifest checks
- [x] Screenshot copy uses family event and holiday gathering language rather than presenting every event as a reunion
- [ ] Physical iPhone test is pending because the connected device was offline during verification
- [ ] App Store Connect upload, metadata save, build selection, and review submission remain pending

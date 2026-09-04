# Kindred — App Store Submission Checklist

**Release 2 review date:** July 30, 2026
**Prior Rejection:** March 23, 2026 (Apple Guideline 3.1.2(c))

---

## CODE FIX APPLIED

- [x] **SubscriptionPage.jsx** — Added auto-renewal disclosure with Apple/Google/web cancellation instructions and links to Terms of Service and Privacy Policy

---

## iOS APP STORE

### App Store Connect

1. **App Store Description**
   - [ ] Replace description with updated copy from `STORE_LISTINGS.md` (iOS section)
   - [ ] Confirm reunion-first product name, subtitle, description, keywords, categories, and release notes
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
   - [ ] `cd frontend && npm install && GENERATE_SOURCEMAP=false npm run build`
   - [ ] `npx cap sync ios`
   - [ ] Open `ios/App/App.xcworkspace` in Xcode
   - [ ] Increment version/build number
   - [ ] Archive and upload via Xcode Cloud or manual upload
   - [ ] Select new build in App Store Connect

6. **Submit**
   - [ ] Verify test credentials are current
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
- [ ] Keep web subscription checkout disabled with `subscription_checkout_migrating`.

---

## KEY DIFFERENCE FROM MARCH 23 REJECTION

The March rejection was for Apple Guideline 3.1.2(c) — the same issue that Ile Ubuntu had. The fix applied today adds the required auto-renewal disclosure, pricing info, and Terms/Privacy links directly in the subscription purchase flow (SubscriptionPage.jsx). The privacy and terms pages were already public routes.

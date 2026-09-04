# Kindred store privacy owner/legal confirmation questionnaire

**Purpose:** Capture only production and legal facts that cannot be proven from repository engineering evidence. Do not infer an answer. Attach the relevant contract, console export, policy, or named owner for every Yes/No response.

**Scope:** Current production web, Android, and iOS applications and every active processor or optional provider.

## 1. Encryption in transit

1. Is TLS enforced for every production path involving MongoDB, frontend/backend hosting, analytics, email, APNs/FCM push, RevenueCat, Stripe, support systems, file/media handling, and optional AI/transcription providers? **Yes / No / Unknown**
2. Are there any internal hops, legacy endpoints, webhooks, exports, backups, or administrator tools that transmit user data without encryption in transit? **Yes / No / Unknown**
3. Evidence owner and links/attachments:

## 2. Processor contracts and Google service-provider treatment

4. List every entity that receives Kindred user data and identify its role: processor/service provider, independent controller, joint controller, or unknown.
5. For each processor, is a current DPA or equivalent agreement in force, with use restricted to providing the contracted service? **Yes / No / Unknown**
6. For each Google Data Safety transfer proposed as “not shared,” has counsel confirmed that every service-provider exclusion condition is satisfied? **Yes / No / Unknown**
7. Does any provider use Kindred data for its own advertising, product improvement, model training, profiling, benchmarking, or another purpose outside Kindred's instructions? **Yes / No / Unknown**
8. Evidence owner and links/attachments:

## 3. Diagnostics and crash reporting

9. Do the production Android or iOS builds, Play/App Store services, hosting platforms, or embedded SDKs collect crash data, performance data, logs, device details, or other diagnostics? **Yes / No / Unknown**
10. If Yes, identify each collector, data fields, whether data is linked to an account/device, purpose, retention, region, and deletion process.
11. Evidence owner and links/attachments:

## 4. GTM, Google Analytics, and PostHog

12. Which GTM containers, GA properties, and PostHog projects are active in production web or mobile?
13. Is consent obtained before non-essential analytics initializes in every applicable jurisdiction? **Yes / No / Unknown**
14. For each service, confirm the production settings for IP collection/truncation, User ID or identity linkage, autocapture, pageviews, session replay, text/attribute masking, advertising features, Google Signals, retention, deletion, processing region, and cross-company use.
15. Can a user opt out or withdraw consent, and does that choice stop future collection? **Yes / No / Unknown**
16. Evidence owner and links/attachments:

## 5. Provider retention and deletion

17. For MongoDB/hosting backups and logs, email, push, analytics, RevenueCat, Stripe, support, file/media storage, and optional AI/transcription providers, state the normal retention period and deletion method.
18. After Kindred account deletion, which processor records, shared-family records, financial records, logs, backups, or legally required records remain, for how long, and under what policy?
19. Are provider deletion requests contractually available and operationally tested? **Yes / No / Unknown**
20. Is any submitted content retained or used to train an AI model? **Yes / No / Unknown**
21. Evidence owner and links/attachments:

## 6. Tracking, sale/share, and cross-company use

22. Is any Kindred data combined with third-party data for targeted advertising, advertising measurement, profiling, data-broker activity, or tracking across apps/websites owned by other companies under Apple's definition? **Yes / No / Unknown**
23. Is any personal information “sold” or “shared” under applicable US state privacy laws? **Yes / No / Unknown**
24. If Yes to either, identify data categories, recipients, purposes, consent/ATT flow, opt-out mechanism, and jurisdictions.
25. Evidence owner and links/attachments:

## 7. Minors, consent, lawful basis, and statutory retention

26. What minimum age applies to Kindred accounts and no-account reunion participation? Can organizers submit information about minors or invite minors? **Yes / No / Unknown**
27. What verified parental/guardian consent or organizer authority is required where children's data may be processed?
28. For each major processing purpose, what lawful basis applies by jurisdiction (contract, consent, legitimate interests, legal obligation, or other)?
29. Which consent records and withdrawal mechanisms are required for analytics, communications, optional AI, photos/audio, and invitations?
30. Which statutory or legal-hold rules require retention after deletion, and what exact data and duration do they cover?
31. Has counsel approved the store declarations and public privacy/deletion wording against these answers? **Yes / No / Pending**

## Approval record

- Product owner name/date:
- Privacy/legal reviewer name/date:
- Engineering evidence reviewer name/date:
- Unresolved answers:
- Approved for Google Data Safety drafting: **Yes / No**
- Approved for Apple App Privacy drafting: **Yes / No**
- Approved for store submission: **No — requires a separate explicit final approval**

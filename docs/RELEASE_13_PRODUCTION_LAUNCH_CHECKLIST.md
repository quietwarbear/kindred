# Release 13 — Production Launch Checklist

This checklist is intentionally separate from merge and deployment. Completing the engineering PR does not authorize a real event, invitations, provider calls, or customer communication.

## Release provenance and containment

- [ ] The approved Release 13 merge commit is recorded.
- [ ] Vercel production is READY at that exact commit.
- [ ] Railway production is successfully deployed at that exact commit.
- [ ] No non-production Railway environment was confused with production.
- [ ] `GET /api/public/rsvp` without a credential returns HTTP 401.
- [ ] No backend `/rsvp/:token` API route exists.
- [ ] Subscription checkout returns HTTP 410 with `subscription_checkout_migrating`.
- [ ] Subscription recovery remains paused.

## Synthetic smoke test

- [ ] Use only a disposable synthetic organizer, synthetic family, and synthetic holiday draft.
- [ ] Draft creation sends no notification, invitation, provider call, or analytics payload.
- [ ] Member and anonymous sessions cannot list or retrieve the draft.
- [ ] A synthetic credential embedded in a malformed draft record cannot resolve through public RSVP.
- [ ] Invitation-plan preview reports counts only and performs zero invite writes.
- [ ] Missing required checks keep **Finish setup** disabled.
- [ ] Checklist network bodies contain only an allowlisted code and boolean.
- [ ] A stale concurrent finish-setup attempt returns the sanitized conflict category.
- [ ] Valid finish setup transitions once to `ready_to_invite`.
- [ ] The synthetic invitation flow uses `/rsvp#credential` and header-only `/api/public/rsvp` transport.
- [ ] No credential enters a path, query, referrer, analytics payload, browser history, service-worker cache, log, screenshot, or report.
- [ ] Delete all disposable synthetic records using the approved test cleanup path.

## Real pilot decision gate

- [ ] The organizer has explicitly agreed to pilot participation and understands what data will be entered.
- [ ] The intended guest and member groups have been reviewed privately.
- [ ] The approved private sharing/redelivery channel is functioning.
- [ ] The organizer understands that preview and checklist actions send nothing.
- [ ] Reminder timing and recipient review are agreed before any send.
- [ ] Hidden/surprise visibility is reviewed if applicable.
- [ ] Legacy Table recipe transfer remains disabled unless its independent production preflight and synthetic smoke test are separately authorized and green.
- [ ] No real names, contacts, event content, or invitation links will be included in engineering evidence.

## Rollback and stop conditions

- [ ] The prior known-good commits and platform rollback procedures are recorded before launch.
- [ ] Rollback does not restore an unsafe path-token API or stale token-bearing service-worker cache.
- [ ] If deployment provenance, privacy isolation, transport, provider preflight, concurrency, or count reconciliation fails, stop without invitations or messages.
- [ ] If a credential is suspected exposed, follow the invitation incident runbook; do not manually rotate it.
- [ ] If checkout ceases returning the required HTTP 410 response, stop and restore containment before continuing.

## Aggregate pilot closeout

- [ ] Record only safe status categories and aggregate counts.
- [ ] Reconcile invitations prepared, privately shared, responses received, reminders intentionally sent, and failures.
- [ ] Record whether recap and recipe-continuity options were offered; do not record their content.
- [ ] Document limitations and any follow-up defects before expanding the pilot.

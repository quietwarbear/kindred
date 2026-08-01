# Release 13 — Thanksgiving Pilot Organizer Runbook

This runbook is for a small, explicitly consenting pilot. All names, addresses, contacts, meal details, and invitation links are private customer data. Do not paste them into tickets, PRs, logs, analytics, screenshots, or support chat.

## Before creating the real pilot

Complete every item in `RELEASE_13_PRODUCTION_LAUNCH_CHECKLIST.md`. Confirm the deployed Kindred commit, backend/frontend health, subscription HTTP 410 response, and that no unresolved incident or invitation-rotation operation is active.

Do not create a real event during engineering verification. Production event creation requires a separate owner decision after this release is merged, deployed, and smoke-tested with synthetic records.

## Organizer walkthrough

1. Open Gatherings and choose the holiday dinner template.
2. Enter the private draft’s essential details, start, end, timezone, RSVP deadline, location, capacity, and editable meal/help defaults.
3. Create the draft. Confirm no invitation, notification, reminder, email, provider request, or public RSVP link is created.
4. Review privacy. Check who can access the organizer draft and whether any hidden-person rule is needed.
5. In the invitation panel, select the intended family members and enter any guests locally. Use **Preview invitation plan**. Confirm only aggregate member/guest counts and note presence are summarized; no credentials are created.
6. Review the attendee-facing schedule, food/help sections, and organizer preview.
7. Mark the three required content-free confirmations: privacy review, guest-plan review, and organizer preview.
8. Confirm the readiness panel shows all required checks complete, then choose **Finish setup** once. If a conflict appears, reload and review the latest draft; do not repeatedly click or work around it.
9. Only after setup is published, prepare invitations through the normal protected invitation workflow. Share each fragment-based RSVP link through the approved private channel. Never paste links into issue trackers or reports.
10. Confirm responses through organizer aggregates. Do not export guest details for pilot reporting.
11. Use existing food/help and reminder preparation workflows. Review the recipient preview before any separately authorized send. A draft/checklist action never sends a message.
12. During the dinner, use the existing attendee hub and private gathering surfaces. Keep sensitive event analytics suppressed.
13. After the end, review the private recap and memory controls. Recipe preservation remains opt-in and subject to the Stage 12B Legacy Table delivery gate.

## Expected state transitions

| Current state | Organizer action | Expected next state | Sends or provider calls |
|---|---|---|---|
| `draft` | Complete required review and finish setup | `ready_to_invite` | none |
| `ready_to_invite` | Prepare and privately share invitations | `invitations_sent` | only the separately chosen sharing/delivery action |
| `invitations_sent` | Event start passes | `active` | none from state derivation |
| `active` | Event end passes | `completed` | none from state derivation |
| `completed` | Use existing archive control, if authorized | `archived` | none from state derivation |

## Fail-closed conditions

Stop and request engineering review if:

- the production commit is not the approved release;
- checkout does not return HTTP 410 with `subscription_checkout_migrating`;
- a private draft appears to a member/guest or resolves through public RSVP;
- the invitation preview creates a credential or network mutation;
- a checklist request contains content beyond its status code and boolean;
- the time, timezone, or RSVP deadline is rejected or appears shifted;
- finish setup reports a conflict after a reload and fresh review;
- any invitation link appears in a path, query string, analytics, log, cache, browser history, screenshot, or report;
- a provider is unavailable or its preflight fails;
- a Legacy Table destination preflight or reconciliation check is not green;
- counts fail to reconcile.

Do not bypass a failed gate, manually edit production data, create replacement credentials, or re-enable subscription checkout.

## Pilot evidence

Record only:

- approved release commit and deployment status;
- safe status categories;
- non-negative aggregate counts;
- opaque operation IDs where an existing workflow requires one;
- sanitized error codes;
- whether each launch-checklist item passed.

Never record identities, contacts, event content, invitation credentials, links, messages, provider payloads, or database identifiers.

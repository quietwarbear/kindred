# Release 11 holiday-meal closed-beta runbook

This runbook is reusable for a small holiday-meal pilot. Never copy participant names, contact details, addresses, invitation credentials, recipes, or private event text into tickets, screenshots, analytics, logs, or release reports.

## Preflight

1. Confirm the deployed backend and frontend are the owner-approved Release 11 commit. Do not use a preview or staging URL for a real pilot.
2. Confirm the organizer understands that creating the draft sends nothing and that every default is editable.
3. Confirm the organizer's timezone, including the date's daylight-saving offset, through the normal form validation.
4. Confirm support ownership, rollback authority, deletion steps, and the pilot close time.
5. Treat Legacy Table as optional. Unless its UI reports sign-in ready, use Kindred only. Recipe delivery remains unavailable until the destination contract supports idempotency and acceptance reconciliation.

## Organizer journey

1. Choose **Holiday meal** and edit the neutral arrival, meal, cleanup, dish, supply, setup, and cleanup defaults.
2. Enter the local start/end time, IANA timezone, location, and privacy selections. Create the retry-safe private organizer draft.
3. Review the draft. Confirm there are zero invitations, RSVP records, named assignments, notifications, or provider actions. Select **Finish setup** only when signed-in family may see it.
4. Prepare the first invitation through the existing private invitation flow. Never paste invitation credentials into support channels.
5. Review aggregate response gaps. Do not export or screenshot named RSVP data.
6. Let signed-in members claim/release dishes and volunteer needs through the existing concurrency-safe controls.
7. Invite members to add an optional recipe or food tradition as their own Legacy Thread. Participation is optional.
8. After the validated end time, use the recap, memory, and next-gathering flows. Publish recap content only after organizer review.

## Optional Legacy Table continuity

The recipe author may open a read-only preview. It shows only their selected title and instructions/story plus categorical destination behavior. Viewing or abandoning it changes nothing. The consent checkbox starts clear. Current live delivery is intentionally unavailable; do not work around that control or copy content manually on a participant's behalf.

## Privacy-safe feedback

Use the Support page's external feedback instruction: rating 1–5; one category from setup, invitations, responses, contributions, recipes, recap, accessibility, or other; and an optional short comment. The tester must omit names, contacts, event details, addresses, invitation data, recipes, and other family information. Kindred does not submit or analyze this text.

## Success metrics

- One retry-safe private draft, with zero automatic recipients or provider actions.
- Organizer can prepare the invitation and understand response gaps.
- Signed-in members can RSVP and claim/release contributions without oversubscription.
- Optional author-owned recipe remains available in Kindred regardless of Legacy Table status.
- Recap and next-gathering continuity work without revealing hidden or draft content.
- No credential, customer content, destination URL, provider response, or feedback text enters telemetry or release artifacts.

## Support, rollback, deletion, and closeout

- Pause new pilot activity on any confidentiality, duplication, identity, or provider ambiguity. Do not rotate or redeliver credentials without the established incident gate.
- Application rollback is an owner-approved deployment action. A rollback must not delete pilot records or publish a draft.
- The participant may delete their account through Settings. Account deletion removes pending SSO codes and owner-scoped community deletion removes obsolete Legacy Table configuration.
- At closeout, confirm invitation scope, recap publication state, optional feedback handling, account/data requests, and that no pilot data was copied into engineering systems.

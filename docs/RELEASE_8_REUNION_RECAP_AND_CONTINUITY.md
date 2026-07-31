# Release 8: private reunion recap and next-gathering continuity

Last verified: 2026-07-31

## Outcome

Release 8 gives an activated family one authenticated post-reunion source of truth: a strict recap of the completed reunion, the existing private memory capsule, and an explicit organizer-only path into a new private reunion draft. It starts from the exact Release 7 merge commit `1de192f7374d99b2e825b93eca5255df8dfde9e1` on `origin/main`.

The release adds no checkout, pricing, trial, public page, public gallery, social behavior, attachment type, AI generation, provider delivery, incident operation, or production migration. All implementation and verification use synthetic local data and fake providers.

## Product and security architecture

- Completion is computed on the server for every read. Viewing a reunion never mutates it or marks it complete.
- The recap is an allowlisted projection of the already-authorized reunion. It contains the display title/date range, published structured itinerary, the viewer's own response state, anonymous counts, published/non-withdrawn memory count, an optional published organizer message, and a categorical next-gathering state.
- Organizer message content is stored in a separate `reunion_recaps` record. It is never copied into notification text, analytics, URLs, provider calls, or application log statements.
- A member recap is available only while its state is `published`. Organizer preview uses a separate organizer-only endpoint and cannot make a draft message visible to ordinary members.
- New reunion drafts are created only after a separate mutation-free preview. The client resubmits the exact preview digest, and the server recomputes it before a transaction creates the immutable operation record and draft.
- New drafts use `publication_state="organizer_draft"`. Ordinary members receive `404`, and general event lists, digests, health, timeline, profile, family-space readiness, and steward projections exclude them.
- Invitation, RSVP, memory, activity, and completed-event history are read but never modified by recap publication or next-gathering creation.

## Canonical completion rule

1. The event must be a reunion in the caller's active community and already pass existing same-community/hidden-event authorization.
2. The reunion timezone must be a valid IANA timezone and the reunion start must parse to one unambiguous instant.
3. The candidate final boundaries are the event end, when present, plus the end of every published structured activity.
4. Every present candidate and every published activity start/end/timezone must parse unambiguously. Nonexistent spring-forward wall times, ambiguous fall-back wall times without an explicit offset, reversed activity ranges, malformed values, and published legacy rows without complete boundaries fail closed.
5. At least one valid final boundary is required. The canonical end is the latest candidate normalized to UTC.
6. `now < final_end` is `not_ready`; `now >= final_end` is `ready`. Client time is never accepted.
7. Ambiguous legacy events return `legacy_conflict` and are not migrated or changed.

No explicit completion write is necessary, so there is no reversible completion flag and no read-time completion mutation.

## Recap lifecycle and concurrency

The derived/stored lifecycle is `not_ready -> ready -> published <-> unpublished`; malformed legacy input produces `legacy_conflict`. Every stored mutation increments a revision.

- Message edit, publish, and unpublish require a same-community `host` or `organizer`, expected revision, and validated idempotency key.
- Operation and payload values are stored only as SHA-256 hashes. The bounded operation ledger lets identical concurrent/retried writes converge after a compare-and-set race.
- A stale edit cannot overwrite a newer message. Divergent reuse of an idempotency key returns a categorical `409` without reflecting private content.
- Publish notification insertion is deterministic and occurs only when a publish transition wins. Unpublish removes the recap notification so it cannot remain unread while the recap is unavailable.
- Platform-administrator flags have no authority in these routes.

## Next-gathering creation

The allowlist is deliberately narrow:

- the existing community association and authenticated organizer association;
- a newly entered, validated title/start/end/timezone;
- optionally the prior gathering format and capacity;
- selected published activity titles plus the `attendance_requested` structural flag, as unscheduled draft templates;
- selected potluck labels and volunteer-slot labels, with no assignments.

Every selected source row is referenced in the preview with a one-way opaque selection reference. All event, activity, contribution, and operation IDs in the created draft are new.

The mutation writes a unique `next_gathering_operations` record and the new event in one MongoDB transaction. An identical retry returns the same draft path. A crash after commit is recoverable from the operation record. A reused key with a different preview fails. Distinct explicit keys can intentionally create later gatherings, and concurrent divergent selections produce separate drafts rather than merged fields.

The created draft has zero invitations, invitation credentials, RSVP records, activity responses, contribution assignments, planning assignments, notifications, memories, incident markers, or provider/payment state.

## Notifications and analytics

- Publication creates only a generic in-app notification with `audience_scope="user"` and explicit same-community recipients who are not excluded from the reunion.
- The organizer message is never included in the notification. No email, SMS, push, or other delivery provider is called.
- Shared notification reads, history, unread counts, and mark-read mutations apply hidden-event filtering to every role.
- Stage 8 analytics allow only four event names: `reunion_recap_viewed`, `reunion_recap_published`, `reunion_memory_continued`, and `next_gathering_started`.
- Only bounded viewer-role, recap-state, and next-action categories survive. Names, message/title text, dates, URLs, event/community/account IDs, request references, credentials, and provider identifiers are dropped.
- `/reunion/recap/:eventId` suppresses PostHog autocapture and replay snapshots. Local synthetic QA suppresses all analytics entry points.

## Data lifecycle

- Recap message and lifecycle state remain linked internally to the completed reunion until that community is deleted. Account deletion preserves the family-facing message but irreversibly removes its author link and records only `author_tombstone=true`.
- Next-gathering operation records retain source/draft linkage for idempotency and crash recovery. Creator identity becomes a non-identifying categorical tombstone on account deletion.
- Release 7 continuity claims claimed by the deleted account are deleted. Applicant request name, relationship fingerprint, and operation hash are removed; the applicant key becomes a fresh non-identifying random tombstone. A pending request becomes `cancelled`; terminal categorical state is retained for organizer audit integrity.
- Sole-owner community deletion now includes `reunion_recaps`, `next_gathering_operations`, `guest_family_claims`, and `family_access_requests`.
- Recap text is not added to existing broad timeline exports. The published recap is reconstructed only through the authenticated recap route; organizer audit hashes and linkages are not exported.
- No vendor-side deletion is promised or invoked.

## Finding-to-test matrix

| Risk / finding | Verification |
|---|---|
| Client time or invalid DST marks completion | Unit boundaries before/at/after final end; valid timezone; nonexistent/ambiguous/malformed/reversed cases |
| Organizer preview leaks unpublished text | Member projection omits message; member route remains `404` until published |
| Named/private attendee data appears in recap | Strict serialized-marker tests and member browser campaign |
| Stale/concurrent writes overwrite a message | Real MongoDB same-key race, divergent payload conflict, revision guards |
| Publish retry duplicates notifications | Deterministic notification and publish/unpublish/retry real-DB assertions |
| Hidden/excluded user receives or counts notification | Hidden member route and notification-query assertions |
| Retry creates duplicate draft | Real MongoDB concurrent identical creation and unique operation/event checks |
| Divergent creation fields combine | Concurrent distinct operations produce isolated detailed/empty drafts |
| Old person-specific or credential fields copy | Exact created-document denylist and zero-state assertions |
| Organizer draft leaks through another surface | `get_event_for_user`, common list/filter, static, and regression coverage |
| Release 7 deletion gap persists | Synthetic account deletion checks claims, request tombstone, recap author, operation creator, community integrity |
| Checkout or invitation safeguards regress | Existing HTTP 410, invitation transport/redelivery, service-worker, and Releases 3-7 campaigns |

## Verification evidence

- Stage 8 focused backend projection/policy suite: `51 passed` with the relevant attendee, capsule, guest-access, and checkout regressions included.
- Disposable local MongoDB replica-set Stage 8 campaign: `1 passed`; it covers recap concurrency, publication/unpublication retry, hidden notification isolation, exact carry-forward, identical and divergent creation races, immutable source history, draft confidentiality, and account deletion.
- Full relevant Releases 2-8 backend regression suite: `251 passed, 1 skipped`; the skip is the environment-gated disposable campaign that was run separately against the local replica set above.
- Frontend unit tests: `32 passed`.
- Optimized frontend build and public-route prerender: passed.
- Built-browser Stage 8 desktop/mobile campaign: passed; it verifies organizer edit/publish, member projection, body-only recap-message transport, explicit preview/create, no query-string Stage 8 API transport, and no external requests.
- Releases 3-7 built-browser continuity campaigns: passed, including organizer, attendee, memory-capsule, activation, and guest-family-access flows.
- Android: Capacitor sync passed and `assembleDebug` produced `app-debug.apk` using the locally configured Android SDK; no artifact is staged or published.
- iOS: Capacitor sync passed and an unsigned generic `iphoneos` Debug build completed with `CODE_SIGNING_ALLOWED=NO` and `CODE_SIGNING_REQUIRED=NO`. Existing project warnings remain for an unassigned app-icon child, the CocoaPods embed phase without outputs, and absent AppIntents metadata.
- OpenAPI: all `7` Stage 8 paths are present among `172` total paths.
- Python compilation, fatal Flake8 checks, analytics/provider/logging scans, generated-artifact review, credential and sensitive-marker scans, and `git diff --check`: passed.
- Evidence images are in `docs/screenshots/release-8/`.

## Known limitations and deferred work

- Completion remains fail-closed for legacy agenda rows without valid structured end boundaries. This release does not migrate them.
- Recap messages are plain text with a 2,000-character limit. There are no attachments, reactions, comments, AI rewriting, moderation providers, public sharing, or provider delivery.
- Recap publication is in-app only. Members who do not open Kindred receive no email, SMS, or push alert.
- Carried itinerary templates are intentionally unscheduled draft rows. Organizers must set their new times/locations in the existing planning workflow before publication.
- General account deletion still has older documented gaps outside the Stage 8 and Release 7 collections, including some vendor-side, subscription, care-circle, and authored-community records.
- Live native OAuth, production data, production deployment, store configuration, incident redelivery, and subscription recovery are intentionally outside this release.

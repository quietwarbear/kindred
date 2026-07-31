# Release 8 route, carry-forward, notification, and retention matrix

Last verified: 2026-07-31

## Route and mutation inventory

| Route | Authorization | Mutation | Safe result |
|---|---|---|---|
| `GET /api/events/{event}/recap` | Authenticated, same-community, visible reunion; published recap | None | Member recap projection |
| `GET /api/events/{event}/recap/organizer` | Same-community host/organizer | None | Organizer preview, completion category, opaque structural catalog |
| `PUT /api/events/{event}/recap/message` | Host/organizer, ready completion, revision, idempotency key | Recap text/revision/hashed operation only | Updated organizer projection |
| `POST /api/events/{event}/recap/publish` | Host/organizer, ready completion, revision, idempotency key | Recap state/revision; generic recipient-scoped notification | Published organizer projection |
| `POST /api/events/{event}/recap/unpublish` | Host/organizer, ready completion, revision, idempotency key | Recap state/revision; removes recap notifications | Unpublished organizer projection |
| `POST /api/events/{event}/next-gathering/preview` | Host/organizer, ready completion | None | Exact proposal and digest; no new draft |
| `POST /api/events/{event}/next-gathering` | Host/organizer, matching preview digest, idempotency key | Transactionally creates immutable operation and one private event draft | Categorical result and existing planner path |

All routes return `401` anonymously. Cross-community and hidden-event lookups fail with `404`. Ordinary-member mutation attempts fail at the canonical community role boundary.

## Carry-forward allowlist and denylist

| Category | Allowed | Never carried |
|---|---|---|
| Association | Existing community; authenticated organizer | Hidden-user lists, family-access decisions, other membership state |
| New gathering basics | Organizer-entered title/start/end/timezone | Old event ID, dates copied silently, old activity IDs |
| Planning configuration | Optional format and capacity | Travel, lodging, budgets, payments, private notes, checklist completion |
| Itinerary | Selected published activity title and attendance-requested flag; new unscheduled draft ID | Venue details, response/deadline state, participant names, old ID, revision history |
| Contributions | Selected potluck/volunteer category label; new ID; empty assignment | Assigned person IDs/names, volunteer history, contribution/payment amounts |
| Invitation/response | Nothing | Records, credentials, links, delivery state, RSVP/activity responses |
| Memory/communication | Nothing | Memories, drafts, withdrawn content, messages, notifications, analytics |
| Incident/provider | Nothing | Redelivery markers, operation IDs, provider IDs, delivery reports |

## Notification and analytics

| Signal | Audience / allowed properties | Excluded |
|---|---|---|
| `reunion-recap-published` in-app notification | Explicit eligible user IDs; generic title/description | Organizer message, names, email, provider delivery, hidden users |
| `reunion_recap_viewed` | Viewer role, recap state | IDs, title/message, URL, dates |
| `reunion_recap_published` | Organizer role, published state | Message, recipients, operation/reference values |
| `reunion_memory_continued` | Viewer role, recap state, `memory_capsule` category | Memory text/ID/count detail beyond server projection |
| `next_gathering_started` | Organizer role, recap state, `continue_planning` category | Draft/source IDs, title, dates, selections, URL |

## Retention, deletion, and export

| Record | Normal retention | Account deletion | Sole-owner community deletion | Export |
|---|---|---|---|---|
| `reunion_recaps` | Linked to completed reunion; no TTL | Message retained as family content; author links removed; categorical tombstone retained | Deleted | Not added to broad timeline export; authenticated projection only |
| `next_gathering_operations` | Retained for retry/crash recovery and source/draft lineage | Creator link removed; categorical tombstone retained | Deleted | Not exposed |
| Created organizer draft | Existing event lifecycle | Existing authored-event behavior; operation lineage remains non-identifying | Deleted with events | Excluded from ordinary exports/lists while private draft |
| Release 7 guest continuity claim | 24-hour application expiry; no TTL deletion | Claimed applicant record deleted | Deleted | Not exposed |
| Release 7 access request | Terminal categorical audit retained; pending lazy expiry | Pending becomes cancelled; applicant/name/relationship/operation data irreversibly anonymized | Deleted | Applicant/organizer safe projections only |

This release does not invoke or promise deletion from Apple, Google, RevenueCat, PostHog, Vercel, Railway, Resend, or any other provider.

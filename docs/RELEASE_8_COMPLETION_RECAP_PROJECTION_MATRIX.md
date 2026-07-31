# Release 8 completion and recap projection matrix

Last verified: 2026-07-31

## Completion boundary

| Input / boundary | Canonical state | Mutation | Consumer behavior |
|---|---|---|---|
| Valid timezone and `now < latest valid end` | `not_ready` | None | Organizer sees categorical status; ordinary recap remains unavailable |
| Valid timezone and `now == latest valid end` | `ready` | None | Organizer may edit/publish; member waits for publication |
| Valid timezone and `now > latest valid end` | `ready` | None | Same as exact boundary |
| Invalid timezone or event start | `legacy_conflict` | None | No migration; organizer receives safe conflict |
| Nonexistent/ambiguous local boundary without offset | `legacy_conflict` | None | Fail closed |
| Published activity missing/reversing start or end | `legacy_conflict` | None | Fail closed even if another end is valid |
| No event end and no published valid activity end | `legacy_conflict` | None | Legacy event remains unchanged |
| Hidden or cross-community reunion | `404` | None | Existence remains concealed |

## Lifecycle transitions

| Current | Edit message | Publish | Unpublish | Ordinary member read |
|---|---|---|---|---|
| `not_ready` | Conflict | Conflict | Conflict | `404` |
| `ready` | CAS edit, remains `ready` | `published` | No-op/current safe state | `404` |
| `published` | CAS edit, remains `published` | Idempotent no-op/retry | `unpublished` | Safe recap |
| `unpublished` | CAS edit, remains `unpublished` | `published` | Idempotent no-op/retry | `404` |
| `legacy_conflict` | Conflict | Conflict | Conflict | `404` |

## Role and visibility

| Actor | Completion/status | Recap content | Message mutation | Publish/unpublish | Next gathering |
|---|---|---|---|---|---|
| Anonymous | `401` | None | `401` | `401` | `401` |
| Cross-community account | `404` | None | `404` | `404` | `404` |
| Hidden/excluded same-community account | `404` | None/notification excluded | `404` | `404` | `404` |
| Ordinary member | Published recap only | Allowlisted member projection | `403` | `403` | `403` |
| Host/organizer | Safe preview and completion category | Allowlisted projection plus unpublished message/catalog | Revisioned edit | Revisioned transition | Preview and explicit transactional creation |
| Member with platform-admin flag | Ordinary-member boundary | Published member projection only | `403` | `403` | `403` |

## Recap projection

| Field category | Member | Organizer preview | Explicitly excluded |
|---|---|---|---|
| Reunion | Display title, date range, timezone | Same | Event/community/database IDs, hidden list, private planning fields |
| Itinerary | Published structured title/time/timezone, ordinal position, own categorical response, anonymous counts | Same | Activity IDs, draft/archived rows, venue/private notes, named rosters |
| Participation | Own overall RSVP and guest count; aggregate categories | Same | Other individual responses, names, emails, invitation rows/credentials |
| Contributions | Aggregate available/claimed counts | Same plus separate safe carry-forward catalog | Assignments, volunteer names, budgets, travel/lodging/payment data |
| Memories | Count of published/non-withdrawn records and existing capsule availability | Same | Draft/withdrawn content, memory IDs, notes/comments/attachments |
| Message | Only while recap is published | Current draft/published text | Author/database IDs, operation hashes, analytics/log/provider copies |
| Continuity | `not_started` or `draft_started` | Same plus selected structural catalog | New draft ID before creation, family-access state, incident/redelivery state |

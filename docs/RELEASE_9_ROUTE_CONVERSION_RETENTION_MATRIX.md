# Release 9 route, conversion, notification, and retention matrix

## Route inventory

| Route | Role | Mutation |
|---|---|---|
| `POST /api/gathering-proposals` | Active member | Idempotent private submission |
| `GET /api/gathering-proposals` | Active member | None |
| `GET /api/gathering-proposals/{reference}` | Active member | None |
| `POST /api/gathering-proposals/{reference}/withdraw` | Owning member | Terminal CAS withdrawal |
| `PUT /api/gathering-proposals/{reference}/interest` | Active member | Transactional own response |
| `GET /api/gathering-proposals/organizer/review` | Host/organizer | None |
| `POST .../{reference}/publish` | Host/organizer | CAS publication |
| `POST .../{reference}/decline` | Host/organizer | CAS terminal decline |
| `POST .../{reference}/close` | Host/organizer | CAS close/expiry |
| `POST .../{reference}/conversion-preview` | Host/organizer | None |
| `POST .../{reference}/convert` | Host/organizer | One transactional draft |

## Conversion

Allowed: current community, explicitly selected active organizer, explicitly entered bounded title/location, valid start/end/IANA timezone, bounded format, and capacity 1–10,000.

Denied: proposer/response identity, organizer note, broad date suggestion, invitations, credentials, delivery, RSVP/activity responses, contributions, assignments, memories, recap, comment/chat, travel/budget/payment, hidden list, notification, family-access record, analytics, incident/provider values, proposal reference, operation key, and old event/activity/database IDs.

## Notification and retention

| Action | Audience | Displayed content | Cleanup |
|---|---|---|---|
| Submit | Explicit organizers | Generic review category | Organizer audit entry |
| Publish | Eligible members | Generic pulse category | Remove on terminal state |
| Decline | Proposer | Generic status category | Own status remains |
| Convert | Proposer | Generic planning category | Own status remains |

| Data | Account deletion | Sole-owner deletion | Export |
|---|---|---|---|
| Proposal content/proposer | Clear content and identity; tombstone | Delete | Not included in timeline export |
| Interest response | Delete member response | Delete | Not included in timeline export |
| Conversion linkage/hash | Tombstone actor links | Delete | Excluded |
| Created private draft | Preserve without proposer identity | Delete with events | Existing event rules |

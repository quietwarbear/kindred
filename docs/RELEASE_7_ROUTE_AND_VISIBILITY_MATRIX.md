# Release 7 route and visibility matrix

Last verified: 2026-07-31

| Surface | Authorization | Safe output / action | Explicitly excluded |
|---|---|---|---|
| `GET /api/public/rsvp` | Invitation bearer header | Existing minimal reunion projection plus categorical `family_access_available` | Claim, contact data, guest list, member/profile data, pending requests |
| `POST /api/public/rsvp` | Invitation bearer header | Existing RSVP write and safe confirmation | Registration requirement, membership write, continuity claim |
| `POST /api/public/family-access-claim` | Active responded guest invitation bearer header | Short-lived opaque claim and categorical expiry seconds | Email authority, account lookup, membership, URL credential, community/event IDs |
| `POST /api/auth/guest-account` | Public account creation | Authenticated account with no community | Community bootstrap, member grant, email-invite acceptance |
| Apple / Google session with family-access intent | Verified provider identity | Existing or new authenticated account | New-account autojoin by matching pending email invite |
| `POST /api/family-access/requests` | Account session plus continuity header | Own safe state/revision/next actions | Other requests, raw IDs, email/profile, invitation/claim, automatic membership while pending |
| `GET /api/family-access/status` | Account session | Only the caller’s state; approved family-space display name | Request reference, organizer identity, other applicants, internal IDs |
| `POST /api/family-access/cancel` | Applicant session, pending state, revision, idempotency key | Own cancelled state | Decision after approval/decline/expiry/conflict; other applicant mutation |
| `GET /api/family-access/organizer/requests` | Same-community host or organizer | Opaque action reference, applicant display name, state, revision, requested timestamp | Email, phone, profile, credential, relationship fingerprint, account/event/community IDs |
| `POST /api/family-access/organizer/decision` | Same-community host or organizer, revision, idempotency key | Transactional approve/decline and safe result | Platform-admin bypass, ordinary-member decision, cross-community merge, URL action credential |
| `/family/join` | Authenticated applicant | Own pending/approved/declined/cancelled/expired/conflict UI | Request lists, organizer tools, replay/autocapture, claim after submission |
| Organizer command-center request card | Host or organizer | Named request and approve/decline controls | Ordinary member access, email/profile/contact details, internal database identifiers |

## Notification visibility

| Event type | Audience | Recipients | Ordinary member | Applicant |
|---|---|---|---|---|
| `family-access-request` | `organizer` | Current host/organizer IDs | Hidden by audience and sensitive-event filters | Not available |
| `family-access-status` | `user` | Applicant user ID | Hidden by recipient filter | Visible only after the account belongs to the relevant family; own status endpoint remains authoritative before membership |

## State transition matrix

| Current | Applicant cancel | Organizer approve | Organizer decline | Expiry / integrity failure |
|---|---|---|---|---|
| `pending` | `cancelled` | `approved` or `conflict` if integrity fails | `declined` | `expired` or `conflict` |
| `approved` | No change | Identical retry only | No change | No change |
| `declined` | No change | No change | Identical retry only | No change |
| `cancelled` | Identical retry only | No change | No change | No change |
| `expired` | No change | No change | No change | No change |
| `conflict` | No change | No change | No change | No change |

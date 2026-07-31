# Release 4 attendee projection matrix

Release 4 separates three reunion views by construction. The authenticated
attendee hub is not a filtered organizer report; it is a dedicated projection
assembled from an already authorized reunion.

| Field or capability | No-account RSVP guest | Authenticated attendee | Organizer command center |
| --- | --- | --- | --- |
| Gathering title, time, published location | Yes, for the invitation credential | Yes, for a visible reunion in the member's community | Yes |
| Published itinerary | Yes | Yes | Yes |
| Draft/private itinerary activities | No | No | Yes |
| Own overall and activity responses | Yes | Yes | Organizer reconciliation only |
| Attendance totals | Privacy-safe aggregates | Privacy-safe aggregates | Aggregate reconciliation |
| Other attendee names, emails, IDs, or responses | No | No | Separate authorized planning surfaces only |
| Own contribution commitments | No | Yes | Yes |
| Open contribution capacity | No | Yes | Yes |
| Names of other contributors | No | No | Planning surface only |
| Invitation ledger, codes, links, delivery state | No | No | Separate authorized invitation surfaces |
| Planning team, response gaps, deadlines, budget, travel gaps | No | No | Yes |
| Deterministic attendee next action | No | Exactly one | No |
| Save reunion memory prompt | No | Yes, private community memory | No |
| AI/provider call from memory prompt | No | No | No |

## Attendee hub projection contract

Allowed top-level objects are `gathering`, `rsvp`, `itinerary`,
`contributions`, `memory_prompt`, and `next_action`.

Explicitly excluded:

- invitation credentials and invitation-delivery metadata;
- organizer notes, planning roles, budgets, travel plans, and reminder state;
- draft/private activities;
- other attendees' identities, individual responses, and contribution names;
- AI summaries, tags, provider payloads, and external publication state.

The shared authenticated event serializer is also hardened for ordinary members:
it removes planning/invitation/internal fields, draft activities, named
commitments, and other respondents' rows while retaining the member's own
canonical response and privacy-safe aggregates.

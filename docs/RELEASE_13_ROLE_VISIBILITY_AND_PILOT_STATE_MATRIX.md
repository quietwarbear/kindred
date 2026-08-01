# Release 13 — Role, Visibility, and Pilot-State Matrix

## Surface visibility

| Surface | Organizer/host | Member | Invitation holder | Anonymous without credential |
|---|---:|---:|---:|---:|
| Holiday organizer draft list/detail | yes | no | no | no |
| Pilot readiness/checklist | yes | no | no | no |
| Internal setup revision | server control only | no | no | no |
| Aggregate invitation-plan preview | local organizer view | no | no | no |
| Create invitation credentials while draft | blocked | blocked | blocked | blocked |
| Published event list/detail | yes | if existing visibility policy permits | invitation projection only | no |
| Public RSVP | normal organizer view elsewhere | normal member view elsewhere | header credential required | HTTP 401 |
| Named RSVP roster | organizer-only existing surface | no | own invitation projection only | no |
| Aggregate RSVP summary | yes | existing bounded member projection | invitation-specific response | no |
| Food/help coordination | existing organizer controls | existing bounded participant controls | invitation projection only where already supported | no |
| Reminder preparation | existing authorized organizer workflow | no | no | no |
| Recap/memory/recipe preview | existing role and consent rules | existing role and consent rules | no account expansion | no |

## Organizer checklist fields

| Code | Derived or explicit | Required for finish setup | Contains customer content |
|---|---|---:|---:|
| `essential_details` | derived | yes | no; boolean status only |
| `schedule_and_timezone` | derived | yes | no; boolean status only |
| `rsvp_window` | derived | yes | no; boolean status only |
| `privacy_reviewed` | explicit | yes | no |
| `guest_plan_reviewed` | explicit | yes | no |
| `organizer_previewed` | explicit | yes | no |
| `food_coordination` | derived | no | no; presence only |
| `reminder_plan_reviewed` | explicit | no | no |
| `invitations_shared` | explicit plus delivery evidence | no | no; requires at least one active invite |

## State derivation

| State | Durable/derived condition | Allowed next organizer action |
|---|---|---|
| `draft` | `publication_state=organizer_draft` | edit, preview aggregate plan, review checklist, finish setup when ready |
| `ready_to_invite` | published, before start, no sharing evidence | prepare invitations through protected workflow |
| `invitations_sent` | active invite plus explicit or durable sharing/delivery evidence | review aggregate response gaps and food/help readiness |
| `active` | current time at/after start and before end | use existing participant coordination surfaces |
| `completed` | current time at/after end | review recap, memory, and opt-in recipe continuity |
| `archived` | archive marker present | read-only historical review under existing privacy rules |

State derivation never sends messages, calls providers, creates credentials, mutates RSVP state, changes subscription state, or enables Legacy Table delivery.

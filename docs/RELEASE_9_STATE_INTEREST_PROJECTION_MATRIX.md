# Release 9 state, role, and interest projection matrix

| State | Proposer | Other eligible member | Host/organizer | Mutation |
|---|---|---|---|---|
| `submitted` | Own fields/status | Hidden | Review, proposer name, private note | Withdraw, publish, decline |
| `published` | Pulse, own response, totals | Pulse, own response, totals | Review and anonymous totals | Respond/update, decline, close, convert |
| `declined` | Own status | Hidden | Audit category | None |
| `withdrawn` | Own status | Hidden | Audit category | None |
| `converted` | Own status | Hidden | Audit category | None |
| `expired` | Own status | Hidden | Audit category | None |
| `conflict` | Safe category | Hidden | Safe category | None |

## Role and visibility

| Context | Member surface | Organizer review/mutations | Interest |
|---|---|---|---|
| Anonymous | `401` | `401` | `401` |
| Active same-family member | Published plus own | `403` | Published only |
| Active host/organizer | Published plus own | Allowed | Published only |
| Platform-admin flag with member role | Member boundary | `403` | Member boundary |
| Cross-community | No existence disclosure | No existence disclosure | No existence disclosure |
| Provisional/inactive/legacy family | `404` | `404` | `404` |
| Suspended/removed/deleted account | `404` | `404` | `404` |

## Projection and reconciliation

| Data | Member | Organizer | Stored only |
|---|---|---|---|
| Title/type/date window/location | Published or own | Yes | Yes |
| Organizer note | Own proposal only | Yes | Yes |
| Proposer name | Never | Current family member only | Until deletion |
| Moderation reason | Never | Categorical | Yes |
| Own interest/revision | Yes | Only own | Yes |
| Anonymous totals | Published | Yes | Computed |
| Other response identity/value/revision/time | Never | Never | Yes |
| Operation hashes/conversion linkage/database IDs | Never | Never | Yes |

Eligible current active same-family response owners are counted. Deleted, suspended, removed, cross-community, and unknown-category responses are excluded. The total always equals the three category counts.

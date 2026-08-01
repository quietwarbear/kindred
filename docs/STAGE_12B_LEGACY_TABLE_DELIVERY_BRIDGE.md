# Stage 12B — Kindred recipe delivery grants

Status: draft, unmerged, undeployed. The bridge is disabled unless every server-side production gate is explicitly configured. Verification used synthetic records, fake destinations, local built applications, and disposable databases only.

## Provenance and readiness

| Surface | Commit | Evidence | Authority |
| --- | --- | --- | --- |
| Kindred `main` and production | `f1c52bad3bbb23985743162f43279f0fbbdfa332` | GitHub Vercel deployment `5701024855` and Railway deployment `5701021939` report success | authoritative |
| Legacy Table PR 41 merge and `main` | `2cb49ea61c1de95ea336f4e6e9f6ce0c7c5d474e` | PR 41 merge metadata and current `main` | authoritative |
| Legacy Table production | `2cb49ea61c1de95ea336f4e6e9f6ce0c7c5d474e` | GitHub Vercel deployment `5701273770` and Railway deployment `5701271131` report success | authoritative |
| Old Legacy Table split repositories | old March 2026 commits | deployments `4111888366` and `4111888367` are inactive `new_root` deployments | non-authoritative |

Authenticated Railway variable and database-index metadata were not available through this task connection. `RECIPE_IMPORT_HASH_KEY`, transaction topology, and production import-index readiness therefore remain unverified activation blockers. No value, database document, customer record, or production log was accessed.

## End-to-end trust boundary

```mermaid
sequenceDiagram
  participant K as Kindred browser
  participant KA as Kindred API
  participant LA as Legacy Table API
  participant L as Legacy Table browser document
  participant DB as Legacy Table transaction
  K->>KA: Author preview and explicit consent
  KA->>KA: Persist one author/source/revision operation
  KA->>LA: Mint single-use SSO code server-to-server
  KA-->>K: /sso?code=...#transfer=...
  K->>L: Initial navigation
  L->>L: Pre-React capture; history.replaceState('/sso')
  L->>LA: Redeem SSO code
  LA-->>L: Legacy Table session
  L->>KA: POST payload with X-Kindred-Transfer; no cookies
  KA-->>L: Exact immutable Stage 12A payload
  L->>L: Explicit existing/create cookbook choice
  L->>LA: Reconcile original operation, then POST if absent
  LA->>DB: Transactional recipe, receipt, and operation
  DB-->>L: Opaque receipt and safe category
  L->>KA: Header-only acknowledgement
  KA->>KA: Transactional monotonic completion
```

Kindred never receives a Legacy Table session or destination user/family identifier. Legacy Table never accepts a destination identity from Kindred; its own Bearer session is the only ownership authority.

## Durable bindings and state

One unique database row binds the keyed author binding and keyed source-subject binding to one random operation ID, one random opaque source reference, the immutable revision digest, `kindred_recipe_import_v1`, audience `legacy_table`, purpose `recipe_import`, and exact origin `https://legacytable.app`. The raw transfer credential is returned once; only its SHA-256 digest is stored. New grants replace the digest while preserving the operation.

| Current state | Allowed transition | Guard |
| --- | --- | --- |
| `previewed` | `consented` | explicit checkbox remains unchecked by default |
| none | `consented` | unique author/source transaction |
| `consented` | `grant_ready` | complete config, author ownership, index readiness, SSO acceptance, revision CAS |
| `grant_ready` | `payload_retrieved` | valid header grant, exact origin/audience/purpose/expiry |
| `payload_retrieved` | same state with a replacement grant | stable operation; no backwards transition |
| `payload_retrieved` / `destination_pending` | `completed` | destination accepted/already accepted, same revision, opaque receipt, transaction |
| non-completed | `conflict` | changed source, divergent receipt/revision, destination conflict/deletion |
| non-completed | `revoked` | explicit browser abandonment |
| active grant | expired grant category | digest removed; operation remains recoverable with its original ID |
| `completed` | `completed` only | identical receipt retry; divergent receipt fails closed |

## Credential and transport matrix

| Value | Initial transport | Later transport | Storage |
| --- | --- | --- | --- |
| Legacy SSO code | unavoidable `/sso?code=...` query | SSO redemption body only | digest-only, short-lived, single-use |
| Kindred transfer credential | URL fragment only | `X-Kindred-Transfer` only | digest-only in Kindred; transient browser memory |
| Legacy Table session | Legacy SSO response | `Authorization: Bearer` to Legacy Table only | existing Legacy Table session storage |
| Recipe payload | none in navigation | Kindred response and Legacy Table POST body | normal source/destination recipe records only |
| Operation ID | API body; Legacy reconciliation path | bodies and safe reports | both operation records |

Payload, acknowledgement, and revocation responses are `no-store` and `no-referrer`. The browser uses `credentials: omit`, rejects redirects, and never sends the Legacy session to Kindred.

## Authorization and ownership

| Actor | Preview | Create/resume grant | Retrieve | Import | Acknowledge |
| --- | --- | --- | --- | --- | --- |
| exact Kindred recipe author | yes | yes with explicit consent | only through grant | only as authenticated Legacy user | through same grant |
| Kindred organizer who is not author | no | no | no | no special authority | no |
| another community/account | indistinguishable not found | no | no | destination owner isolation | no |
| anonymous caller | no | no | valid purpose-bound grant only | no | valid grant only |
| Legacy administrator/keeper | no ownership bypass | no | no | normal authenticated family rules only | no |

Hidden, deleted, withdrawn, non-recipe, missing, changed-revision, wrong-origin, wrong-audience, malformed, expired, revoked, and unknown cases fail closed.

## Failure, retry, and reconciliation

| Failure | Safe behavior |
| --- | --- |
| configuration, URL, key, index, or transaction preflight | no operation, grant, provider call, or recipe mutation |
| crash after operation creation | original operation recovered by keyed author/source binding |
| concurrent start | one operation and one CAS grant winner; losing navigation fails closed |
| browser crash after grant | new grant reuses the original operation ID |
| timeout before destination acceptance | reconcile original ID; POST identical payload only when absent |
| timeout after acceptance / lost response | reconciliation recovers the existing opaque receipt |
| lost Kindred acknowledgement | a replacement grant retrieves the same operation and acknowledges the recovered receipt |
| different operation for the same source | Legacy Table source-subject uniqueness converges to the original receipt |
| divergent payload or revision | conflict; no source or destination overwrite |
| destination deletion | safe deleted/conflict state; tombstone prevents recreation |
| transient unavailable acknowledgement | does not replace completion or destroy recovery state |

## Logging, analytics, retention, and deletion

Neither application logs or reports identity, content, source references, revision digests, credentials, sessions, headers, request/response bodies, family/user/recipe identifiers, provider payloads, or credential-bearing URLs. Safe output is limited to opaque operation/receipt references and categorical status/error codes. The Legacy Table `/sso` document suppresses CookieYes, Google tags, PostHog initialization, identify/reset/capture calls, replay, and service-worker registration for its entire lifetime.

Transfer credentials expire after 10 minutes. Kindred operations expire after 400 days. Legacy Table operations and replay tombstones follow the Stage 12A 400-day/replay-retention contract. Source and destination copies retain independent deletion control. Kindred account/community deletion removes source content; the non-content keyed operation remains only as a bounded replay/reconciliation record. Destination deletion removes imported content and retains the Stage 12A keyed tombstone.

## Production configuration and rollout

Required names, without values:

- Kindred backend: `LEGACY_TABLE_TRANSFER_ENABLED`, `LEGACY_TABLE_TRANSFER_HASH_KEY`, `LEGACY_TABLE_API_ORIGIN`, `LEGACY_TABLE_WEB_ORIGIN`, `UBUNTU_SSO_SECRET`, `CORS_ORIGINS`, `MONGO_URL`, `DB_NAME`.
- Legacy Table backend: `RECIPE_IMPORT_HASH_KEY`, `UBUNTU_SSO_SECRET`, `CORS_ORIGINS`, `MONGO_URL`, `DB_NAME`, `JWT_SECRET`.
- Legacy Table web: `REACT_APP_BACKEND_URL`, `REACT_APP_KINDRED_API_ORIGIN`.

Deployment order is: verify Legacy Table transactions/indexes/key; deploy Legacy Table; deploy Kindred with transfer disabled; verify both commits; configure exact origins/CORS and server keys under separate authorization; run a synthetic smoke plan; enable Kindred last. Rollback disables Kindred first, preserves destination receipts/tombstones, lets grants expire, and never deletes accepted recipes automatically.

## Verification evidence and limitations

- Kindred focused backend/security: 300 passed, 11 environment-gated skips.
- Kindred Stage 12B plus Release 11/checkout focused gate: 39 passed.
- Eight disposable Kindred transaction/security campaigns passed when run separately to avoid Motor event-loop coupling; the new Stage 12B concurrency campaign also passed after the final durable-link hardening.
- Kindred frontend: 37 passed; production build and six-route prerender passed.
- Built browser fragment/header, legacy-link, third-party isolation, and service-worker campaigns passed with synthetic data and no external requests.
- Android debug build passed with 340 tasks in a disposable copy; the unsigned iOS device build produced the expected application artifact with signing disabled.
- Legacy Table backend Stage 12A contract/transaction suite: 34 passed against a disposable replica set.
- Legacy Table frontend: 6 passed after the final analytics and credential-lifecycle guards; production build/five-route prerender and both built SSO/import isolation campaigns passed. The import campaign exercised the real built application with synthetic SSO, header-only retrieval, reconciliation, acceptance, acknowledgement, zero credential persistence, and zero third-party requests.
- OpenAPI, compilation, fatal lint, Black 26.1.0, `git diff --check`, credential/logging/provider/analytics/generated-artifact scans, and repository asset-isolation checks passed.

Remaining activation limitations: authenticated production verification of `RECIPE_IMPORT_HASH_KEY`, Mongo transaction topology and required indexes; both coordinated PR merges/deployments; exact production CORS/web configuration; and an approved synthetic production smoke plan. This draft does not activate delivery.

Dependency scans also retain repository-wide baseline findings outside this bridge: Kindred reports 18 low, 96 moderate, 131 high, and 5 critical dependency advisories; Legacy Table reports 3 low, 10 moderate, and 24 high advisories. This change adds no dependency or lockfile updates. Those broader remediation tracks remain explicit limitations rather than silently claimed green results.

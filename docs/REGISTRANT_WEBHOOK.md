# Registrant webhook

Every Kindred event can receive registrants from any ticketing platform, form
tool, or automation service that can send a signed HTTP request. Each request
creates (or updates) one invitation, marks the person "coming" for the sessions
they bought, and emails them their private Kindred invitation.

The same fields can be uploaded as a CSV from the event's **Import registrants**
panel. Both paths share one pipeline, so they behave the same way.

## Getting the URL and secret

In Kindred, open the event → **Import registrants** → **Webhook** →
**Create webhook**. You get:

- a URL like `https://<kindred-api-host>/api/inbound/registrants/<hook-id>`
- a secret that starts with `kwhsec_`

Only organizers of the event's community can see these. **Rotate secret**
replaces the secret immediately; the URL stays the same and the old secret stops
working. Rotate it if it is ever shared by mistake.

## Request

```
POST /api/inbound/registrants/<hook-id>
Content-Type: application/json
X-Kindred-Timestamp: 1767225600
X-Kindred-Signature: sha256=5f0c…
```

Body (UTF-8 JSON, at most 16 KB):

```json
{
  "name": "Ada Example",
  "email": "ada@example.com",
  "sessions": ["Day One Workshop", "Closing Circle"]
}
```

| Field | Required | Notes |
|---|---|---|
| `email` | yes | Identifies the person. Case and surrounding spaces are ignored, so re-sending the same person never makes a second invitation. |
| `name` | no | Full name. `first_name` + `last_name` are accepted instead. |
| `sessions` | no | A list of session titles or session ids, or one string separated by `;` or `|`. Titles ignore case and extra spaces. `"all"` means every session that takes RSVPs. Omit it (or send `[]`) to invite the person without marking any session. |

Other fields are ignored, so you can forward a platform's payload after mapping
these three.

**Sessions are an exact list.** Kindred marks the person "coming" for exactly the
sessions listed. If a later request for the same email lists fewer sessions, the
marks Kindred added for the dropped sessions are removed. An answer the person
gave themselves in Kindred is never overwritten.

## Signature

1. Take the Unix time in seconds as a string, for example `1767225600`.
2. Build the message `<timestamp>.<raw request body>` — the exact bytes you send.
3. Compute HMAC-SHA256 of that message with the secret as the key, hex-encoded.
4. Send `X-Kindred-Timestamp: <timestamp>` and
   `X-Kindred-Signature: sha256=<hex>`.

Kindred refuses a request when:

- the signature does not match the event's current secret (`401 invalid_signature`),
- the timestamp is more than 5 minutes from Kindred's clock (`401 stale_timestamp`),
- the exact same signature was already accepted (`409 replayed`). Re-sending a
  person is fine — sign it again with a new timestamp.

During a rotation you may send two signatures separated by a comma
(`sha256=<old>,sha256=<new>`); either one matching the current secret is enough.

### Examples

Shell:

```bash
ts=$(date +%s)
body='{"name":"Ada Example","email":"ada@example.com","sessions":["Day One Workshop"]}'
sig=$(printf '%s.%s' "$ts" "$body" | openssl dgst -sha256 -hmac "$KINDRED_SECRET" -hex | sed 's/^.* //')
curl -X POST "$KINDRED_URL" \
  -H "Content-Type: application/json" \
  -H "X-Kindred-Timestamp: $ts" \
  -H "X-Kindred-Signature: sha256=$sig" \
  --data "$body"
```

Python:

```python
import hashlib, hmac, json, time, urllib.request

body = json.dumps({"name": "Ada Example", "email": "ada@example.com",
                   "sessions": ["Day One Workshop"]}).encode()
ts = str(int(time.time()))
sig = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
req = urllib.request.Request(URL, data=body, method="POST", headers={
    "Content-Type": "application/json",
    "X-Kindred-Timestamp": ts,
    "X-Kindred-Signature": "sha256=" + sig,
})
print(urllib.request.urlopen(req).read())
```

JavaScript (Node 18+):

```js
import crypto from "node:crypto";

const body = JSON.stringify({ name: "Ada Example", email: "ada@example.com", sessions: ["Day One Workshop"] });
const ts = Math.floor(Date.now() / 1000).toString();
const sig = crypto.createHmac("sha256", SECRET).update(`${ts}.${body}`).digest("hex");
await fetch(URL, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Kindred-Timestamp": ts, "X-Kindred-Signature": `sha256=${sig}` },
  body,
});
```

## Responses

`200`:

```json
{"status": "accepted", "result": "created", "sessions": ["Day One Workshop"], "invitation": "sent"}
```

- `result`: `created`, `updated` (sessions or name changed), `skipped` (already
  up to date), or `flagged` (see below).
- `invitation`: `sent`, `already_sent`, `not_sent` (the email provider refused
  it), `not_requested` (flagged rows send nothing), `delivery_disabled` or
  `provider_unconfigured` (email is off on this Kindred deployment; the
  invitation still exists and the organizer can share its link).

Errors, all with `{"status": "rejected", "code": …}`:

| Status | Code | Meaning |
|---|---|---|
| 400 | `invalid_json` | Body is not JSON. |
| 401 | `missing_signature`, `invalid_timestamp`, `stale_timestamp`, `invalid_signature` | See Signature. An unknown URL also answers `401`. |
| 409 | `replayed` | This exact signed request was already accepted. |
| 409 | `organizer_draft_import_blocked` | The event is still a private draft. Retry after it is published. |
| 413 | `payload_too_large` | Body over 16 KB. |
| 422 | `invalid_payload` | Missing or invalid email, or `sessions` is not a list of strings. |
| 422 | `unknown_session`, `ambiguous_session` | A session title doesn't exist, or two sessions share it (send the id). Nothing was changed. |

Retry on `5xx` and on `409 organizer_draft_import_blocked`. Don't retry other
`4xx` without fixing the request.

## Possible duplicates

If the name matches someone already invited to the event under a different
email, Kindred does not create a second invitation. The request returns
`result: "flagged"` and the organizer sees the pair under **Possible
duplicates**, where they can create a separate invitation, apply the sessions to
the existing invitee, or dismiss it. Later requests for the same email follow
that decision.

## CSV upload

The CSV panel takes the same three fields. The first row must name the columns.
Recognized headers (case, spaces and punctuation ignored):

- email: `Email`, `Email Address`, `Attendee Email`
- name: `Name`, `Full Name`, `Attendee Name` — or `First Name` + `Last Name`
- sessions: `Sessions`, `Sessions Purchased`, `Activities`, `Tickets`, `Ticket Type`

Commas, semicolons and tabs are all accepted as the column separator. Several
rows with the same email (one row per ticket, as many platforms export) are
combined into one person. Up to 2,000 rows and 1 MB per upload. The report lists
every row as created, updated, skipped, flagged or error, with its row number.

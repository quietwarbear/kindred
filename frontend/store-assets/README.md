# Kindred mobile store screenshot campaign

This directory contains repository-managed **proposed** Apple and Google store creative. Nothing here has been uploaded or published.

## Narrative

1. Start a family reunion.
2. Build a multiday itinerary.
3. Share one private invitation.
4. RSVP without creating an account.
5. See response gaps and planning progress.
6. Preserve stories and memories after the reunion.

The exact captions, order, alt text, dimensions, and SHA-256 hashes are recorded in `manifest.json`.

## Reproducible source

Run from `frontend`:

```bash
npm run build
npm run store-assets:generate
```

`scripts/generate-store-assets.js` starts the real production frontend build on a loopback-only server, blocks external requests, provides in-process synthetic API responses, and captures the actual rendered application. It does not access a production database, invitation, provider payload, email history, analytics identity, or customer record.

The synthetic campaign uses:

- The Rivers Family Reunion
- Maya Rivers and Jordan Rivers
- Cedar Grove, Georgia
- July 16–18, 2027
- synthetic itinerary, response totals, planning records, invitation state, and memory text

These people, family-space records, responses, and invitations are disposable fixtures created solely in the screenshot generator. No email address appears in the source campaign or final creative. The private RSVP credential is synthetic, remains in a URL fragment and authorization header inside the local test harness, and is never rendered into an image, filename, report, or manifest.

## Final export locations

| Platform set | Directory | Dimensions | Files |
|---|---|---:|---:|
| Apple iPhone 6.9-inch | `apple/iphone-6.9` | 1320 × 2868 PNG | 6 |
| Apple iPad 13-inch | `apple/ipad-13` | 2064 × 2752 PNG | 6 |
| Google phone | `google/phone` | 1080 × 1920 PNG | 6 |

The Apple dimensions are accepted current App Store Connect sizes for the 6.9-inch iPhone and 13-inch iPad families. The Google exports use the recommended 9:16 portrait ratio at 1080-pixel minimum resolution.

References:

- https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/
- https://support.google.com/googleplay/android-developer/answer/9866151

## Automated validation

The generator fails unless:

- every image has its exact expected pixel dimensions;
- every PNG has no alpha channel;
- captions remain inside the safe area;
- caption typography remains readable;
- no horizontal crop is present;
- the intended application panel intersects the viewport;
- rendered visible text contains no email, URL, reviewer, demo, staging, development, generated-tool, token, credential, or `example.invalid` marker;
- all external application/provider requests are blocked.

The final review should also visually inspect all 18 files at full size and store-thumbnail scale before any console upload.

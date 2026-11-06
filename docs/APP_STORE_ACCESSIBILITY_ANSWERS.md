# App Store accessibility answers (draft for owner)

Drafted November 2026 with the K12 accessibility pass. **Nothing here has been submitted.** App Store Connect → the app → **Accessibility** asks, per device (iPhone, iPad), whether people can complete the app's *common tasks* with each feature. Apple's rule is to claim a feature only when that is true for every common task, so each answer below names what still has to be checked on a real device first.

## Common tasks used for these answers

1. Open an invitation and RSVP to an event (with or without an account).
2. Choose which activities you are coming to, and how you will join.
3. Read the itinerary, including times, places and activity materials.
4. Read announcements from the organizer.
5. Organizer: create an event, add activities, send invitations.
6. Share a memory (story, photo or voice note) to the event.

## Answers

| Feature | Draft answer | Basis | Verify before claiming |
|---|---|---|---|
| **VoiceOver** | Yes, after verification | RSVP flow passes automated axe checks at every step. Focus moves to each new step's heading. Answer buttons announce pressed state and sit in groups named for the activity. Errors are announced. Decorative icons are hidden. New-tab links say so. | One full pass of tasks 1–6 with VoiceOver on an iPhone. The PR checklist lists what to listen for. |
| **Voice Control** | Not yet | Buttons have visible text labels, which Voice Control needs. Never tested. | Say "Tap Attending", "Tap Coming" and so on through tasks 1–3. |
| **Larger Text** | Yes, after verification | Before K12 the iOS app ignored the system text size. It now follows Dynamic Type, including the accessibility sizes, via `-apple-system-body`. All text sizes are relative (rem), with no fixed-pixel text on the main screens. | Settings → Accessibility → Larger Text at the largest size, then tasks 1–6. Look for clipped or overlapping text. |
| **Dark Interface** | Yes | Follows the system light/dark setting by default (`defaultTheme="system"`), with a manual switch in the menu. | Quick look at tasks 1–4 in dark mode. |
| **Differentiate Without Color Alone** | Yes, after verification | Selected answers are marked with `aria-pressed` and a border change as well as colour. Statuses are written out ("Coming", "Not coming"), not shown as colour alone. | Visual check with Settings → Accessibility → Display → Differentiate Without Color. |
| **Sufficient Contrast** | Yes, after verification | Text on the invite, RSVP, itinerary and announcement screens and in the emails was checked against WCAG AA (4.5:1). Failing greys were darkened. | Spot-check the organizer screens, which weren't part of this pass. |
| **Reduced Motion** | Yes | System Reduce Motion now turns off animated transitions and smooth scrolling. The app has no autoplaying animation. | None needed. |
| **Captions** | Not applicable: leave unclaimed | The app plays no video. Voice notes are audio only, and oral-history threads can be transcribed. | If in-app video is ever added, it needs captions before this can be claimed. |
| **Audio Descriptions** | Not applicable: leave unclaimed | No video. | None. |

## Android (Google Play)

Play has no equivalent per-feature declaration. TalkBack and the system font scale are covered by the same fixes; Android's WebView already followed the system font size before K12. Run tasks 1–3 once with TalkBack on before the Play submission.

## What changed in K12 (for reference)

- **iOS text size:** follows Dynamic Type.
- **System settings:** Reduce Motion is respected.
- **Guest RSVP focus:** focus moves to each step heading. Focus doesn't move on page load.
- **Guest RSVP announcements:** step changes and errors are announced.
- **Grouping:** activity answer and choice groups are named for their activity, on the RSVP page and in the attendee hub.
- **Labels:** the attendee hub's story box has a label.
- **Contrast:** grey text below 4.5:1 was darkened on the RSVP and invite pages, the notification panel, and the invitation and announcement emails.
- **Fixed-pixel text:** removed from the notification panel.
- **Emails:** invitation and announcement emails declare `lang="en"` and a charset.
- **Focus ring:** announcement composer fields show a full-strength focus ring.

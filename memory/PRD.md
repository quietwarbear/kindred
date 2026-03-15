# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build "Kindred," a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build.

## Architecture
- **Frontend**: React SPA (PWA), Tailwind CSS, Shadcn UI, react-force-graph-2d
- **Backend**: FastAPI + MongoDB (11 modular route files)
- **Auth**: JWT + Google OAuth
- **Payments**: Stripe (web) + RevenueCat (mobile iOS/Android, configured)
- **AI**: Gemini via Emergent LLM Key
- **Bundle ID**: `com.ubuntumarket.kindred` (Apple)

## All Implemented Features

### Core Infrastructure
- Full auth (JWT, Google OAuth, password recovery, account deletion)
- Modular backend (server.py → 11 route files)
- PWA: service worker, web manifest, offline fallback, install prompt
- Multi-courtyard membership + community switcher

### Communication & Activity
- Activity Feed (paginated, filtered by type)
- Announcements (inline edit/delete)
- Chat rooms (attachments, pin, delete)
- Notifications (bell, badge, history, browser push)

### Events & Gatherings
- Template-based events with inline editing & deletion
- RSVP, agenda, volunteers, potluck, invites, Zoom, reminders

### Timeline, Memory & Legacy
- Timeline: search, type filters, CSV export
- Memory Vault: photos, voice recording (MediaRecorder), AI auto-tagging
- AI tagging: sentiment + mood analysis, batch re-tagging
- Legacy Threads: 7 categories, voice notes, threaded comments

### Kinship & Community
- Kinship Map: force-directed network graph
- Relationship-based invitation shortcuts
- Courtyards & Subyards with full CRUD

### Finance & Billing
- Stripe: one-time payments + 5-tier subscriptions
- Add-on marketplace (Storage, Templates, SMS)
- RevenueCat: full integration (webhook, offerings, restore, receipt validation, config)
- Bundle ID: com.ubuntumarket.kindred

### PWA
- Service worker with offline caching
- Web App Manifest (standalone, shortcuts)
- Offline fallback page
- Install prompt banner
- Apple meta tags (web-app-capable, touch icons)

## Remaining Backlog
- Community Mood Board (sentiment trend visualization)
- Weekly community digest emails
- Native mobile wrapper (React Native / Capacitor)

# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build "Kindred," a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build.

## Architecture
- **Frontend**: React SPA (PWA + Capacitor native)
- **Backend**: FastAPI + MongoDB (11 modular route files)
- **Auth**: JWT + Google OAuth + native push tokens
- **Payments**: Stripe (web) + RevenueCat (mobile, configured)
- **AI**: Gemini via Emergent LLM Key
- **Bundle ID**: `com.ubuntumarket.kindred`
- **Native**: Capacitor 6 (iOS + Android)

## All Implemented Features

### Core Infrastructure
- Modular backend (server.py → 11 route files)
- Full auth (JWT, Google OAuth, password recovery, account deletion)
- Multi-courtyard membership + community switcher
- PWA: service worker, manifest, offline fallback, install prompt
- Capacitor native wrapper (iOS + Android)

### Native Mobile (Capacitor)
- Native bridge with web fallbacks (camera, push, haptics, status bar, keyboard)
- Push notification registration + token storage
- Camera access for Memory Vault photos
- Haptic feedback on key interactions
- App lifecycle management (back button, URL open)
- Status bar + splash screen configuration
- Build scripts + deployment guide (NATIVE_DEPLOY.md)

### Communication & Activity
- Activity Feed (paginated, type-filtered)
- Announcements (inline edit/delete), Chat rooms, Notifications
- Browser + native push notifications

### Events, Timeline, Memory & Legacy
- Template-based events with inline editing & deletion
- Timeline with search, filters, CSV export
- Memory Vault with AI tagging, voice recording, native camera
- Legacy Threads with 7 categories and voice notes
- Kinship Map with network graph + invite shortcuts

### Finance & Billing
- Stripe: one-time + subscriptions + add-on marketplace
- RevenueCat: webhook, offerings, restore, receipt validation
- 5-tier subscription system

## Remaining Backlog
- Community Mood Board (sentiment trend visualization)
- Weekly community digest emails

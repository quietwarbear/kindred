# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build "Kindred," a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. A Digital Courtyard layout with courtyards/subyards, kinship mapping, smart gathering planning, timeline archive, shared funds/travel, and Legacy Table connection settings.

## Architecture
- **Frontend**: React SPA, Tailwind CSS, Shadcn UI, react-force-graph-2d
- **Backend**: FastAPI + MongoDB (modular router-based structure)
- **Auth**: JWT + Google OAuth
- **Payments**: Stripe (web checkout + subscriptions + add-ons) + RevenueCat (mobile, configured)
- **AI**: Gemini via Emergent LLM Key (auto-tagging, sentiment, mood, batch retag)

## Backend Structure
```
/app/backend/
├── server.py           # Clean orchestrator (~70 lines)
├── db.py               # Database connection + collections
├── models.py           # Pydantic models
├── dependencies.py     # Shared helpers, auth, constants
├── security.py         # JWT + password hashing
├── ai_tagging.py       # Gemini AI tagging with sentiment/mood + batch retag
└── routes/
    ├── activity.py     # Activity feed
    ├── auth.py         # Auth: bootstrap, login, me, google, profile, etc.
    ├── community.py    # Community: overview, courtyard, subyards, kinship, invites, multi-courtyard
    ├── communications.py # Announcements, chat, notifications
    ├── events.py       # Events CRUD + inline edit/delete, RSVP, agenda, etc.
    ├── finance.py      # Travel plans, budget plans, payments, stripe webhook
    ├── legacy.py       # Legacy table config/sync
    ├── polls.py        # Polls CRUD, voting, close
    ├── revenuecat.py   # RevenueCat webhook, receipt validation, status
    ├── subscriptions.py # Plans, current, checkout, cancel, feature-check, add-ons
    └── timeline.py     # Timeline + search/export, memories CRUD, threads, batch retag
```

## All Implemented Features

### Core
- Full auth (JWT, Google OAuth, password recovery, account deletion)
- Modular backend architecture (server.py orchestrates 11 route files)
- 5-step onboarding, Courtyards & Subyards CRUD + inline editing
- Members, invites, role assignments

### Activity & Communication
- Activity Feed: dedicated page with type filters and pagination
- Announcements with inline editing + delete
- Chat rooms with attachments, pinning, delete
- Notifications: bell, unread badge, dropdown, mark-read, history, preferences
- Browser push notifications (Web Notifications API)

### Gatherings & Events
- Template-based events with recurrence
- Inline editing & deletion for events
- RSVP, agenda, volunteers, potluck, event invites, Zoom links, reminders

### Timeline & Memory Vault
- Unified timeline with search, type filters, CSV export
- Memory Vault with photos, voice notes, AI auto-tagging
- In-app voice recording (MediaRecorder API)
- Enhanced AI tagging: sentiment + mood analysis, batch re-tagging
- Sentiment/mood badges on memory cards

### Legacy Threads & Kinship
- Legacy Threads: 7 categories, filters, voice notes, comments, elder attribution
- Kinship Map: interactive force-directed network graph
- Relationship-based invitation shortcuts (quick-invite by kinship group)

### Decisions, Finance & Billing
- Polls & Voting: create/vote/close/delete
- Stripe checkout + webhooks (one-time + subscriptions)
- 5-tier subscription system (Seedling → Elder Grove)
- Add-on marketplace: Extra Storage (10GB/25GB), Premium Templates, SMS Packs (100/500)
- Add-on Stripe checkout with purchase history
- RevenueCat: webhook handler, receipt validation, tier mapping (configured with API keys)
- Budgets + travel plans CRUD

### Multi-Courtyard
- Users belong to multiple communities
- Community switcher in sidebar
- Join communities via invite code, switch between communities

## Prioritized Backlog

### P2 (Future)
- Full RevenueCat mobile deployment (SDK integration for iOS/Android)
- PWA features for mobile use
- Community Mood Board (sentiment trend visualization)
- Weekly community digest emails

# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build "Kindred," a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. A Digital Courtyard layout with courtyards/subyards, kinship mapping, smart gathering planning, timeline archive, shared funds/travel, and Legacy Table connection settings.

## Architecture
- **Frontend**: React SPA, Tailwind CSS, Shadcn UI, react-force-graph-2d
- **Backend**: FastAPI + MongoDB (modular router-based structure)
- **Auth**: JWT + Google OAuth
- **Payments**: Stripe (web) + RevenueCat (mobile, infrastructure ready)
- **AI**: Gemini via Emergent LLM Key (auto-tagging, sentiment, mood)

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
    ├── activity.py     # Activity feed (paginated, filtered)
    ├── auth.py         # Auth: bootstrap, login, me, google, profile, etc.
    ├── community.py    # Community: overview, courtyard, subyards, kinship, invites, multi-courtyard
    ├── communications.py # Announcements, chat, notifications
    ├── events.py       # Events CRUD + inline edit/delete, RSVP, agenda, etc.
    ├── finance.py      # Travel plans, budget plans, payments, stripe webhook
    ├── legacy.py       # Legacy table config/sync
    ├── polls.py        # Polls CRUD, voting, close
    ├── revenuecat.py   # RevenueCat webhook, receipt validation, status
    ├── subscriptions.py # Plans, current, checkout, cancel, feature-check
    └── timeline.py     # Timeline archive + search/export, memories CRUD, threads, batch retag
```

## All Implemented Features

### Core Infrastructure
- Full auth (JWT, Google OAuth, password recovery, account deletion)
- Backend refactored: modular router-based architecture
- 5-step onboarding for new hosts
- Courtyards & Subyards with full CRUD + inline editing
- Members, invites, role assignments

### Activity & Communication
- **Activity Feed**: Dedicated page with type filters, pagination
- Scoped announcements with inline editing + delete
- Chat rooms with attachments, pinning, delete
- Notifications: bell icon, unread badge, dropdown, mark-read, history, preferences
- Browser push notifications (Web Notifications API)

### Gatherings & Events
- Template-based events with recurrence rules
- Inline editing & deletion for events
- RSVP, agenda, volunteer sign-ups, potluck
- Event invites, Zoom-link support, one-click reminders

### Timeline & Memory Vault
- Unified timeline with search, type filters, CSV export
- Memory Vault with photo upload, voice notes, and AI auto-tagging
- **In-app voice recording** (MediaRecorder API) for memories, stories, threads
- **Enhanced AI tagging**: sentiment analysis (positive/neutral/reflective/celebratory/somber), mood detection
- **Batch re-tagging**: "Re-tag all with AI" button for bulk improvement
- Sentiment and mood badges on memory cards

### Legacy Threads & Kinship
- **Legacy Threads**: 7 categories, filters, voice notes, threaded comments, elder attribution
- **Kinship Map**: Interactive force-directed network graph (react-force-graph-2d)
- Add/delete relationships with type-specific colors and legends
- Kinship group shortcuts for bulk invitations

### Decisions, Finance & Billing
- Polls & Voting: create/vote/close/delete, multi-select
- Stripe checkout + webhooks (one-time and subscriptions)
- 5-tier subscription system (Seedling → Elder Grove)
- Budgets + travel plans with CRUD
- **RevenueCat infrastructure**: webhook handler, receipt validation, tier mapping (ready for mobile deployment)

### Multi-Courtyard
- Users can belong to multiple communities
- Community switcher in sidebar
- Join additional communities via invite code
- Switch between communities (session refresh)

## Prioritized Backlog

### P1
- Relationship-based invitation shortcuts UI (backend exists)
- Add-on purchases (storage, templates, SMS credits)

### P2
- Full RevenueCat mobile deployment (requires API key configuration)
- Progressive Web App (PWA) features for mobile use

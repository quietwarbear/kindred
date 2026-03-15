# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build "Kindred," a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. A Digital Courtyard layout with courtyards/subyards, kinship mapping, smart gathering planning, timeline archive, shared funds/travel, and Legacy Table connection settings.

## Architecture
- **Frontend**: React SPA, Tailwind CSS, Shadcn UI
- **Backend**: FastAPI + MongoDB (modular router-based structure)
- **Auth**: JWT + Google OAuth
- **Payments**: Stripe (test key in env) — one-time checkout + subscription tiers

## Backend Structure (Refactored - Mar 2026)
```
/app/backend/
├── server.py           # ~60 lines - Clean orchestrator (imports routers, CORS, shutdown)
├── db.py               # Database connection + collections
├── models.py           # ~400 lines - Pydantic models
├── dependencies.py     # ~500 lines - Shared helpers, auth, constants
├── security.py         # JWT + password hashing
├── courtyard_helpers.py
├── ai_tagging.py
└── routes/             # Domain-specific routers (all prefixed /api)
    ├── auth.py         # Auth: bootstrap, login, me, google, profile, onboarding, account deletion, transfer-ownership
    ├── community.py    # Community: overview, courtyard home/structure, subyards, kinship, invites, members
    ├── communications.py # Announcements, chat rooms, notifications
    ├── events.py       # Events CRUD, RSVP, invites, roles, agenda, checklist, volunteers, potluck
    ├── finance.py      # Travel plans, budget plans, payments, stripe webhook
    ├── legacy.py       # Legacy table config/sync
    ├── polls.py        # Polls CRUD, voting, close
    ├── subscriptions.py # Plans, current, checkout, cancel, feature-check
    └── timeline.py     # Timeline archive, memories, threads
```

## Implemented Features

### Core
- Full auth (JWT, Google OAuth, password recovery)
- User profiles, settings, notification preferences
- 5-step onboarding for new hosts
- Courtyards & Subyards with full CRUD + inline editing
- Members, invites, role assignments

### Gatherings
- Template-based events with recurrence rules
- RSVP, agenda, volunteer sign-ups, potluck
- Event invites, Zoom-link support, travel coordination
- One-click reminder sending

### Communication
- Scoped announcements with inline editing + delete
- Chat rooms with attachments, pinning, delete
- Notifications: bell icon, unread badge, dropdown, mark-read, history, preferences

### Decisions & Finance
- Polls & Voting: create/vote/close/delete, multi-select
- Stripe checkout + webhooks
- Budgets + travel plans with CRUD

### Account Management
- Account deletion (Play Store compliant)
- Ownership transfer flow
- Edit/delete for: subyards, kinship, announcements, chat messages, budgets, travel plans

### Inline Editing
- Click-to-edit subyards (name, description)
- Click-to-edit announcements (title, body)
- Save/Cancel buttons + Enter/Escape keyboard shortcuts

### Subscription Monetization (Feb 2026)
- 5-tier subscription system: Seedling, Sapling, Oak, Redwood, Elder Grove
- Monthly & annual billing with ~15% annual discount
- Stripe checkout integration for plan upgrades
- Feature gating by tier
- Subscription management: checkout, status polling, cancel
- Pricing page with plan comparison cards

### Backend Refactor (Mar 2026) ✅
- Migrated all routes from monolithic server.py (~2400 lines) to 9 domain-specific router files
- server.py reduced to ~60 lines (clean orchestrator)
- Full regression test: 38/38 backend API tests pass
- Fixed Pydantic model mismatches discovered during testing

## Prioritized Backlog

### P1
- Inline editing for events/memories
- Advanced timeline filters/search/export
- Relationship-based invitation shortcuts

### P2
- Multi-courtyard membership
- Push notifications
- Legacy Threads & Kinship Map visualization
- Memory Vault with AI auto-tagging + voice notes
- Add-on purchases (storage, templates, SMS)
- App Store Connect / Google Play Billing SDK integration (RevenueCat)

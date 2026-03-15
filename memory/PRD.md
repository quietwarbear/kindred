# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build "Kindred," a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. A Digital Courtyard layout with courtyards/subyards, kinship mapping, smart gathering planning, timeline archive, shared funds/travel, and Legacy Table connection settings.

## Architecture
- **Frontend**: React SPA, Tailwind CSS, Shadcn UI
- **Backend**: FastAPI + MongoDB (refactored modular structure)
- **Auth**: JWT + Google OAuth
- **Payments**: Stripe (test key in env)

## Backend Structure
```
/app/backend/
├── server.py         # ~2200 lines - API routes
├── db.py             # Database connection + collections
├── models.py         # ~395 lines - Pydantic models
├── dependencies.py   # ~370 lines - Shared helpers, auth, constants
├── security.py       # JWT + password hashing
├── courtyard_helpers.py
├── ai_tagging.py
└── routes/           # (Future decomposition)
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

## Prioritized Backlog

### P1
- Further split server.py into domain routers
- Inline editing for events/memories
- Advanced timeline filters/search/export
- Relationship-based invitation shortcuts

### P2
- Multi-courtyard membership
- Push notifications
- Legacy Threads & Kinship Map visualization
- Memory Vault with AI auto-tagging + voice notes
- Monetization (tiered subscriptions)

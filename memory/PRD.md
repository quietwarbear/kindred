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
├── server.py           # ~65 lines - Clean orchestrator
├── db.py               # Database connection + collections
├── models.py           # Pydantic models
├── dependencies.py     # Shared helpers, auth, constants
├── security.py         # JWT + password hashing
├── courtyard_helpers.py
├── ai_tagging.py       # Gemini AI tagging for memories
└── routes/             # Domain-specific routers (all prefixed /api)
    ├── activity.py     # Activity feed (paginated, filtered)
    ├── auth.py         # Auth: bootstrap, login, me, google, profile, etc.
    ├── community.py    # Community: overview, courtyard, subyards, kinship, invites, multi-courtyard
    ├── communications.py # Announcements, chat, notifications
    ├── events.py       # Events CRUD + inline edit/delete, RSVP, agenda, etc.
    ├── finance.py      # Travel plans, budget plans, payments, stripe webhook
    ├── legacy.py       # Legacy table config/sync
    ├── polls.py        # Polls CRUD, voting, close
    ├── subscriptions.py # Plans, current, checkout, cancel, feature-check
    └── timeline.py     # Timeline archive + search/export, memories CRUD, threads
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
- Inline editing & deletion for events
- One-click reminder sending

### Communication
- Scoped announcements with inline editing + delete
- Chat rooms with attachments, pinning, delete
- Notifications: bell icon, unread badge, dropdown, mark-read, history, preferences
- Browser push notifications (Web Notifications API)

### Decisions & Finance
- Polls & Voting: create/vote/close/delete, multi-select
- Stripe checkout + webhooks
- Budgets + travel plans with CRUD

### Account Management
- Account deletion (Play Store compliant)
- Ownership transfer flow
- Edit/delete for: subyards, kinship, announcements, chat messages, budgets, travel plans

### Subscription Monetization (Feb 2026)
- 5-tier subscription system
- Monthly & annual billing with Stripe
- Feature gating by tier

### Phase 1: Activity & UX Enhancements (Mar 2026)
- **Activity Feed**: Dedicated page showing all community activity with type filters and pagination
- **Inline Editing**: Click-to-edit for events (title, description, date, location, format) and memories (title, description)
- **Event & Memory Deletion**: With confirmation dialogs
- **Timeline Search**: Full-text search across all timeline items
- **Timeline Type Filters**: Filter by gathering/memory/story types
- **Timeline CSV Export**: Download timeline data as CSV with auth
- **Kinship Group Shortcuts**: API for invite shortcuts based on relationship types

### Phase 2: Legacy & Kinship (Mar 2026)
- **Kinship Map**: Interactive network graph visualization using react-force-graph-2d
  - Add/delete relationships with type-specific colors
  - Force-directed graph on dark canvas with node labels
  - Color legend for relationship types
  - Relationship list view with delete
- **Legacy Threads**: Dedicated page for preserving stories and oral history
  - 7 categories (Oral History, Sermon Archive, Youth Reflection, Community Dialogue, Family Lore, Migration Story, Recipe/Tradition)
  - Category filters with colored badges
  - Voice note support
  - Threaded comments/responses
  - Elder/speaker attribution

### Phase 3: Platform Scaling (Mar 2026)
- **Multi-courtyard Membership**: Users can belong to and switch between multiple communities
  - `community_ids` array on user docs
  - Community switcher in sidebar
  - Join additional communities via invite code while logged in
  - Switch between communities (refreshes session)
- **Browser Push Notifications**: Web Notifications API
  - Permission request on app load
  - Browser notification when new unread count increases

## Prioritized Backlog

### P1
- Relationship-based invitation shortcuts (backend endpoint exists, frontend UI needed)
- Add-on purchases (storage, templates, SMS)

### P2
- App Store Connect / Google Play Billing SDK (RevenueCat)
- Memory Vault voice-note recording (currently upload-only)
- Advanced AI auto-tagging improvements

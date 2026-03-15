# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build "Kindred," a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. A Digital Courtyard layout with courtyards/subyards, kinship mapping, smart gathering planning, timeline archive, shared funds/travel, and Legacy Table connection settings.

## Architecture
- **Frontend**: React SPA, Tailwind CSS, Shadcn UI
- **Backend**: FastAPI + MongoDB (refactored into modular structure)
- **Auth**: JWT + Google OAuth
- **Payments**: Stripe (test key in env)

## Backend Structure (Refactored)
```
/app/backend/
├── server.py         # ~2100 lines - API routes and endpoint handlers
├── db.py             # Database connection and collection references
├── models.py         # ~395 lines - All Pydantic request/response models
├── dependencies.py   # ~370 lines - Shared helpers, auth, constants, notification logic
├── security.py       # JWT token handling, password hashing
├── courtyard_helpers.py  # Courtyard-specific utility functions
├── ai_tagging.py     # AI memory tagging
└── routes/           # (Future: further route decomposition)
```

## What's Implemented
### Core
- Full auth system (JWT, Google OAuth, password recovery)
- User profiles with settings, notification preferences
- Community onboarding (5-step guided flow for new hosts)
- Courtyards & Subyards with CRUD, role mapping, kinship graph
- Members, invites, role assignments

### Gatherings
- Template-based event creation with recurrence rules
- RSVP, agenda builder, volunteer sign-ups, potluck coordination
- Event-level invites, Zoom-link-aware hybrid/online events
- Travel coordination records per event
- One-click reminder sending for pending RSVPs

### Communication
- Scoped announcements (courtyard + subyard) with comments
- Internal chat rooms with attachments, pinning, comments
- Notification system: Bell icon + unread badge, dropdown panel, mark-all-read, notification history, user preferences

### Decisions & Finance
- Polls & Voting: Create/vote/close/delete with percentage bars, multi-select, role-based access
- Stripe checkout sessions with webhook lifecycle
- Contribution packages, transaction ledger, budget plans
- Funds & Travel overview page

### Account Management
- Account deletion (Play Store compliant): password confirmation, ownership-aware blocking
- Ownership transfer: host can hand off community to another member
- Sole-owner deletion cascades to remove entire community

### Edit/Delete Flows (New)
- Subyards: PUT/DELETE with chat room cleanup
- Kinship relationships: DELETE
- Announcements: PUT/DELETE
- Chat messages: DELETE (own or organizer+)
- Budget plans: PUT/DELETE
- Travel plans: PUT/DELETE (creator or organizer+)
- Frontend delete buttons on all entity cards

### Infrastructure
- MongoDB aggregation pipelines for efficient payment calculations
- Backend refactored: extracted db.py, models.py, dependencies.py from monolithic server.py
- Comprehensive test coverage (iterations 8-12)

## Prioritized Backlog
### P0
- Further split server.py into domain routers (auth.py, events.py, polls.py, etc.)

### P1
- Edit flows for subyards/events/memories (inline editing UI)
- Advanced timeline filters/search/export
- Relationship-based invitation shortcuts and gathering suggestions
- Smarter unread indicators

### P2
- Multi-courtyard membership
- Push notifications, SMS/email auth
- Legacy Threads & Kinship Map visualization
- Advanced Memory Vault with AI auto-tagging and voice notes
- Monetization (tiered subscription model)
- External travel provider connections
- Live Legacy Table import/export

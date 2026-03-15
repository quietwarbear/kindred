# Kindred / Digital Courtyard PRD

## Original Problem Statement
Build “Kindred,” a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. Initial deliverables included an MVP app and strategy pack. Follow-up direction requested preserving the same color scheme and overall appearance while reshaping the product into a Digital Courtyard layout with courtyards/subyards, kinship mapping, smart gathering planning, timeline archive, shared funds/travel, and Legacy Table connection settings. Latest follow-up requested recurring events, announcements, and internal chat for the gathering ecosystem.

## User Choices
- Build both MVP app + strategy pack initially
- Initial MVP: invite-only email/password with Host, Organizer, Member roles; Events Hub, Memory Vault, Legacy Threads; Stripe contributions; voice-note memories + AI auto-tagging via Gemini using Emergent LLM key
- Digital Courtyard expansion: implement UI + backend + as much working functionality as possible; rename community into Courtyard + Subyards; keep Legacy Table connection-ready until docs/credentials arrive; deepen funds/travel workflows
- Recurring events: simple repeat rules (daily / weekly / monthly / yearly)
- Announcements: courtyard-wide + subyard-specific
- Internal chat: courtyard chat + subyard chats
- Chat v1: text + file/image attachments + pinned messages, with comment threads on shared content

## Architecture Decisions
- Frontend remains React SPA with preserved warm visual system, updated Digital Courtyard navigation, and expanded communication modules inside the Courtyards experience
- Backend remains FastAPI + MongoDB, extending into subyards, kinship, travel, budgets, announcements, chat rooms/messages, and recurring event instance generation
- Recurring events are implemented by storing the master event plus pre-generated future instances for simple repeat rules, keeping current CRUD flows compatible
- Chat rooms are auto-provisioned for the main courtyard and each subyard; messages support attachments, comments, and pinned state
- Announcements support scoped delivery (courtyard or subyard) with attachments and comments
- Legacy Table remains architected as connection-ready with saved config and sync preview until external details are provided

## What’s Implemented
- Preserved the existing color scheme/visual identity while redesigning the app around a Digital Courtyard IA
- Home page with upcoming gatherings, active courtyards/subyards, quick actions, role catalog, and relationship/funding prompts
- Courtyards page with parent courtyard overview, subyard creation, role tool mapping, kinship relationship graph entries, member roster, invite management, scoped announcements, and internal chat rooms
- Auth page now includes Google sign-in/sign-up, password recovery by email code, and Settings includes a profile page with name, nickname, avatar/profile image, email, phone number, and member type
- Timeline page with unified archive feed, On This Day reminders, memory uploads, and story thread creation
- Gatherings page with template-based event creation, recurrence rules, auto-generated checklists, role assignment, RSVP, agenda, volunteers, potluck, and travel coordination records
- Gatherings page now supports event-level invites from existing members plus manual guest emails, custom/multi-person role assignments, and Zoom-link-aware hybrid/online invitation records
- Funds & Travel page with contribution packages, transaction ledger, event/family budgets, and travel overview
- Settings page with Legacy Table connection profile and sync preview workflow
- Backend APIs for subyards, kinship, timeline archive, travel plans, budget plans, gathering templates/checklists, recurring instances, announcements, chat rooms/messages, funds-travel overview, and Legacy Table settings
- Automated regression coverage for recurrence, announcements, chat, and the broader Digital Courtyard flows

## Prioritized Backlog
### P0
- Validate one full Stripe paid completion + webhook lifecycle end-to-end in sandbox
- Modularize oversized backend/server.py into domain routers/services
- Add editing/deletion flows for subyards, kinship relationships, budgets, travel plans, announcements, and messages

### P1
- Add relationship-group based invitation shortcuts and recurring gathering suggestions
- Add unread chat state, mention-style notifications, and richer announcement targeting
- Add advanced timeline filters/search/export and richer archive moderation controls
- Add external travel provider connections and live Legacy Table import/export once docs/credentials are available

### P2
- Multi-courtyard membership across separate parent communities
- Push notifications, SMS/email auth, and richer communications tooling
- Premium finance analytics, deeper travel booking logic, and partner ecosystem integrations

## Next Tasks
1. Complete Stripe paid-state verification in sandbox
2. Modularize backend domains for maintainability
3. Add edit/delete/admin flows for communications and courtyard objects
4. Add smarter unread indicators, relationship-based invitations, and gathering suggestions

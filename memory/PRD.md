# Gathering Cypher / Digital Courtyard PRD

## Original Problem Statement
Build “Gathering Cypher,” a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. Initial deliverables included an MVP app and strategy pack. Follow-up direction requested preserving the same color scheme and overall appearance while reshaping the product into a Digital Courtyard layout with courtyards/subyards, kinship mapping, smart gathering planning, timeline archive, shared funds/travel, and Legacy Table connection settings.

## User Choices
- Build both MVP app + strategy pack initially
- Initial MVP: invite-only email/password with Host, Organizer, Member roles; Events Hub, Memory Vault, Legacy Threads; Stripe contributions; voice-note memories + AI auto-tagging via Gemini using Emergent LLM key
- Follow-up expansion: implement UI + backend + as much working functionality as possible
- Rename/reshape current community concept into Courtyard + Subyards
- Build Courtyard features now and keep Legacy Table integration connection-ready until credentials/docs are provided
- Build deeper funds/travel with working travel coordination records, shared budgets, contribution tracking, and internal booking-style coordination

## Architecture Decisions
- Frontend remains React SPA with preserved warm visual system, updated primary navigation, and new Digital Courtyard information architecture
- Backend remains FastAPI + MongoDB for consistency with existing stack, expanding current community/event/archive model into courtyard/subyard, kinship, travel, budget, and settings APIs
- Legacy routes from the earlier MVP remain accessible for regression safety while primary nav shifts to Home, Courtyards, Timeline, Gatherings, Funds & Travel, and Settings
- Legacy Table is architected as a connection-ready integration layer with persisted config and sync preview counts pending real external API credentials/docs
- Stripe remains the contribution processor; Gemini-based AI tagging remains active for memories

## What’s Implemented
- Preserved existing color scheme/visual identity while redesigning the app around a Digital Courtyard IA
- New Home page with upcoming gatherings, active courtyards/subyards, quick actions, role catalog, and relationship/funding prompts
- Courtyards page with parent courtyard overview, subyard creation, role tool mapping, kinship relationship graph entries, member roster, and invite management
- Timeline page with unified archive feed, On This Day reminders, memory uploads, and story thread creation
- Gatherings page with template-based event creation, auto-generated checklists, role assignment, RSVP, agenda, volunteers, potluck, and travel coordination records
- Funds & Travel page with contribution packages, transaction ledger, event/family budgets, and travel overview
- Settings page with Legacy Table connection profile and sync preview workflow
- Backend APIs for subyards, kinship, timeline archive, travel plans, budget plans, gathering templates/checklists, funds-travel overview, and Legacy Table settings
- Expanded backend tests and frontend Playwright regression; core requested flows passed

## Prioritized Backlog
### P0
- Validate one full Stripe paid completion + webhook lifecycle end-to-end in sandbox
- Modularize oversized backend/server.py into domain routers/services
- Add editing/deletion flows for subyards, kinship relationships, budgets, and travel plans

### P1
- Add relationship-group based invitation shortcuts and recurring gathering suggestions
- Add advanced timeline filters/search/export and richer archive moderation controls
- Add external travel provider connections once credentials/docs are available
- Add live Legacy Table import/export once API docs/credentials are available

### P2
- Multi-courtyard membership across separate parent communities
- Push notifications, SMS/email auth, and richer communications tooling
- Premium finance analytics, deeper travel booking logic, and partner ecosystem integrations

## Next Tasks
1. Complete Stripe paid-state verification in sandbox
2. Modularize backend domains for maintainability
3. Add edit/delete/admin flows for newly introduced courtyard objects
4. Add smarter relationship-based invitations and gathering suggestions

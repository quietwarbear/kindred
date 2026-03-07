# Gathering Cypher PRD

## Original Problem Statement
Build “Gathering Cypher,” a private ecosystem for families, churches, and intentional communities to gather, plan, remember, and build. Requested outputs included both an MVP application and strategy materials: wireframe flow, brand naming concepts, venture pitch framing, feature prioritization roadmap, and competitive landscape analysis.

## User Choices
- Prioritize both MVP app build and strategy pack
- MVP scope: invite-only communities, role-based access, Events Hub, Memory Vault, Legacy Threads
- Access model: invite-only email/password with Host, Organizer, Member roles
- Contributions: Stripe integration
- AI/media: voice-note memories plus AI auto-tagging
- AI model: Gemini 3 Flash using Emergent LLM key

## Architecture Decisions
- Frontend: React + React Router SPA with a public landing page, auth flows, and protected app shell
- Backend: FastAPI monolith API with JWT auth, role checks, MongoDB collections, Stripe checkout/session status endpoints, and Gemini-based AI tag generation with graceful fallback
- Database collections: users, communities, invites, events, memories, threads, payment_transactions
- Media handling: photo/audio uploads are stored as data URLs for MVP simplicity, enabling direct rendering and lightweight archive workflows
- Strategy materials are embedded as a dedicated Strategy Deck page available publicly and within the app

## What’s Implemented
- Public landing page with community-first positioning and protected auth experience
- Host community bootstrap, login, invite-code registration, JWT session restore, role-aware app shell
- Events Hub with event creation, RSVP tracking, agenda builder, volunteer slots/signup, potluck coordination, map links, and event templates
- Memory Vault with event-linked uploads, voice-note support, AI tags/summary, and comments
- Legacy Threads with categories, voice reflections, and discussion replies
- Members page with invite creation and invite ledger
- Contributions page with Stripe checkout initiation, contribution packages, transaction ledger, and status polling
- Strategy Deck with wireframe flow, naming concepts, pitch framing, roadmap, and competitive analysis
- Automated backend regression tests plus frontend Playwright validation against the public preview URL

## Prioritized Backlog
### P0
- Validate full Stripe webhook paid-state completion flow end-to-end
- Split backend server.py into domain routers/services for maintainability
- Add richer permission controls for editing/removing invites, members, and content

### P1
- Add polls, anonymous suggestion box, and board/community decisions flows
- Add better media management (download controls, moderation, richer upload previews)
- Add community profile/settings management and custom branding controls

### P2
- Add scholarship pools, mentorship matching, documentary generation, reunion books, and broader institutional tooling
- Add archival search, filters, exports, and deeper analytics
- Add push notifications and recurring event workflows

## Next Tasks
1. Complete Stripe webhook simulation and paid-state confirmation UX
2. Modularize backend routes and services
3. Add polls/voting and anonymous suggestion functionality
4. Improve member admin controls and content moderation workflows

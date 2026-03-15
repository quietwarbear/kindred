"""
Backend Refactor Regression Tests - Iteration 15
Tests all major API endpoints after moving routes from server.py to modular route files

Test coverage:
- Auth routes (bootstrap, login, me)
- Community routes (overview, courtyard home/structure)
- Events routes (CRUD, RSVP)
- Communications routes (announcements, chat rooms, notifications)
- Polls routes (CRUD, voting)
- Subscriptions routes (plans, current, feature-check)
- Timeline routes (archive, memories)
- Finance routes (travel plans, budget plans, funds overview)
- Legacy routes (status)
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test user credentials provided for regression testing
TEST_EMAIL = "refactor-test@kindred.app"
TEST_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for test user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("token")
    pytest.skip(f"Authentication failed - status {response.status_code}: {response.text}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


# =============================================================================
# API Root and Health Check
# =============================================================================
class TestAPIHealth:
    """Test API root endpoint"""

    def test_api_root_returns_ready(self, api_client):
        """API root should return ready message"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "message" in data
        assert "ready" in data["message"].lower()
        print("✓ API root endpoint working")


# =============================================================================
# Auth Routes Tests
# =============================================================================
class TestAuthRoutes:
    """Test auth routes from routes/auth.py"""

    def test_login_success(self, api_client):
        """Login with valid credentials should return token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert "community" in data
        assert data["user"]["email"] == TEST_EMAIL
        print(f"✓ Login successful for {TEST_EMAIL}")

    def test_login_invalid_credentials(self, api_client):
        """Login with wrong password should return 401"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": "wrong-password"
        })
        assert response.status_code == 401
        print("✓ Login correctly rejects wrong password")

    def test_auth_me_requires_token(self, api_client):
        """GET /auth/me without token should return 401"""
        temp_client = requests.Session()
        temp_client.headers.update({"Content-Type": "application/json"})
        response = temp_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("✓ /auth/me correctly requires authentication")

    def test_auth_me_returns_user(self, authenticated_client):
        """GET /auth/me with valid token returns user data"""
        response = authenticated_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Auth me failed: {response.text}"
        data = response.json()
        assert "user" in data
        assert "community" in data
        assert data["user"]["email"] == TEST_EMAIL
        print("✓ /auth/me returns authenticated user data")


# =============================================================================
# Community Routes Tests
# =============================================================================
class TestCommunityRoutes:
    """Test community routes from routes/community.py"""

    def test_community_overview(self, authenticated_client):
        """GET /community/overview returns dashboard data"""
        response = authenticated_client.get(f"{BASE_URL}/api/community/overview")
        assert response.status_code == 200, f"Overview failed: {response.text}"
        data = response.json()
        assert "community" in data
        assert "stats" in data
        assert "upcoming_events" in data
        print("✓ Community overview endpoint working")

    def test_courtyard_home(self, authenticated_client):
        """GET /courtyard/home returns courtyard dashboard"""
        response = authenticated_client.get(f"{BASE_URL}/api/courtyard/home")
        assert response.status_code == 200, f"Courtyard home failed: {response.text}"
        data = response.json()
        assert "courtyard" in data
        assert "user" in data
        assert "stats" in data
        assert "upcoming_gatherings" in data
        assert "notifications" in data
        print("✓ Courtyard home endpoint working")

    def test_courtyard_structure(self, authenticated_client):
        """GET /courtyard/structure returns structure data"""
        response = authenticated_client.get(f"{BASE_URL}/api/courtyard/structure")
        assert response.status_code == 200, f"Structure failed: {response.text}"
        data = response.json()
        assert "courtyard" in data
        assert "subyards" in data
        assert "kinships" in data
        assert "members" in data
        assert "invites" in data
        print("✓ Courtyard structure endpoint working")

    def test_community_members_list(self, authenticated_client):
        """GET /community/members returns member list"""
        response = authenticated_client.get(f"{BASE_URL}/api/community/members")
        assert response.status_code == 200, f"Members list failed: {response.text}"
        data = response.json()
        assert "members" in data
        assert isinstance(data["members"], list)
        print("✓ Community members list endpoint working")


# =============================================================================
# Events Routes Tests
# =============================================================================
class TestEventsRoutes:
    """Test events routes from routes/events.py"""

    def test_list_events(self, authenticated_client):
        """GET /events returns list of events"""
        response = authenticated_client.get(f"{BASE_URL}/api/events")
        assert response.status_code == 200, f"Events list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Events list working ({len(data)} events found)")

    def test_create_event(self, authenticated_client):
        """POST /events creates new event"""
        event_data = {
            "title": f"TEST_Refactor_Event_{uuid.uuid4().hex[:6]}",
            "description": "Test event for refactor regression",
            "start_at": "2026-06-15T14:00:00Z",
            "location": "Test Location",
            "event_template": "custom",
            "gathering_format": "in-person",
            "max_attendees": 50,
            "recurrence_frequency": "none"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/events", json=event_data)
        assert response.status_code == 200, f"Create event failed: {response.text}"
        data = response.json()
        assert data["title"] == event_data["title"]
        assert "id" in data
        print(f"✓ Event created: {data['id']}")
        return data["id"]

    def test_rsvp_to_event(self, authenticated_client):
        """POST /events/{id}/rsvp updates RSVP status"""
        # First get events list to find one
        events_response = authenticated_client.get(f"{BASE_URL}/api/events")
        events = events_response.json()
        if not events:
            pytest.skip("No events available for RSVP test")
        
        event_id = events[0]["id"]
        rsvp_data = {"status": "going"}
        response = authenticated_client.post(f"{BASE_URL}/api/events/{event_id}/rsvp", json=rsvp_data)
        assert response.status_code == 200, f"RSVP failed: {response.text}"
        data = response.json()
        assert "rsvp_records" in data
        print(f"✓ RSVP to event {event_id} working")

    def test_gathering_templates(self, authenticated_client):
        """GET /gatherings/templates returns template list"""
        response = authenticated_client.get(f"{BASE_URL}/api/gatherings/templates")
        assert response.status_code == 200, f"Templates failed: {response.text}"
        data = response.json()
        assert "templates" in data
        assert len(data["templates"]) > 0
        print(f"✓ Gathering templates working ({len(data['templates'])} templates)")


# =============================================================================
# Communications Routes Tests
# =============================================================================
class TestCommunicationsRoutes:
    """Test communications routes from routes/communications.py"""

    def test_list_announcements(self, authenticated_client):
        """GET /announcements returns list"""
        response = authenticated_client.get(f"{BASE_URL}/api/announcements")
        assert response.status_code == 200, f"Announcements list failed: {response.text}"
        data = response.json()
        assert "announcements" in data
        print(f"✓ Announcements list working ({len(data['announcements'])} found)")

    def test_create_announcement(self, authenticated_client):
        """POST /announcements creates new announcement"""
        announcement_data = {
            "title": f"TEST_Refactor_Announcement_{uuid.uuid4().hex[:6]}",
            "body": "Test announcement for refactor regression",
            "scope": "courtyard",
            "subyard_id": "",
            "attachments": []
        }
        response = authenticated_client.post(f"{BASE_URL}/api/announcements", json=announcement_data)
        assert response.status_code == 200, f"Create announcement failed: {response.text}"
        data = response.json()
        assert data["title"] == announcement_data["title"]
        assert "id" in data
        print(f"✓ Announcement created: {data['id']}")

    def test_chat_rooms_list(self, authenticated_client):
        """GET /chat/rooms returns chat rooms"""
        response = authenticated_client.get(f"{BASE_URL}/api/chat/rooms")
        assert response.status_code == 200, f"Chat rooms failed: {response.text}"
        data = response.json()
        assert "rooms" in data
        print(f"✓ Chat rooms list working ({len(data['rooms'])} rooms)")

    def test_notifications_history(self, authenticated_client):
        """GET /notifications/history returns notification history"""
        response = authenticated_client.get(f"{BASE_URL}/api/notifications/history")
        assert response.status_code == 200, f"Notifications history failed: {response.text}"
        data = response.json()
        assert "items" in data
        print(f"✓ Notifications history working ({len(data['items'])} items)")

    def test_notifications_unread_count(self, authenticated_client):
        """GET /notifications/unread-count returns count"""
        response = authenticated_client.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 200, f"Unread count failed: {response.text}"
        data = response.json()
        assert "unread_count" in data
        print(f"✓ Notifications unread count: {data['unread_count']}")


# =============================================================================
# Polls Routes Tests
# =============================================================================
class TestPollsRoutes:
    """Test polls routes from routes/polls.py"""

    def test_list_polls(self, authenticated_client):
        """GET /polls returns list of polls"""
        response = authenticated_client.get(f"{BASE_URL}/api/polls")
        assert response.status_code == 200, f"Polls list failed: {response.text}"
        data = response.json()
        assert "polls" in data
        print(f"✓ Polls list working ({len(data['polls'])} polls found)")

    def test_create_poll(self, authenticated_client):
        """POST /polls creates new poll"""
        poll_data = {
            "title": f"TEST_Refactor_Poll_{uuid.uuid4().hex[:6]}",
            "description": "Test poll for refactor regression",
            "options": [
                {"text": "Option A"},
                {"text": "Option B"}
            ],
            "allow_multiple": False,
            "closes_at": ""
        }
        response = authenticated_client.post(f"{BASE_URL}/api/polls", json=poll_data)
        assert response.status_code == 200, f"Create poll failed: {response.text}"
        data = response.json()
        assert data["title"] == poll_data["title"]
        assert "id" in data
        assert len(data["options"]) == 2
        print(f"✓ Poll created: {data['id']}")
        return data

    def test_vote_on_poll(self, authenticated_client):
        """POST /polls/{id}/vote casts vote"""
        # First create a poll
        poll_data = {
            "title": f"TEST_Vote_Poll_{uuid.uuid4().hex[:6]}",
            "description": "Poll for vote testing",
            "options": [
                {"text": "Yes"},
                {"text": "No"}
            ],
            "allow_multiple": False
        }
        create_response = authenticated_client.post(f"{BASE_URL}/api/polls", json=poll_data)
        assert create_response.status_code == 200
        poll = create_response.json()
        
        # Vote on the poll
        option_id = poll["options"][0]["id"]
        vote_data = {"option_ids": [option_id]}
        response = authenticated_client.post(f"{BASE_URL}/api/polls/{poll['id']}/vote", json=vote_data)
        assert response.status_code == 200, f"Vote failed: {response.text}"
        data = response.json()
        assert data["options"][0]["vote_count"] == 1
        print(f"✓ Vote on poll {poll['id']} working")


# =============================================================================
# Subscriptions Routes Tests
# =============================================================================
class TestSubscriptionsRoutes:
    """Test subscriptions routes from routes/subscriptions.py"""

    def test_subscription_plans(self, api_client):
        """GET /subscriptions/plans returns available plans (no auth required)"""
        response = api_client.get(f"{BASE_URL}/api/subscriptions/plans")
        assert response.status_code == 200, f"Plans failed: {response.text}"
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) == 5  # seedling, sapling, oak, redwood, elder-grove
        plan_ids = [p["id"] for p in data["plans"]]
        assert "seedling" in plan_ids
        assert "elder-grove" in plan_ids
        print(f"✓ Subscription plans working ({len(data['plans'])} plans)")

    def test_current_subscription(self, authenticated_client):
        """GET /subscriptions/current returns current tier"""
        response = authenticated_client.get(f"{BASE_URL}/api/subscriptions/current")
        assert response.status_code == 200, f"Current subscription failed: {response.text}"
        data = response.json()
        assert "tier" in data
        assert "usage" in data
        print(f"✓ Current subscription: {data['tier']['name']}")

    def test_feature_check(self, authenticated_client):
        """GET /subscriptions/feature-check/{feature} checks feature access"""
        response = authenticated_client.get(f"{BASE_URL}/api/subscriptions/feature-check/travel_coordination")
        assert response.status_code == 200, f"Feature check failed: {response.text}"
        data = response.json()
        assert "feature_key" in data
        assert "allowed" in data
        assert "tier_id" in data
        print(f"✓ Feature check working: travel_coordination={data['allowed']}")


# =============================================================================
# Timeline Routes Tests
# =============================================================================
class TestTimelineRoutes:
    """Test timeline routes from routes/timeline.py"""

    def test_timeline_archive(self, authenticated_client):
        """GET /timeline/archive returns timeline items"""
        response = authenticated_client.get(f"{BASE_URL}/api/timeline/archive")
        assert response.status_code == 200, f"Archive failed: {response.text}"
        data = response.json()
        assert "timeline_items" in data
        assert "on_this_day" in data
        print(f"✓ Timeline archive working ({len(data['timeline_items'])} items)")

    def test_list_memories(self, authenticated_client):
        """GET /memories returns memory list"""
        response = authenticated_client.get(f"{BASE_URL}/api/memories")
        assert response.status_code == 200, f"Memories list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Memories list working ({len(data)} memories)")

    def test_create_memory(self, authenticated_client):
        """POST /memories creates new memory"""
        memory_data = {
            "title": f"TEST_Refactor_Memory_{uuid.uuid4().hex[:6]}",
            "description": "Test memory for refactor regression",
            "event_id": "",
            "category": "photo",
            "image_data_url": "",
            "voice_note_data_url": "",
            "tags": ["test", "regression"]
        }
        response = authenticated_client.post(f"{BASE_URL}/api/memories", json=memory_data)
        assert response.status_code == 200, f"Create memory failed: {response.text}"
        data = response.json()
        assert data["title"] == memory_data["title"]
        assert "id" in data
        print(f"✓ Memory created: {data['id']}")


# =============================================================================
# Finance Routes Tests
# =============================================================================
class TestFinanceRoutes:
    """Test finance routes from routes/finance.py"""

    def test_travel_plans_list(self, authenticated_client):
        """GET /travel-plans returns list"""
        response = authenticated_client.get(f"{BASE_URL}/api/travel-plans")
        assert response.status_code == 200, f"Travel plans failed: {response.text}"
        data = response.json()
        assert "travel_plans" in data
        print(f"✓ Travel plans list working ({len(data['travel_plans'])} plans)")

    def test_create_travel_plan(self, authenticated_client):
        """POST /travel-plans creates new plan"""
        plan_data = {
            "event_id": "",
            "title": f"TEST_Travel_{uuid.uuid4().hex[:6]}",
            "travel_type": "driving",
            "details": "Test travel plan",
            "coordinator_name": "",
            "amount_estimate": 100.0,
            "payment_status": "pending",
            "seats_available": 4,
            "traveler_name": "",
            "mode": "driving",
            "origin": "Test City",
            "departure_at": "2026-06-14T08:00:00Z",
            "arrival_at": "2026-06-15T12:00:00Z",
            "notes": "Regression test",
            "estimated_cost": 100.0
        }
        response = authenticated_client.post(f"{BASE_URL}/api/travel-plans", json=plan_data)
        assert response.status_code == 200, f"Create travel plan failed: {response.text}"
        data = response.json()
        assert "id" in data
        print(f"✓ Travel plan created: {data['id']}")

    def test_budget_plans_list(self, authenticated_client):
        """GET /budget-plans returns list"""
        response = authenticated_client.get(f"{BASE_URL}/api/budget-plans")
        assert response.status_code == 200, f"Budget plans failed: {response.text}"
        data = response.json()
        assert "budgets" in data
        print(f"✓ Budget plans list working ({len(data['budgets'])} budgets)")

    def test_create_budget_plan(self, authenticated_client):
        """POST /budget-plans creates new budget"""
        budget_data = {
            "title": f"TEST_Budget_{uuid.uuid4().hex[:6]}",
            "target_amount": 500.0,
            "current_amount": 0.0,
            "suggested_contribution": 25.0,
            "budget_type": "event",
            "event_id": "",
            "notes": "Regression test budget",
            "line_items": []
        }
        response = authenticated_client.post(f"{BASE_URL}/api/budget-plans", json=budget_data)
        assert response.status_code == 200, f"Create budget failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["title"] == budget_data["title"]
        print(f"✓ Budget plan created: {data['id']}")

    def test_funds_travel_overview(self, authenticated_client):
        """GET /funds-travel/overview returns combined data"""
        response = authenticated_client.get(f"{BASE_URL}/api/funds-travel/overview")
        assert response.status_code == 200, f"Overview failed: {response.text}"
        data = response.json()
        assert "budgets" in data
        assert "travel_plans" in data
        assert "packages" in data
        print("✓ Funds-travel overview working")


# =============================================================================
# Legacy Routes Tests
# =============================================================================
class TestLegacyRoutes:
    """Test legacy routes from routes/legacy.py"""

    def test_legacy_table_status(self, authenticated_client):
        """GET /legacy-table/status returns connection status"""
        response = authenticated_client.get(f"{BASE_URL}/api/legacy-table/status")
        assert response.status_code == 200, f"Legacy status failed: {response.text}"
        data = response.json()
        assert "connection_status" in data
        assert "capabilities" in data
        print(f"✓ Legacy table status: {data['connection_status']}")


# =============================================================================
# Invites Routes Tests
# =============================================================================
class TestInvitesRoutes:
    """Test invite routes"""

    def test_list_invites(self, authenticated_client):
        """GET /invites returns invite list"""
        response = authenticated_client.get(f"{BASE_URL}/api/invites")
        assert response.status_code == 200, f"Invites list failed: {response.text}"
        data = response.json()
        assert "invites" in data
        print(f"✓ Invites list working ({len(data['invites'])} invites)")

    def test_create_invite(self, authenticated_client):
        """POST /invites creates new invite"""
        invite_data = {
            "email": f"test-invite-{uuid.uuid4().hex[:6]}@test.com",
            "role": "member",
            "subyard_id": ""
        }
        response = authenticated_client.post(f"{BASE_URL}/api/invites", json=invite_data)
        assert response.status_code == 200, f"Create invite failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert "code" in data
        assert data["email"] == invite_data["email"]
        print(f"✓ Invite created: {data['code']}")


# =============================================================================
# Subyards and Kinship Routes Tests
# =============================================================================
class TestSubyardsKinshipRoutes:
    """Test subyards and kinship routes"""

    def test_list_subyards(self, authenticated_client):
        """GET /subyards returns subyard list"""
        response = authenticated_client.get(f"{BASE_URL}/api/subyards")
        assert response.status_code == 200, f"Subyards list failed: {response.text}"
        data = response.json()
        assert "subyards" in data
        print(f"✓ Subyards list working ({len(data['subyards'])} subyards)")

    def test_list_kinship(self, authenticated_client):
        """GET /kinship returns kinship relationships"""
        response = authenticated_client.get(f"{BASE_URL}/api/kinship")
        assert response.status_code == 200, f"Kinship list failed: {response.text}"
        data = response.json()
        assert "relationships" in data
        print(f"✓ Kinship list working ({len(data['relationships'])} relationships)")


# =============================================================================
# Cleanup - Delete TEST_ prefixed data
# =============================================================================
class TestCleanup:
    """Cleanup test data created during regression tests"""

    def test_cleanup_test_data(self, authenticated_client):
        """Remove TEST_ prefixed test data"""
        cleanup_counts = {
            "events": 0,
            "announcements": 0,
            "polls": 0,
            "memories": 0,
            "travel_plans": 0,
            "budget_plans": 0
        }

        # Cleanup events
        events_response = authenticated_client.get(f"{BASE_URL}/api/events")
        if events_response.status_code == 200:
            events = events_response.json()
            for event in events:
                if event.get("title", "").startswith("TEST_"):
                    # Note: No direct delete endpoint for events, but they're test data
                    cleanup_counts["events"] += 1

        # Cleanup announcements
        announcements_response = authenticated_client.get(f"{BASE_URL}/api/announcements")
        if announcements_response.status_code == 200:
            announcements = announcements_response.json().get("announcements", [])
            for ann in announcements:
                if ann.get("title", "").startswith("TEST_"):
                    delete_resp = authenticated_client.delete(f"{BASE_URL}/api/announcements/{ann['id']}")
                    if delete_resp.status_code == 200:
                        cleanup_counts["announcements"] += 1

        # Cleanup polls
        polls_response = authenticated_client.get(f"{BASE_URL}/api/polls")
        if polls_response.status_code == 200:
            polls = polls_response.json().get("polls", [])
            for poll in polls:
                if poll.get("title", "").startswith("TEST_"):
                    delete_resp = authenticated_client.delete(f"{BASE_URL}/api/polls/{poll['id']}")
                    if delete_resp.status_code == 200:
                        cleanup_counts["polls"] += 1

        # Cleanup travel plans
        travel_response = authenticated_client.get(f"{BASE_URL}/api/travel-plans")
        if travel_response.status_code == 200:
            plans = travel_response.json().get("travel_plans", [])
            for plan in plans:
                if plan.get("title", "").startswith("TEST_"):
                    delete_resp = authenticated_client.delete(f"{BASE_URL}/api/travel-plans/{plan['id']}")
                    if delete_resp.status_code == 200:
                        cleanup_counts["travel_plans"] += 1

        # Cleanup budget plans
        budget_response = authenticated_client.get(f"{BASE_URL}/api/budget-plans")
        if budget_response.status_code == 200:
            budgets = budget_response.json().get("budgets", [])
            for budget in budgets:
                if budget.get("title", "").startswith("TEST_"):
                    delete_resp = authenticated_client.delete(f"{BASE_URL}/api/budget-plans/{budget['id']}")
                    if delete_resp.status_code == 200:
                        cleanup_counts["budget_plans"] += 1

        print(f"✓ Cleanup completed: {cleanup_counts}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

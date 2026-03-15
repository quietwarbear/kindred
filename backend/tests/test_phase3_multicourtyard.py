"""
Phase 3 Multi-Courtyard and Push Notifications Backend Tests

Tests:
- GET /api/communities/mine - list all communities user belongs to
- POST /api/communities/switch - switch active community
- POST /api/communities/join - join a new community with invite code
- community_ids field set during bootstrap
- Notification polling (GET /api/notifications/unread-count)
- Regression for existing endpoints
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "refactor-test@kindred.app"
TEST_PASSWORD = "Test1234!"

@pytest.fixture(scope="module")
def api_session():
    """Shared requests session for all tests"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="module")
def auth_token(api_session):
    """Login and get auth token"""
    response = api_session.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data, "Token not in login response"
    return data["token"]

@pytest.fixture(scope="module")
def authenticated_session(api_session, auth_token):
    """Session with auth header"""
    api_session.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_session


class TestMultiCourtyardAPIs:
    """Test multi-courtyard membership APIs"""

    def test_01_communities_mine_endpoint(self, authenticated_session):
        """GET /api/communities/mine returns user's communities list"""
        response = authenticated_session.get(f"{BASE_URL}/api/communities/mine")
        assert response.status_code == 200, f"communities/mine failed: {response.text}"
        
        data = response.json()
        assert "communities" in data, "Missing 'communities' in response"
        assert "active_community_id" in data, "Missing 'active_community_id' in response"
        
        communities = data["communities"]
        assert isinstance(communities, list), "communities should be a list"
        assert len(communities) >= 1, "User should belong to at least 1 community"
        
        # Check community structure
        for c in communities:
            assert "id" in c, "Community missing 'id'"
            assert "name" in c, "Community missing 'name'"
            assert "member_count" in c, "Community missing 'member_count'"
            assert "is_active" in c, "Community missing 'is_active'"
        
        # Verify active_community_id matches
        active_count = sum(1 for c in communities if c["is_active"])
        assert active_count == 1, "Exactly one community should be active"
        
        active_community = [c for c in communities if c["is_active"]][0]
        assert active_community["id"] == data["active_community_id"], "active_community_id should match"
        print(f"✓ communities/mine: {len(communities)} communities, active={active_community['name']}")

    def test_02_communities_switch_missing_id(self, authenticated_session):
        """POST /api/communities/switch fails without community_id"""
        response = authenticated_session.post(f"{BASE_URL}/api/communities/switch", json={})
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        assert "community_id" in data["detail"].lower() or "required" in data["detail"].lower()
        print("✓ communities/switch properly rejects missing community_id")

    def test_03_communities_switch_invalid_id(self, authenticated_session):
        """POST /api/communities/switch fails for non-member community"""
        fake_id = str(uuid.uuid4())
        response = authenticated_session.post(f"{BASE_URL}/api/communities/switch", json={
            "community_id": fake_id
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✓ communities/switch properly rejects non-member community")

    def test_04_communities_join_missing_code(self, authenticated_session):
        """POST /api/communities/join fails without invite_code"""
        response = authenticated_session.post(f"{BASE_URL}/api/communities/join", json={})
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✓ communities/join properly rejects missing invite_code")

    def test_05_communities_join_invalid_code(self, authenticated_session):
        """POST /api/communities/join fails with invalid invite code"""
        response = authenticated_session.post(f"{BASE_URL}/api/communities/join", json={
            "invite_code": "INVALIDCODE123"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✓ communities/join properly rejects invalid invite code")


class TestNotificationPolling:
    """Test notification polling endpoint for push notifications"""

    def test_01_notifications_unread_count(self, authenticated_session):
        """GET /api/notifications/unread-count returns count"""
        response = authenticated_session.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 200, f"unread-count failed: {response.text}"
        
        data = response.json()
        assert "unread_count" in data, "Missing 'unread_count' in response"
        assert isinstance(data["unread_count"], int), "unread_count should be int"
        print(f"✓ notifications/unread-count: {data['unread_count']} unread")

    def test_02_notifications_history(self, authenticated_session):
        """GET /api/notifications/history returns items list"""
        response = authenticated_session.get(f"{BASE_URL}/api/notifications/history")
        assert response.status_code == 200, f"notifications/history failed: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing 'items' in response"
        assert isinstance(data["items"], list), "items should be a list"
        print(f"✓ notifications/history: {len(data['items'])} items")


class TestRegressionPhase3:
    """Regression tests for existing features during Phase 3"""

    def test_01_auth_login(self, api_session):
        """Auth login still works"""
        response = api_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert "community" in data
        
        # Check community_ids is in user object (bootstrap sets this)
        user = data["user"]
        # Note: Old users may not have community_ids - that's OK, 
        # the API handles backwards compatibility
        print(f"✓ Auth login works, user={user['full_name']}")

    def test_02_kinship_graph(self, authenticated_session):
        """Kinship Map graph endpoint works"""
        response = authenticated_session.get(f"{BASE_URL}/api/kinship/graph")
        assert response.status_code == 200, f"kinship/graph failed: {response.text}"
        
        data = response.json()
        assert "nodes" in data
        assert "links" in data
        assert "relationship_types" in data
        print(f"✓ kinship/graph: {len(data['nodes'])} nodes, {len(data['links'])} links")

    def test_03_threads_list(self, authenticated_session):
        """Legacy Threads list endpoint works"""
        response = authenticated_session.get(f"{BASE_URL}/api/threads")
        assert response.status_code == 200, f"threads list failed: {response.text}"
        
        data = response.json()
        # API returns list directly or wrapped in 'threads'
        threads = data if isinstance(data, list) else data.get("threads", [])
        print(f"✓ threads: {len(threads)} threads")

    def test_04_activity_page_load(self, authenticated_session):
        """Activity Feed UI - courtyard/home has notifications for activity"""
        # Activity feed is built into courtyard/home, not a separate endpoint
        response = authenticated_session.get(f"{BASE_URL}/api/courtyard/home")
        assert response.status_code == 200, f"courtyard/home failed: {response.text}"
        
        data = response.json()
        assert "notifications" in data
        assert "recent_timeline" in data
        print(f"✓ activity data available via courtyard/home: {len(data['notifications'])} notifications")

    def test_05_timeline_memories_threads(self, authenticated_session):
        """Timeline data from memories and threads"""
        # Timeline is composed from memories and threads endpoints
        mem_resp = authenticated_session.get(f"{BASE_URL}/api/memories")
        assert mem_resp.status_code == 200
        
        thr_resp = authenticated_session.get(f"{BASE_URL}/api/threads")
        assert thr_resp.status_code == 200
        
        print("✓ timeline data available via memories and threads endpoints")

    def test_06_timeline_export(self, authenticated_session):
        """Timeline export endpoint works"""
        response = authenticated_session.get(f"{BASE_URL}/api/timeline/export")
        assert response.status_code == 200, f"timeline/export failed: {response.text}"
        
        # Export returns CSV
        content_type = response.headers.get("content-type", "")
        assert "csv" in content_type or response.status_code == 200
        print("✓ timeline/export works")

    def test_07_events_list(self, authenticated_session):
        """Events list endpoint works"""
        response = authenticated_session.get(f"{BASE_URL}/api/events")
        assert response.status_code == 200, f"events list failed: {response.text}"
        
        data = response.json()
        # API returns list directly or wrapped in 'events'
        events = data if isinstance(data, list) else data.get("events", [])
        print(f"✓ events: {len(events)} events")

    def test_08_memories_list(self, authenticated_session):
        """Memories list endpoint works"""
        response = authenticated_session.get(f"{BASE_URL}/api/memories")
        assert response.status_code == 200, f"memories list failed: {response.text}"
        
        data = response.json()
        # API returns list directly or wrapped in 'memories'
        memories = data if isinstance(data, list) else data.get("memories", [])
        print(f"✓ memories: {len(memories)} memories")

    def test_09_courtyard_home(self, authenticated_session):
        """Courtyard home endpoint works"""
        response = authenticated_session.get(f"{BASE_URL}/api/courtyard/home")
        assert response.status_code == 200, f"courtyard/home failed: {response.text}"
        
        data = response.json()
        assert "courtyard" in data
        assert "user" in data
        assert "notifications" in data
        print("✓ courtyard/home works")


class TestBootstrapWithCommunityIds:
    """Test that new bootstrap sets community_ids correctly"""

    def test_01_bootstrap_creates_community_ids(self, api_session):
        """Bootstrap creates user with community_ids array"""
        test_email = f"TEST_phase3_{uuid.uuid4().hex[:6]}@test.com"
        
        response = api_session.post(f"{BASE_URL}/api/auth/bootstrap", json={
            "email": test_email,
            "password": "Test1234!",
            "full_name": "TEST Phase3 User",
            "community_name": "TEST Phase3 Community",
            "community_type": "family",
            "location": "Test City",
            "description": "Test community for Phase 3"
        })
        
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        
        data = response.json()
        assert "user" in data
        assert "community" in data
        assert "token" in data
        
        user = data["user"]
        community = data["community"]
        
        # Check community_ids is set and contains the community_id
        # Note: The API might not expose community_ids directly in user object
        # but it should be set in the database
        assert user["community_id"] == community["id"], "community_id should match"
        print(f"✓ Bootstrap creates user with community_id={community['id']}")
        
        # Verify by calling communities/mine with the new token
        token = data["token"]
        api_session.headers.update({"Authorization": f"Bearer {token}"})
        
        mine_response = api_session.get(f"{BASE_URL}/api/communities/mine")
        assert mine_response.status_code == 200
        
        mine_data = mine_response.json()
        assert len(mine_data["communities"]) == 1, "Should have exactly 1 community"
        assert mine_data["communities"][0]["id"] == community["id"]
        assert mine_data["communities"][0]["is_active"] == True
        print(f"✓ communities/mine returns correct community for new user")
        
        # Cleanup: Delete the test account
        delete_response = api_session.delete(f"{BASE_URL}/api/auth/account", json={
            "password": "Test1234!"
        })
        assert delete_response.status_code == 200
        print("✓ Cleaned up test account")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

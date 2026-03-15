"""
Phase 1 Features Test Suite
Tests for:
- Activity Feed (GET /api/activity-feed)
- Event inline editing (PUT /api/events/{event_id})
- Event deletion (DELETE /api/events/{event_id})
- Memory inline editing (PUT /api/memories/{memory_id})
- Memory deletion (DELETE /api/memories/{memory_id})
- Timeline CSV export (GET /api/timeline/export?format=csv)
- Kinship groups (GET /api/kinship/groups)
- Regression tests for auth, polls, subscriptions, announcements
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL environment variable must be set"


class TestAuthentication:
    """Auth tests and token retrieval"""

    @pytest.fixture(scope="class")
    def auth_data(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        return data

    def test_login_success(self, auth_data):
        """Verify login returns token and user data"""
        assert "token" in auth_data
        assert "user" in auth_data
        assert auth_data["user"]["email"] == "refactor-test@kindred.app"
        assert auth_data["user"]["role"] == "host"

    def test_auth_me_endpoint(self, auth_data):
        """Verify /api/auth/me returns authenticated user"""
        token = auth_data["token"]
        response = requests.get(f"{BASE_URL}/api/auth/me", 
                                headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "refactor-test@kindred.app"


class TestActivityFeed:
    """Activity Feed feature tests"""

    @pytest.fixture(scope="class")
    def token(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        return response.json()["token"]

    def test_activity_feed_returns_paginated_data(self, token):
        """GET /api/activity-feed returns paginated feed items"""
        response = requests.get(f"{BASE_URL}/api/activity-feed",
                                headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        
        # Check pagination structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert "event_types" in data
        assert "community_member_count" in data
        
        # Verify data types
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["page"], int)
        assert isinstance(data["event_types"], list)
        
        print(f"Activity feed has {data['total']} total items, {len(data['items'])} on page {data['page']}")

    def test_activity_feed_pagination(self, token):
        """GET /api/activity-feed supports pagination"""
        response = requests.get(f"{BASE_URL}/api/activity-feed?page=1&page_size=5",
                                headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["items"]) <= 5

    def test_activity_feed_filter_by_type(self, token):
        """GET /api/activity-feed supports event_type filter"""
        # First get available event types
        response = requests.get(f"{BASE_URL}/api/activity-feed",
                                headers={"Authorization": f"Bearer {token}"})
        data = response.json()
        
        if data["event_types"]:
            event_type = data["event_types"][0]
            filtered_response = requests.get(
                f"{BASE_URL}/api/activity-feed?event_type={event_type}",
                headers={"Authorization": f"Bearer {token}"})
            assert filtered_response.status_code == 200
            filtered_data = filtered_response.json()
            
            # All items should match the filter
            for item in filtered_data["items"]:
                assert item["event_type"] == event_type
            print(f"Filter by '{event_type}' returned {len(filtered_data['items'])} items")

    def test_activity_feed_item_structure(self, token):
        """Activity feed items have correct structure"""
        response = requests.get(f"{BASE_URL}/api/activity-feed",
                                headers={"Authorization": f"Bearer {token}"})
        data = response.json()
        
        if data["items"]:
            item = data["items"][0]
            # Check expected fields
            assert "id" in item
            assert "event_type" in item
            assert "title" in item
            assert "description" in item
            assert "created_at" in item
            assert "actor_name" in item
            assert "is_read" in item


class TestEventInlineEditing:
    """Event (Gathering) inline editing and deletion tests"""

    @pytest.fixture(scope="class")
    def session_data(self):
        """Get auth token and create test event"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        token = login_response.json()["token"]
        
        # Create a test event
        event_payload = {
            "title": "TEST_Phase1_Event",
            "description": "Test event for Phase 1 testing",
            "start_at": "2026-12-25T14:00:00Z",
            "location": "Test Location",
            "event_template": "reunion",
            "gathering_format": "in-person",
            "max_attendees": 50,
            "recurrence_frequency": "none"
        }
        create_response = requests.post(f"{BASE_URL}/api/events",
                                        headers={"Authorization": f"Bearer {token}"},
                                        json=event_payload)
        assert create_response.status_code == 200, f"Event creation failed: {create_response.text}"
        event = create_response.json()
        
        return {"token": token, "event_id": event["id"], "event": event}

    def test_event_update_title(self, session_data):
        """PUT /api/events/{id} updates event title"""
        token = session_data["token"]
        event_id = session_data["event_id"]
        
        update_payload = {
            "title": "TEST_Phase1_Event_Updated"
        }
        response = requests.put(f"{BASE_URL}/api/events/{event_id}",
                               headers={"Authorization": f"Bearer {token}"},
                               json=update_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Phase1_Event_Updated"

    def test_event_update_multiple_fields(self, session_data):
        """PUT /api/events/{id} updates multiple fields"""
        token = session_data["token"]
        event_id = session_data["event_id"]
        
        update_payload = {
            "title": "TEST_Phase1_Event_Multi_Update",
            "description": "Updated description",
            "location": "Updated Location",
            "gathering_format": "hybrid"
        }
        response = requests.put(f"{BASE_URL}/api/events/{event_id}",
                               headers={"Authorization": f"Bearer {token}"},
                               json=update_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Phase1_Event_Multi_Update"
        assert data["description"] == "Updated description"
        assert data["location"] == "Updated Location"
        assert data["gathering_format"] == "hybrid"

    def test_event_verify_persistence(self, session_data):
        """GET /api/events returns updated event data"""
        token = session_data["token"]
        event_id = session_data["event_id"]
        
        response = requests.get(f"{BASE_URL}/api/events",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        events = response.json()
        
        # Find our test event
        test_event = next((e for e in events if e["id"] == event_id), None)
        assert test_event is not None
        assert test_event["title"] == "TEST_Phase1_Event_Multi_Update"

    def test_event_delete(self, session_data):
        """DELETE /api/events/{id} removes event"""
        token = session_data["token"]
        event_id = session_data["event_id"]
        
        response = requests.delete(f"{BASE_URL}/api/events/{event_id}",
                                   headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_event_delete_verification(self, session_data):
        """Verify deleted event no longer exists"""
        token = session_data["token"]
        event_id = session_data["event_id"]
        
        response = requests.get(f"{BASE_URL}/api/events",
                               headers={"Authorization": f"Bearer {token}"})
        events = response.json()
        
        # Event should no longer exist
        test_event = next((e for e in events if e["id"] == event_id), None)
        assert test_event is None, "Deleted event should not appear in list"


class TestMemoryInlineEditing:
    """Memory inline editing and deletion tests"""

    @pytest.fixture(scope="class")
    def memory_session(self):
        """Get auth token, create test event, and create test memory"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        token = login_response.json()["token"]
        
        # Create a test event first (memories need event_id)
        event_payload = {
            "title": "TEST_Memory_Event",
            "description": "Event for memory testing",
            "start_at": "2026-12-26T14:00:00Z",
            "location": "Memory Test Location",
            "event_template": "reunion",
            "gathering_format": "in-person",
            "max_attendees": 50,
            "recurrence_frequency": "none"
        }
        event_response = requests.post(f"{BASE_URL}/api/events",
                                       headers={"Authorization": f"Bearer {token}"},
                                       json=event_payload)
        event = event_response.json()
        
        # Create a test memory
        memory_payload = {
            "title": "TEST_Phase1_Memory",
            "description": "Test memory for Phase 1 testing",
            "event_id": event["id"],
            "tags": ["test", "phase1"]
        }
        memory_response = requests.post(f"{BASE_URL}/api/memories",
                                        headers={"Authorization": f"Bearer {token}"},
                                        json=memory_payload)
        assert memory_response.status_code == 200, f"Memory creation failed: {memory_response.text}"
        memory = memory_response.json()
        
        return {"token": token, "memory_id": memory["id"], "event_id": event["id"]}

    def test_memory_update_title(self, memory_session):
        """PUT /api/memories/{id} updates memory title"""
        token = memory_session["token"]
        memory_id = memory_session["memory_id"]
        
        update_payload = {
            "title": "TEST_Phase1_Memory_Updated"
        }
        response = requests.put(f"{BASE_URL}/api/memories/{memory_id}",
                               headers={"Authorization": f"Bearer {token}"},
                               json=update_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Phase1_Memory_Updated"

    def test_memory_update_description(self, memory_session):
        """PUT /api/memories/{id} updates memory description"""
        token = memory_session["token"]
        memory_id = memory_session["memory_id"]
        
        update_payload = {
            "title": "TEST_Phase1_Memory_Updated",
            "description": "Updated memory description"
        }
        response = requests.put(f"{BASE_URL}/api/memories/{memory_id}",
                               headers={"Authorization": f"Bearer {token}"},
                               json=update_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated memory description"

    def test_memory_verify_persistence(self, memory_session):
        """GET /api/memories returns updated memory data"""
        token = memory_session["token"]
        memory_id = memory_session["memory_id"]
        
        response = requests.get(f"{BASE_URL}/api/memories",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        memories = response.json()
        
        test_memory = next((m for m in memories if m["id"] == memory_id), None)
        assert test_memory is not None
        assert test_memory["title"] == "TEST_Phase1_Memory_Updated"

    def test_memory_delete(self, memory_session):
        """DELETE /api/memories/{id} removes memory"""
        token = memory_session["token"]
        memory_id = memory_session["memory_id"]
        
        response = requests.delete(f"{BASE_URL}/api/memories/{memory_id}",
                                   headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_memory_delete_verification(self, memory_session):
        """Verify deleted memory no longer exists"""
        token = memory_session["token"]
        memory_id = memory_session["memory_id"]
        
        response = requests.get(f"{BASE_URL}/api/memories",
                               headers={"Authorization": f"Bearer {token}"})
        memories = response.json()
        
        test_memory = next((m for m in memories if m["id"] == memory_id), None)
        assert test_memory is None, "Deleted memory should not appear in list"

    def test_cleanup_test_event(self, memory_session):
        """Cleanup: delete the test event"""
        token = memory_session["token"]
        event_id = memory_session["event_id"]
        
        response = requests.delete(f"{BASE_URL}/api/events/{event_id}",
                                   headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200


class TestTimelineExport:
    """Timeline CSV export tests"""

    @pytest.fixture(scope="class")
    def token(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        return response.json()["token"]

    def test_timeline_export_json(self, token):
        """GET /api/timeline/export?format=json returns JSON"""
        response = requests.get(f"{BASE_URL}/api/timeline/export?format=json",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        print(f"Timeline has {data['total']} items for export")

    def test_timeline_export_csv(self, token):
        """GET /api/timeline/export?format=csv returns CSV file"""
        response = requests.get(f"{BASE_URL}/api/timeline/export?format=csv",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/csv; charset=utf-8"
        
        # Verify CSV content
        csv_content = response.text
        assert "type,title,description,date,location,tags" in csv_content
        print(f"CSV export successful, {len(csv_content)} chars")

    def test_timeline_export_csv_filter(self, token):
        """GET /api/timeline/export?format=csv&item_type=gathering filters export"""
        response = requests.get(f"{BASE_URL}/api/timeline/export?format=csv&item_type=gathering",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        
        csv_lines = response.text.strip().split('\n')
        # All data rows (skip header) should be type=gathering
        for line in csv_lines[1:]:
            if line.strip():
                assert line.startswith("gathering,"), f"Expected gathering type, got: {line[:50]}"


class TestKinshipGroups:
    """Kinship groups endpoint tests"""

    @pytest.fixture(scope="class")
    def token(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        return response.json()["token"]

    def test_kinship_groups_endpoint(self, token):
        """GET /api/kinship/groups returns grouped kinship data"""
        response = requests.get(f"{BASE_URL}/api/kinship/groups",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        
        # Check structure
        assert "groups" in data
        assert "members" in data
        assert isinstance(data["groups"], dict)
        assert isinstance(data["members"], list)
        
        print(f"Kinship groups: {list(data['groups'].keys())}")
        print(f"Members for invite: {len(data['members'])}")

    def test_kinship_groups_members_structure(self, token):
        """Kinship groups members have correct structure"""
        response = requests.get(f"{BASE_URL}/api/kinship/groups",
                               headers={"Authorization": f"Bearer {token}"})
        data = response.json()
        
        for member in data["members"]:
            assert "id" in member
            assert "full_name" in member
            assert "email" in member
            assert "role" in member


class TestRegressionEndpoints:
    """Regression tests for existing functionality"""

    @pytest.fixture(scope="class")
    def token(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        return response.json()["token"]

    def test_auth_bootstrap(self, token):
        """GET /api/auth/bootstrap returns community bootstrap data"""
        response = requests.get(f"{BASE_URL}/api/auth/bootstrap",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "user" in data or "community" in data

    def test_polls_endpoint(self, token):
        """GET /api/polls returns polls list"""
        response = requests.get(f"{BASE_URL}/api/polls",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_announcements_endpoint(self, token):
        """GET /api/announcements returns announcements list"""
        response = requests.get(f"{BASE_URL}/api/announcements",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_subscriptions_plans(self, token):
        """GET /api/subscriptions/plans returns subscription plans"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) == 5  # 5 subscription tiers

    def test_timeline_archive(self, token):
        """GET /api/timeline/archive returns timeline data"""
        response = requests.get(f"{BASE_URL}/api/timeline/archive",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "timeline_items" in data
        assert "on_this_day" in data

    def test_events_list(self, token):
        """GET /api/events returns events list"""
        response = requests.get(f"{BASE_URL}/api/events",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_memories_list(self, token):
        """GET /api/memories returns memories list"""
        response = requests.get(f"{BASE_URL}/api/memories",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_kinship_list(self, token):
        """GET /api/kinship returns kinship relationships"""
        response = requests.get(f"{BASE_URL}/api/kinship",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "relationships" in data

    def test_community_overview(self, token):
        """GET /api/community/overview returns dashboard data"""
        response = requests.get(f"{BASE_URL}/api/community/overview",
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "community" in data
        assert "user" in data
        assert "stats" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

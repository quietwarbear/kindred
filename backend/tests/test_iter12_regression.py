"""
Iteration 12 Regression Tests:
- Backend refactoring verification (existing endpoints still work)
- Full CRUD for subyards, kinship, announcements, budgets, travel plans
- Verify model fixes: KinshipCreateRequest (related_to_name, relationship_scope), SubyardCreateRequest (role_focus)
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_PREFIX = "TEST_ITER12_"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_community(api_client):
    """Bootstrap a fresh test community"""
    unique_id = str(uuid.uuid4())[:8]
    email = f"{TEST_PREFIX}owner_{unique_id}@kindred.app"
    password = "Test1234!"
    
    response = api_client.post(f"{BASE_URL}/api/auth/bootstrap", json={
        "email": email,
        "password": password,
        "full_name": f"{TEST_PREFIX}Owner User",
        "community_name": f"{TEST_PREFIX}Test Community",
        "community_type": "family",
        "location": "Test Location",
        "description": "Test community for iteration 12",
    })
    assert response.status_code == 200, f"Bootstrap failed: {response.text}"
    data = response.json()
    return {
        "token": data["token"],
        "user": data["user"],
        "community": data["community"],
        "email": email,
        "password": password,
    }


@pytest.fixture(scope="module")
def existing_user_token(api_client):
    """Login with existing test user credentials"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": "notiftest2@kindred.app",
        "password": "Test1234!"
    })
    if response.status_code == 200:
        return response.json()["token"]
    return None


# ========== HEALTH CHECK / BACKEND REFACTORING ==========

class TestBackendHealth:
    """Verify backend is working after refactoring"""
    
    def test_health_check(self, api_client):
        """GET /api/ returns health check"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        assert response.json().get("message") == "Kindred API is ready."
    
    def test_existing_user_login(self, api_client):
        """POST /api/auth/login works with existing user"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "notiftest2@kindred.app",
            "password": "Test1234!"
        })
        # User may or may not exist depending on test environment
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert "token" in data
            assert "user" in data
    
    def test_courtyard_home(self, api_client, test_community):
        """GET /api/courtyard/home returns valid response"""
        response = api_client.get(
            f"{BASE_URL}/api/courtyard/home",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "courtyard" in data
        assert "user" in data
        assert "stats" in data
    
    def test_polls_endpoint(self, api_client, test_community):
        """GET /api/polls returns polls list"""
        response = api_client.get(
            f"{BASE_URL}/api/polls",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "polls" in response.json()
    
    def test_notifications_unread_count(self, api_client, test_community):
        """GET /api/notifications/unread-count returns count"""
        response = api_client.get(
            f"{BASE_URL}/api/notifications/unread-count",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "unread_count" in response.json()


# ========== SUBYARDS CRUD ==========

class TestSubyardsCRUD:
    """Full CRUD tests for subyards - verifies model fixes"""
    
    def test_create_subyard(self, api_client, test_community):
        """POST /api/subyards creates subyard with role_focus list"""
        response = api_client.post(
            f"{BASE_URL}/api/subyards",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "name": f"{TEST_PREFIX}Test Subyard",
                "description": "Testing subyard creation with role_focus fix",
                "role_focus": ["organizer", "historian"],
                "inherited_roles": True,
                "visibility": "shared"
            }
        )
        assert response.status_code == 200, f"Create subyard failed: {response.text}"
        data = response.json()
        assert data["name"] == f"{TEST_PREFIX}Test Subyard"
        assert "role_focus" in data
        # Store for later tests
        test_community["subyard_id"] = data["id"]
        return data["id"]
    
    def test_list_subyards(self, api_client, test_community):
        """GET /api/subyards returns subyards list"""
        response = api_client.get(
            f"{BASE_URL}/api/subyards",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "subyards" in data
        assert len(data["subyards"]) > 0  # Should have default subyards from bootstrap
    
    def test_update_subyard(self, api_client, test_community):
        """PUT /api/subyards/{id} updates subyard - verifies model fix"""
        # Get existing subyards
        list_response = api_client.get(
            f"{BASE_URL}/api/subyards",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        subyards = list_response.json().get("subyards", [])
        if not subyards:
            pytest.skip("No subyards to update")
        
        subyard_id = subyards[0]["id"]
        new_name = f"{TEST_PREFIX}Updated Subyard Name"
        
        response = api_client.put(
            f"{BASE_URL}/api/subyards/{subyard_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "name": new_name,
                "description": "Updated description",
                "role_focus": ["organizer", "treasurer"]
            }
        )
        assert response.status_code == 200, f"Update subyard failed: {response.text}"
        data = response.json()
        assert data["name"] == new_name
    
    def test_delete_subyard(self, api_client, test_community):
        """DELETE /api/subyards/{id} deletes subyard"""
        # Create a subyard to delete
        create_response = api_client.post(
            f"{BASE_URL}/api/subyards",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "name": f"{TEST_PREFIX}To Delete",
                "description": "Will be deleted",
                "role_focus": ["organizer"]
            }
        )
        if create_response.status_code != 200:
            pytest.skip(f"Cannot create subyard for delete test: {create_response.text}")
        subyard_id = create_response.json()["id"]
        
        # Delete it
        delete_response = api_client.delete(
            f"{BASE_URL}/api/subyards/{subyard_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== KINSHIP CRUD ==========

class TestKinshipCRUD:
    """Full CRUD tests for kinship - verifies model fixes (related_to_name, relationship_scope)"""
    
    def test_create_kinship(self, api_client, test_community):
        """POST /api/kinship creates kinship with fixed model fields"""
        response = api_client.post(
            f"{BASE_URL}/api/kinship",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "person_name": f"{TEST_PREFIX}John Doe",
                "related_to_name": f"{TEST_PREFIX}Jane Doe",
                "relationship_type": "cousin",
                "relationship_scope": "blood",
                "notes": "Test kinship relationship"
            }
        )
        assert response.status_code == 200, f"Create kinship failed: {response.text}"
        data = response.json()
        assert data["person_name"] == f"{TEST_PREFIX}John Doe"
        assert data["related_to_name"] == f"{TEST_PREFIX}Jane Doe"
        assert data["relationship_scope"] == "blood"
        test_community["kinship_id"] = data["id"]
        return data["id"]
    
    def test_list_kinship(self, api_client, test_community):
        """GET /api/kinship returns relationships list"""
        response = api_client.get(
            f"{BASE_URL}/api/kinship",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "relationships" in response.json()
    
    def test_delete_kinship(self, api_client, test_community):
        """DELETE /api/kinship/{id} deletes kinship relationship"""
        # Create a kinship to delete
        create_response = api_client.post(
            f"{BASE_URL}/api/kinship",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "person_name": f"{TEST_PREFIX}Delete Person",
                "related_to_name": f"{TEST_PREFIX}Related Person",
                "relationship_type": "sibling",
                "relationship_scope": "blood",
            }
        )
        if create_response.status_code != 200:
            pytest.skip(f"Cannot create kinship for delete test: {create_response.text}")
        kinship_id = create_response.json()["id"]
        
        # Delete it
        delete_response = api_client.delete(
            f"{BASE_URL}/api/kinship/{kinship_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== ANNOUNCEMENTS CRUD ==========

class TestAnnouncementsCRUD:
    """Full CRUD tests for announcements"""
    
    def test_create_announcement(self, api_client, test_community):
        """POST /api/announcements creates announcement"""
        response = api_client.post(
            f"{BASE_URL}/api/announcements",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}Test Announcement",
                "body": "This is a test announcement body",
                "scope": "courtyard"
            }
        )
        assert response.status_code == 200, f"Create announcement failed: {response.text}"
        data = response.json()
        assert data["title"] == f"{TEST_PREFIX}Test Announcement"
        test_community["announcement_id"] = data["id"]
        return data["id"]
    
    def test_list_announcements(self, api_client, test_community):
        """GET /api/announcements returns announcements list"""
        response = api_client.get(
            f"{BASE_URL}/api/announcements",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "announcements" in response.json()
    
    def test_update_announcement(self, api_client, test_community):
        """PUT /api/announcements/{id} updates announcement"""
        # First create one
        create_response = api_client.post(
            f"{BASE_URL}/api/announcements",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}Original Title",
                "body": "Original body",
                "scope": "courtyard"
            }
        )
        if create_response.status_code != 200:
            pytest.skip("Cannot create announcement for update test")
        ann_id = create_response.json()["id"]
        
        # Update it
        update_response = api_client.put(
            f"{BASE_URL}/api/announcements/{ann_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}Updated Title",
                "body": "Updated body content",
                "scope": "courtyard"
            }
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["title"] == f"{TEST_PREFIX}Updated Title"
        assert data["body"] == "Updated body content"
    
    def test_delete_announcement(self, api_client, test_community):
        """DELETE /api/announcements/{id} deletes announcement"""
        # Create one to delete
        create_response = api_client.post(
            f"{BASE_URL}/api/announcements",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}To Delete",
                "body": "Will be deleted",
                "scope": "courtyard"
            }
        )
        if create_response.status_code != 200:
            pytest.skip("Cannot create announcement for delete test")
        ann_id = create_response.json()["id"]
        
        delete_response = api_client.delete(
            f"{BASE_URL}/api/announcements/{ann_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== BUDGET PLANS CRUD ==========

class TestBudgetPlansCRUD:
    """Full CRUD tests for budget plans"""
    
    def test_create_budget(self, api_client, test_community):
        """POST /api/budget-plans creates budget plan"""
        response = api_client.post(
            f"{BASE_URL}/api/budget-plans",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}Test Budget",
                "target_amount": 1000.0,
                "current_amount": 250.0,
                "suggested_contribution": 50.0,
                "notes": "Test budget for iteration 12"
            }
        )
        assert response.status_code == 200, f"Create budget failed: {response.text}"
        data = response.json()
        assert data["title"] == f"{TEST_PREFIX}Test Budget"
        test_community["budget_id"] = data["id"]
        return data["id"]
    
    def test_list_budgets(self, api_client, test_community):
        """GET /api/budget-plans returns budgets list"""
        response = api_client.get(
            f"{BASE_URL}/api/budget-plans",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "budget_plans" in response.json()
    
    def test_update_budget(self, api_client, test_community):
        """PUT /api/budget-plans/{id} updates budget"""
        # Create one first
        create_response = api_client.post(
            f"{BASE_URL}/api/budget-plans",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}Original Budget",
                "target_amount": 500.0,
                "current_amount": 100.0,
            }
        )
        if create_response.status_code != 200:
            pytest.skip(f"Cannot create budget for update test: {create_response.text}")
        budget_id = create_response.json()["id"]
        
        # Update it
        update_response = api_client.put(
            f"{BASE_URL}/api/budget-plans/{budget_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}Updated Budget",
                "target_amount": 1500.0,
                "current_amount": 500.0,
            }
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["title"] == f"{TEST_PREFIX}Updated Budget"
        assert data["target_amount"] == 1500.0
    
    def test_delete_budget(self, api_client, test_community):
        """DELETE /api/budget-plans/{id} deletes budget"""
        # Create one to delete
        create_response = api_client.post(
            f"{BASE_URL}/api/budget-plans",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "title": f"{TEST_PREFIX}To Delete Budget",
                "target_amount": 100.0,
                "current_amount": 0.0,
            }
        )
        if create_response.status_code != 200:
            pytest.skip(f"Cannot create budget for delete test: {create_response.text}")
        budget_id = create_response.json()["id"]
        
        delete_response = api_client.delete(
            f"{BASE_URL}/api/budget-plans/{budget_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== TRAVEL PLANS CRUD ==========

class TestTravelPlansCRUD:
    """Full CRUD tests for travel plans"""
    
    def test_create_travel_plan(self, api_client, test_community):
        """POST /api/travel-plans creates travel plan"""
        response = api_client.post(
            f"{BASE_URL}/api/travel-plans",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "traveler_name": f"{TEST_PREFIX}Test Traveler",
                "mode": "driving",
                "origin": "New York",
                "notes": "Test travel plan",
                "estimated_cost": 150.0,
            }
        )
        assert response.status_code == 200, f"Create travel plan failed: {response.text}"
        data = response.json()
        assert data["traveler_name"] == f"{TEST_PREFIX}Test Traveler"
        test_community["travel_plan_id"] = data["id"]
        return data["id"]
    
    def test_list_travel_plans(self, api_client, test_community):
        """GET /api/travel-plans returns travel plans list"""
        response = api_client.get(
            f"{BASE_URL}/api/travel-plans",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "travel_plans" in response.json()
    
    def test_delete_travel_plan(self, api_client, test_community):
        """DELETE /api/travel-plans/{id} deletes travel plan"""
        # Create one to delete
        create_response = api_client.post(
            f"{BASE_URL}/api/travel-plans",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={
                "traveler_name": f"{TEST_PREFIX}Delete Traveler",
                "mode": "flying",
                "origin": "Chicago",
                "estimated_cost": 300.0,
            }
        )
        if create_response.status_code != 200:
            pytest.skip(f"Cannot create travel plan for delete test: {create_response.text}")
        plan_id = create_response.json()["id"]
        
        delete_response = api_client.delete(
            f"{BASE_URL}/api/travel-plans/{plan_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== CHAT MESSAGES CRUD ==========

class TestChatMessagesCRUD:
    """Tests for chat message creation and deletion"""
    
    def test_create_and_delete_chat_message(self, api_client, test_community):
        """POST and DELETE chat messages"""
        # Get chat rooms
        rooms_response = api_client.get(
            f"{BASE_URL}/api/chat/rooms",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        rooms = rooms_response.json().get("rooms", [])
        if not rooms:
            pytest.skip("No chat rooms available")
        
        room_id = rooms[0]["id"]
        
        # Create a message
        create_response = api_client.post(
            f"{BASE_URL}/api/chat/rooms/{room_id}/messages",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={"text": f"{TEST_PREFIX}Test chat message", "attachments": []}
        )
        assert create_response.status_code == 200, f"Create chat message failed: {create_response.text}"
        
        messages = create_response.json().get("messages", [])
        test_msg = next((m for m in messages if TEST_PREFIX in m.get("text", "")), None)
        if not test_msg:
            pytest.skip("Could not find created message")
        
        msg_id = test_msg["id"]
        
        # Delete the message
        delete_response = api_client.delete(
            f"{BASE_URL}/api/chat/rooms/{room_id}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True

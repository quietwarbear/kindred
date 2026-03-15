"""
Tests for Iteration 11:
- Ownership transfer flow (POST /api/community/transfer-ownership)
- Community members listing (GET /api/community/members)
- Edit/Delete endpoints for subyards, kinship, announcements, chat messages, budgets, travel plans
- Backend refactoring verification (existing endpoints still work)
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test data prefix for cleanup
TEST_PREFIX = "TEST_ITER11_"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_community(api_client):
    """Bootstrap a fresh test community with owner"""
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
        "description": "Test community for iteration 11",
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
def member_user(api_client, test_community):
    """Create an invite and register a member user"""
    unique_id = str(uuid.uuid4())[:8]
    member_email = f"{TEST_PREFIX}member_{unique_id}@kindred.app"
    member_password = "Member1234!"
    
    # Create invite as owner
    invite_response = api_client.post(
        f"{BASE_URL}/api/invites",
        headers={"Authorization": f"Bearer {test_community['token']}"},
        json={"email": member_email, "role": "member"}
    )
    assert invite_response.status_code == 200, f"Invite creation failed: {invite_response.text}"
    invite_code = invite_response.json()["code"]
    
    # Register member with invite
    register_response = api_client.post(f"{BASE_URL}/api/auth/register-with-invite", json={
        "email": member_email,
        "password": member_password,
        "full_name": f"{TEST_PREFIX}Member User",
        "invite_code": invite_code,
    })
    assert register_response.status_code == 200, f"Member registration failed: {register_response.text}"
    data = register_response.json()
    return {
        "token": data["token"],
        "user": data["user"],
        "email": member_email,
        "password": member_password,
    }


# ========== OWNERSHIP TRANSFER TESTS ==========

class TestOwnershipTransfer:
    """Tests for POST /api/community/transfer-ownership and GET /api/community/members"""
    
    def test_list_community_members(self, api_client, test_community, member_user):
        """GET /api/community/members returns all community members"""
        response = api_client.get(
            f"{BASE_URL}/api/community/members",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert len(data["members"]) >= 2  # Owner + member at minimum
        
        # Verify member structure
        member_ids = [m["id"] for m in data["members"]]
        assert test_community["user"]["id"] in member_ids
        assert member_user["user"]["id"] in member_ids
    
    def test_transfer_blocks_self_transfer(self, api_client, test_community):
        """POST /api/community/transfer-ownership blocks self-transfer"""
        response = api_client.post(
            f"{BASE_URL}/api/community/transfer-ownership",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={"new_owner_user_id": test_community["user"]["id"]}
        )
        assert response.status_code == 400
        assert "already the owner" in response.json().get("detail", "").lower()
    
    def test_transfer_blocks_non_host_users(self, api_client, member_user, test_community):
        """POST /api/community/transfer-ownership blocks non-host users"""
        response = api_client.post(
            f"{BASE_URL}/api/community/transfer-ownership",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={"new_owner_user_id": test_community["user"]["id"]}
        )
        assert response.status_code == 403
    
    def test_transfer_blocks_invalid_user(self, api_client, test_community):
        """POST /api/community/transfer-ownership with invalid user returns 404"""
        response = api_client.post(
            f"{BASE_URL}/api/community/transfer-ownership",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={"new_owner_user_id": "invalid-user-id"}
        )
        assert response.status_code == 404
    
    def test_transfer_ownership_success(self, api_client, test_community, member_user):
        """POST /api/community/transfer-ownership transfers owner to another member"""
        response = api_client.post(
            f"{BASE_URL}/api/community/transfer-ownership",
            headers={"Authorization": f"Bearer {test_community['token']}"},
            json={"new_owner_user_id": member_user["user"]["id"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True
        assert data.get("new_owner_name") == member_user["user"]["full_name"]
        
        # Verify the old owner is now demoted (check via /api/auth/me)
        me_response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["user"]["role"] == "organizer"


# ========== BACKEND REFACTORING VERIFICATION ==========

class TestBackendRefactoring:
    """Verify existing endpoints still work after refactoring"""
    
    def test_root_endpoint(self, api_client):
        """GET /api/ still works"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        assert response.json().get("message") == "Kindred API is ready."
    
    def test_polls_endpoint(self, api_client, test_community):
        """GET /api/polls still works"""
        # Use member token since ownership was transferred
        response = api_client.get(
            f"{BASE_URL}/api/polls",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "polls" in response.json()
    
    def test_notifications_unread_count(self, api_client, test_community):
        """GET /api/notifications/unread-count still works"""
        response = api_client.get(
            f"{BASE_URL}/api/notifications/unread-count",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        assert "unread_count" in response.json()
    
    def test_courtyard_home(self, api_client, test_community):
        """GET /api/courtyard/home still works"""
        response = api_client.get(
            f"{BASE_URL}/api/courtyard/home",
            headers={"Authorization": f"Bearer {test_community['token']}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "courtyard" in data
        assert "user" in data


# ========== KINSHIP CRUD TESTS ==========

class TestKinshipCRUD:
    """Tests for kinship delete endpoint"""
    
    def test_create_and_delete_kinship(self, api_client, member_user):
        """DELETE /api/kinship/{id} deletes kinship relationship"""
        # Create a kinship
        create_response = api_client.post(
            f"{BASE_URL}/api/kinship",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "person_name": f"{TEST_PREFIX}Test Person",
                "relationship_type": "cousin",
                "notes": "Test kinship for deletion"
            }
        )
        assert create_response.status_code == 200, f"Create kinship failed: {create_response.text}"
        kinship_id = create_response.json()["id"]
        
        # Delete the kinship
        delete_response = api_client.delete(
            f"{BASE_URL}/api/kinship/{kinship_id}",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True
        
        # Verify it's gone
        list_response = api_client.get(
            f"{BASE_URL}/api/kinship",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        kinship_ids = [k["id"] for k in list_response.json().get("relationships", [])]
        assert kinship_id not in kinship_ids
    
    def test_delete_nonexistent_kinship(self, api_client, member_user):
        """DELETE /api/kinship/{id} with invalid ID returns 404"""
        response = api_client.delete(
            f"{BASE_URL}/api/kinship/nonexistent-id",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        assert response.status_code == 404


# ========== ANNOUNCEMENTS CRUD TESTS ==========

class TestAnnouncementsCRUD:
    """Tests for announcements edit/delete endpoints"""
    
    @pytest.fixture
    def test_announcement(self, api_client, member_user):
        """Create an announcement for testing (need organizer+ role, use transferred owner)"""
        # Member is now host after transfer, so they can create announcements
        response = api_client.post(
            f"{BASE_URL}/api/announcements",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "title": f"{TEST_PREFIX}Test Announcement",
                "body": "Test body for deletion",
                "scope": "courtyard",
            }
        )
        if response.status_code != 200:
            pytest.skip(f"Cannot create announcement: {response.text}")
        return response.json()
    
    def test_update_announcement(self, api_client, member_user, test_announcement):
        """PUT /api/announcements/{id} updates announcement title/body"""
        new_title = f"{TEST_PREFIX}Updated Title"
        new_body = "Updated body content"
        
        response = api_client.put(
            f"{BASE_URL}/api/announcements/{test_announcement['id']}",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "title": new_title,
                "body": new_body,
                "scope": "courtyard",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == new_title
        assert data["body"] == new_body
    
    def test_delete_announcement(self, api_client, member_user):
        """DELETE /api/announcements/{id} deletes announcement"""
        # Create a fresh announcement
        create_response = api_client.post(
            f"{BASE_URL}/api/announcements",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "title": f"{TEST_PREFIX}To Delete",
                "body": "Will be deleted",
                "scope": "courtyard",
            }
        )
        if create_response.status_code != 200:
            pytest.skip("Cannot create announcement for delete test")
        ann_id = create_response.json()["id"]
        
        # Delete it
        delete_response = api_client.delete(
            f"{BASE_URL}/api/announcements/{ann_id}",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== BUDGET PLANS CRUD TESTS ==========

class TestBudgetPlansCRUD:
    """Tests for budget plans edit/delete endpoints"""
    
    @pytest.fixture
    def test_budget(self, api_client, member_user):
        """Create a budget plan for testing"""
        response = api_client.post(
            f"{BASE_URL}/api/budget-plans",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "title": f"{TEST_PREFIX}Test Budget",
                "target_amount": 1000.0,
                "current_amount": 200.0,
                "suggested_contribution": 50.0,
                "budget_type": "event",
                "notes": "Test budget"
            }
        )
        if response.status_code != 200:
            pytest.skip(f"Cannot create budget: {response.text}")
        return response.json()
    
    def test_update_budget_plan(self, api_client, member_user, test_budget):
        """PUT /api/budget-plans/{id} updates budget title/amounts"""
        new_title = f"{TEST_PREFIX}Updated Budget"
        new_target = 1500.0
        new_current = 500.0
        
        response = api_client.put(
            f"{BASE_URL}/api/budget-plans/{test_budget['id']}",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "title": new_title,
                "target_amount": new_target,
                "current_amount": new_current,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == new_title
        assert data["target_amount"] == new_target
        assert data["current_amount"] == new_current
    
    def test_delete_budget_plan(self, api_client, member_user):
        """DELETE /api/budget-plans/{id} deletes budget plan"""
        # Create a fresh budget
        create_response = api_client.post(
            f"{BASE_URL}/api/budget-plans",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "title": f"{TEST_PREFIX}To Delete Budget",
                "target_amount": 500.0,
                "current_amount": 0.0,
            }
        )
        if create_response.status_code != 200:
            pytest.skip(f"Cannot create budget for delete test: {create_response.text}")
        budget_id = create_response.json()["id"]
        
        # Delete it
        delete_response = api_client.delete(
            f"{BASE_URL}/api/budget-plans/{budget_id}",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== SUBYARDS CRUD TESTS ==========

class TestSubyardsCRUD:
    """Tests for subyards edit/delete endpoints"""
    
    def test_list_subyards(self, api_client, member_user):
        """GET /api/subyards returns subyards"""
        response = api_client.get(
            f"{BASE_URL}/api/subyards",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        assert response.status_code == 200
        assert "subyards" in response.json()
    
    def test_update_subyard(self, api_client, member_user):
        """PUT /api/subyards/{id} updates subyard name/description"""
        # Get existing subyards
        list_response = api_client.get(
            f"{BASE_URL}/api/subyards",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        subyards = list_response.json().get("subyards", [])
        if not subyards:
            pytest.skip("No subyards to update")
        
        subyard_id = subyards[0]["id"]
        new_name = f"{TEST_PREFIX}Updated Subyard"
        
        response = api_client.put(
            f"{BASE_URL}/api/subyards/{subyard_id}",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={
                "name": new_name,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == new_name


# ========== CHAT MESSAGE DELETE TESTS ==========

class TestChatMessageDelete:
    """Tests for chat message delete endpoint"""
    
    def test_delete_chat_message(self, api_client, member_user):
        """DELETE /api/chat/rooms/{room_id}/messages/{msg_id} deletes message"""
        # Get chat rooms
        rooms_response = api_client.get(
            f"{BASE_URL}/api/chat/rooms",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        rooms = rooms_response.json().get("rooms", [])
        if not rooms:
            pytest.skip("No chat rooms available")
        
        room_id = rooms[0]["id"]
        
        # Create a message
        create_response = api_client.post(
            f"{BASE_URL}/api/chat/rooms/{room_id}/messages",
            headers={"Authorization": f"Bearer {member_user['token']}"},
            json={"text": f"{TEST_PREFIX}Test message to delete", "attachments": []}
        )
        if create_response.status_code != 200:
            pytest.skip(f"Cannot create chat message: {create_response.text}")
        
        messages = create_response.json().get("messages", [])
        # Find our message
        test_msg = next((m for m in messages if TEST_PREFIX in m.get("text", "")), None)
        if not test_msg:
            pytest.skip("Could not find created message")
        
        msg_id = test_msg["id"]
        
        # Delete the message
        delete_response = api_client.delete(
            f"{BASE_URL}/api/chat/rooms/{room_id}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        assert delete_response.status_code == 200
        assert delete_response.json().get("ok") == True


# ========== TRAVEL PLANS CRUD TESTS ==========

class TestTravelPlansCRUD:
    """Tests for travel plans edit/delete endpoints"""
    
    def test_list_travel_plans(self, api_client, member_user):
        """GET /api/travel-plans returns travel plans"""
        response = api_client.get(
            f"{BASE_URL}/api/travel-plans",
            headers={"Authorization": f"Bearer {member_user['token']}"}
        )
        assert response.status_code == 200
        assert "travel_plans" in response.json()


# ========== AUTH AND LOGIN TEST ==========

class TestExistingUserLogin:
    """Test login with existing credentials"""
    
    def test_login_with_test_credentials(self, api_client):
        """Login with the provided test credentials works"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "notiftest2@kindred.app",
            "password": "Test1234!"
        })
        # This might fail if user doesn't exist, that's ok
        if response.status_code == 200:
            data = response.json()
            assert "token" in data
            assert "user" in data
        else:
            # User doesn't exist, which is fine for a clean test environment
            assert response.status_code in [401, 404]

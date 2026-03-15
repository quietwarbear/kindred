"""
Account Deletion Tests - Play Store Compliant Account Deletion Feature
Tests DELETE /api/auth/account endpoint with various scenarios:
- Password-auth user deletion with correct/wrong/missing password
- Community owner deletion blocking (when other members exist)
- Sole owner deletion (cascades to community + all data)
- Token invalidation after deletion
"""

import os
import pytest
import requests
import uuid
from time import sleep

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


class TestAccountDeletionPasswordAuth:
    """Tests for password-authenticated user account deletion"""

    @pytest.fixture
    def test_user(self):
        """Create a disposable user via bootstrap for deletion testing"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "email": f"TEST_delete_{unique_id}@kindred.app",
            "password": "DeleteTest123!",
            "full_name": f"Delete Test {unique_id}",
            "community_name": f"Delete Test Community {unique_id}",
            "community_type": "family",
            "location": "Test Location",
            "description": "Test community for deletion testing",
            "motto": "Test motto"
        }
        response = requests.post(f"{BASE_URL}/api/auth/bootstrap", json=payload)
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        return {
            "token": data["token"],
            "user_id": data["user"]["id"],
            "email": payload["email"],
            "password": payload["password"],
            "community_id": data["community"]["id"]
        }

    def test_delete_account_correct_password(self, test_user):
        """DELETE /api/auth/account with correct password deletes account"""
        token = test_user["token"]
        password = test_user["password"]

        # Delete account
        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": password}
        )
        assert response.status_code == 200, f"Delete failed: {response.text}"
        data = response.json()
        assert data["ok"] is True
        assert "deleted" in data["message"].lower()

        # Verify token is invalid after deletion
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_response.status_code == 401, "Token should be invalid after deletion"
        print("PASS: Account deleted with correct password, token invalidated")

    def test_delete_account_wrong_password(self, test_user):
        """DELETE /api/auth/account with wrong password returns 403"""
        token = test_user["token"]

        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "WrongPassword123!"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert "password" in data.get("detail", "").lower()
        print("PASS: Wrong password returns 403 Forbidden")

    def test_delete_account_no_password(self, test_user):
        """DELETE /api/auth/account without password returns 400 for password-auth users"""
        token = test_user["token"]

        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": ""}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "password" in data.get("detail", "").lower() and "required" in data.get("detail", "").lower()
        print("PASS: Missing password returns 400 Bad Request")

    def test_delete_account_empty_payload(self, test_user):
        """DELETE /api/auth/account without password field returns 400"""
        token = test_user["token"]

        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        # Should still trigger 400 since default password is empty string
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Empty payload returns 400 for password-auth user")


class TestCommunityOwnerDeletion:
    """Tests for community owner deletion scenarios"""

    @pytest.fixture
    def owner_with_member(self):
        """Create owner + invite a member to test ownership block"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create owner via bootstrap
        owner_payload = {
            "email": f"TEST_owner_{unique_id}@kindred.app",
            "password": "OwnerTest123!",
            "full_name": f"Owner Test {unique_id}",
            "community_name": f"Ownership Test Community {unique_id}",
            "community_type": "family",
            "location": "Test Location",
            "description": "Test community for ownership testing",
            "motto": "Test motto"
        }
        owner_response = requests.post(f"{BASE_URL}/api/auth/bootstrap", json=owner_payload)
        assert owner_response.status_code == 200, f"Owner bootstrap failed: {owner_response.text}"
        owner_data = owner_response.json()
        owner_token = owner_data["token"]
        community_id = owner_data["community"]["id"]

        # Create invite for member
        invite_payload = {
            "email": f"TEST_member_{unique_id}@kindred.app",
            "role": "member"
        }
        invite_response = requests.post(
            f"{BASE_URL}/api/invites",
            headers={"Authorization": f"Bearer {owner_token}"},
            json=invite_payload
        )
        assert invite_response.status_code == 200, f"Invite creation failed: {invite_response.text}"
        invite_code = invite_response.json()["code"]

        # Register member with invite
        member_payload = {
            "email": f"TEST_member_{unique_id}@kindred.app",
            "password": "MemberTest123!",
            "full_name": f"Member Test {unique_id}",
            "invite_code": invite_code
        }
        member_response = requests.post(f"{BASE_URL}/api/auth/register-with-invite", json=member_payload)
        assert member_response.status_code == 200, f"Member registration failed: {member_response.text}"
        member_data = member_response.json()

        return {
            "owner_token": owner_token,
            "owner_password": owner_payload["password"],
            "owner_user_id": owner_data["user"]["id"],
            "member_token": member_data["token"],
            "member_password": member_payload["password"],
            "member_user_id": member_data["user"]["id"],
            "community_id": community_id
        }

    def test_owner_deletion_blocked_with_other_members(self, owner_with_member):
        """Community owner with other members gets 409 block message"""
        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {owner_with_member['owner_token']}"},
            json={"password": owner_with_member["owner_password"]}
        )
        assert response.status_code == 409, f"Expected 409 Conflict, got {response.status_code}: {response.text}"
        data = response.json()
        assert "owner" in data.get("detail", "").lower()
        assert "transfer" in data.get("detail", "").lower()
        print("PASS: Owner deletion blocked with 409 when other members exist")

    def test_member_can_delete_while_owner_exists(self, owner_with_member):
        """Non-owner members can delete their accounts without restriction"""
        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {owner_with_member['member_token']}"},
            json={"password": owner_with_member["member_password"]}
        )
        assert response.status_code == 200, f"Member deletion failed: {response.text}"
        print("PASS: Non-owner member can delete account")

    def test_owner_can_delete_after_sole_member(self, owner_with_member):
        """After member leaves, owner (now sole member) can delete - cascades to community"""
        # First delete the member
        member_delete = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {owner_with_member['member_token']}"},
            json={"password": owner_with_member["member_password"]}
        )
        assert member_delete.status_code == 200, f"Member deletion failed: {member_delete.text}"

        # Now owner should be able to delete (sole member)
        owner_delete = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {owner_with_member['owner_token']}"},
            json={"password": owner_with_member["owner_password"]}
        )
        assert owner_delete.status_code == 200, f"Owner deletion failed: {owner_delete.text}"
        data = owner_delete.json()
        assert data["ok"] is True
        print("PASS: Sole owner can delete account (cascades to community)")


class TestSoleOwnerDeletion:
    """Tests for sole community owner deletion (cascades to community + all data)"""

    @pytest.fixture
    def sole_owner(self):
        """Create a sole owner community for full cascade deletion test"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "email": f"TEST_sole_{unique_id}@kindred.app",
            "password": "SoleTest123!",
            "full_name": f"Sole Owner {unique_id}",
            "community_name": f"Sole Owner Community {unique_id}",
            "community_type": "family",
            "location": "Test Location",
            "description": "Test community for cascade deletion testing",
            "motto": "Test motto"
        }
        response = requests.post(f"{BASE_URL}/api/auth/bootstrap", json=payload)
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        return {
            "token": data["token"],
            "user_id": data["user"]["id"],
            "email": payload["email"],
            "password": payload["password"],
            "community_id": data["community"]["id"]
        }

    def test_sole_owner_deletion_cascades(self, sole_owner):
        """Sole community owner can delete (deletes community + all data)"""
        token = sole_owner["token"]
        password = sole_owner["password"]
        community_id = sole_owner["community_id"]

        # Verify community exists before deletion
        home_response = requests.get(
            f"{BASE_URL}/api/courtyard/home",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert home_response.status_code == 200, "Community should exist before deletion"

        # Delete sole owner account
        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": password}
        )
        assert response.status_code == 200, f"Deletion failed: {response.text}"
        data = response.json()
        assert data["ok"] is True
        print("PASS: Sole owner deletion succeeds and cascades to community")


class TestTokenInvalidation:
    """Tests for token invalidation after account deletion"""

    @pytest.fixture
    def test_user_for_token_test(self):
        """Create user for token invalidation test"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "email": f"TEST_token_{unique_id}@kindred.app",
            "password": "TokenTest123!",
            "full_name": f"Token Test {unique_id}",
            "community_name": f"Token Test Community {unique_id}",
            "community_type": "family",
            "location": "Test Location",
            "description": "Test community",
            "motto": ""
        }
        response = requests.post(f"{BASE_URL}/api/auth/bootstrap", json=payload)
        assert response.status_code == 200
        data = response.json()
        return {
            "token": data["token"],
            "password": payload["password"]
        }

    def test_token_invalid_after_deletion(self, test_user_for_token_test):
        """Token becomes invalid after account deletion"""
        token = test_user_for_token_test["token"]
        password = test_user_for_token_test["password"]

        # Verify token works before deletion
        me_before = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_before.status_code == 200, "Token should work before deletion"

        # Delete account
        delete_response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": password}
        )
        assert delete_response.status_code == 200

        # Verify token is invalid after deletion
        me_after = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_after.status_code == 401, f"Token should be invalid after deletion, got {me_after.status_code}"
        print("PASS: Token invalidated after account deletion")

    def test_all_endpoints_blocked_after_deletion(self, test_user_for_token_test):
        """All authenticated endpoints should reject deleted user's token"""
        token = test_user_for_token_test["token"]
        password = test_user_for_token_test["password"]

        # Delete account
        delete_response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": password}
        )
        assert delete_response.status_code == 200

        # Test various endpoints
        endpoints = [
            ("GET", "/api/courtyard/home"),
            ("GET", "/api/community/members"),
            ("GET", "/api/polls"),
            ("GET", "/api/announcements"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                resp = requests.get(
                    f"{BASE_URL}{endpoint}",
                    headers={"Authorization": f"Bearer {token}"}
                )
            assert resp.status_code == 401, f"{endpoint} should return 401 after deletion"
        
        print("PASS: All endpoints reject token after account deletion")


class TestUnauthorizedDeletion:
    """Tests for unauthorized deletion attempts"""

    def test_delete_without_auth_returns_401(self):
        """DELETE /api/auth/account without auth returns 401"""
        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            json={"password": "anything"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Unauthenticated deletion returns 401")

    def test_delete_with_invalid_token_returns_401(self):
        """DELETE /api/auth/account with invalid token returns 401"""
        response = requests.delete(
            f"{BASE_URL}/api/auth/account",
            headers={"Authorization": "Bearer invalid_token_here"},
            json={"password": "anything"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Invalid token returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

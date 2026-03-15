"""
Backend tests for inline editing of subyards and announcements.
Tests PUT /api/subyards/{id} and PUT /api/announcements/{id} endpoints.
Iteration 13 - Testing inline edit feature for Courtyards page.
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from previous iterations
TEST_EMAIL = "notiftest2@kindred.app"
TEST_PASSWORD = "Test1234!"


class TestInlineEditingFeature:
    """Tests for subyard and announcement inline editing"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login once and get auth token"""
        if not BASE_URL:
            pytest.skip("REACT_APP_BACKEND_URL not set")
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        yield

    def test_login_works(self):
        """Verify test user can login"""
        print(f"✅ Login successful with token starting: {self.token[:20]}...")
        assert self.token is not None

    def test_get_subyards_list(self):
        """GET /api/subyards returns list"""
        response = requests.get(f"{BASE_URL}/api/subyards", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "subyards" in data
        print(f"✅ GET /api/subyards - Found {len(data['subyards'])} subyards")
        return data["subyards"]

    def test_create_subyard_for_edit_test(self):
        """POST /api/subyards creates subyard for edit testing"""
        payload = {
            "name": f"TEST_EDIT_Subyard_{uuid.uuid4().hex[:6]}",
            "description": "Original description for edit test",
            "inherited_roles": True,
            "role_focus": ["organizer", "historian"],
            "visibility": "shared"
        }
        response = requests.post(
            f"{BASE_URL}/api/subyards",
            headers=self.headers,
            json=payload
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        assert data["name"] == payload["name"]
        assert data["description"] == payload["description"]
        print(f"✅ POST /api/subyards - Created subyard: {data['id']}")
        return data

    def test_put_subyard_updates_name_and_description(self):
        """PUT /api/subyards/{id} updates subyard name and description"""
        # First create a subyard
        create_payload = {
            "name": f"TEST_PUT_Subyard_{uuid.uuid4().hex[:6]}",
            "description": "Original description",
            "inherited_roles": True,
            "role_focus": ["organizer"],
            "visibility": "shared"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/subyards",
            headers=self.headers,
            json=create_payload
        )
        assert create_response.status_code == 200
        created = create_response.json()
        subyard_id = created["id"]

        # Now update it via PUT
        update_payload = {
            "name": "Updated Subyard Name",
            "description": "Updated description after inline edit",
            "inherited_roles": True,
            "role_focus": ["organizer"],
            "visibility": "shared"
        }
        put_response = requests.put(
            f"{BASE_URL}/api/subyards/{subyard_id}",
            headers=self.headers,
            json=update_payload
        )
        assert put_response.status_code == 200, f"PUT failed: {put_response.text}"
        updated = put_response.json()
        
        # Verify the update
        assert updated["name"] == "Updated Subyard Name", f"Name not updated: {updated}"
        assert updated["description"] == "Updated description after inline edit", f"Description not updated: {updated}"
        print(f"✅ PUT /api/subyards/{subyard_id} - Successfully updated name and description")

        # GET to verify persistence
        get_response = requests.get(f"{BASE_URL}/api/subyards", headers=self.headers)
        assert get_response.status_code == 200
        subyards = get_response.json()["subyards"]
        found = next((s for s in subyards if s["id"] == subyard_id), None)
        assert found is not None
        assert found["name"] == "Updated Subyard Name"
        assert found["description"] == "Updated description after inline edit"
        print(f"✅ GET /api/subyards - Verified update persisted in database")

        # Cleanup
        delete_response = requests.delete(
            f"{BASE_URL}/api/subyards/{subyard_id}",
            headers=self.headers
        )
        assert delete_response.status_code == 200
        print(f"✅ Cleaned up test subyard")

    def test_get_announcements_list(self):
        """GET /api/announcements returns list"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "announcements" in data
        print(f"✅ GET /api/announcements - Found {len(data['announcements'])} announcements")
        return data["announcements"]

    def test_create_announcement_for_edit_test(self):
        """POST /api/announcements creates announcement for edit testing"""
        payload = {
            "title": f"TEST_EDIT_Announcement_{uuid.uuid4().hex[:6]}",
            "body": "Original body for edit test",
            "scope": "courtyard",
            "subyard_id": "",
            "attachments": []
        }
        response = requests.post(
            f"{BASE_URL}/api/announcements",
            headers=self.headers,
            json=payload
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        assert data["title"] == payload["title"]
        assert data["body"] == payload["body"]
        print(f"✅ POST /api/announcements - Created announcement: {data['id']}")
        return data

    def test_put_announcement_updates_title_and_body(self):
        """PUT /api/announcements/{id} updates announcement title and body"""
        # First create an announcement
        create_payload = {
            "title": f"TEST_PUT_Announcement_{uuid.uuid4().hex[:6]}",
            "body": "Original body content",
            "scope": "courtyard",
            "subyard_id": "",
            "attachments": []
        }
        create_response = requests.post(
            f"{BASE_URL}/api/announcements",
            headers=self.headers,
            json=create_payload
        )
        assert create_response.status_code == 200
        created = create_response.json()
        announcement_id = created["id"]

        # Now update it via PUT
        update_payload = {
            "title": "Updated Announcement Title",
            "body": "Updated body content after inline edit",
            "scope": "courtyard",
            "subyard_id": ""
        }
        put_response = requests.put(
            f"{BASE_URL}/api/announcements/{announcement_id}",
            headers=self.headers,
            json=update_payload
        )
        assert put_response.status_code == 200, f"PUT failed: {put_response.text}"
        updated = put_response.json()
        
        # Verify the update
        assert updated["title"] == "Updated Announcement Title", f"Title not updated: {updated}"
        assert updated["body"] == "Updated body content after inline edit", f"Body not updated: {updated}"
        print(f"✅ PUT /api/announcements/{announcement_id} - Successfully updated title and body")

        # GET to verify persistence
        get_response = requests.get(f"{BASE_URL}/api/announcements", headers=self.headers)
        assert get_response.status_code == 200
        announcements = get_response.json()["announcements"]
        found = next((a for a in announcements if a["id"] == announcement_id), None)
        assert found is not None
        assert found["title"] == "Updated Announcement Title"
        assert found["body"] == "Updated body content after inline edit"
        print(f"✅ GET /api/announcements - Verified update persisted in database")

        # Cleanup
        delete_response = requests.delete(
            f"{BASE_URL}/api/announcements/{announcement_id}",
            headers=self.headers
        )
        assert delete_response.status_code == 200
        print(f"✅ Cleaned up test announcement")

    def test_put_subyard_returns_404_for_invalid_id(self):
        """PUT /api/subyards/{invalid_id} returns 404"""
        update_payload = {
            "name": "Should Not Exist",
            "description": "This should fail",
            "inherited_roles": True,
            "role_focus": ["organizer"],
            "visibility": "shared"
        }
        response = requests.put(
            f"{BASE_URL}/api/subyards/invalid-uuid-12345",
            headers=self.headers,
            json=update_payload
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✅ PUT /api/subyards/invalid-id - Correctly returns 404")

    def test_put_announcement_returns_404_for_invalid_id(self):
        """PUT /api/announcements/{invalid_id} returns 404"""
        update_payload = {
            "title": "Should Not Exist",
            "body": "This should fail",
            "scope": "courtyard",
            "subyard_id": ""
        }
        response = requests.put(
            f"{BASE_URL}/api/announcements/invalid-uuid-12345",
            headers=self.headers,
            json=update_payload
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✅ PUT /api/announcements/invalid-id - Correctly returns 404")

    def test_delete_subyard_still_works(self):
        """DELETE /api/subyards/{id} still works after edit feature added"""
        # Create a subyard
        create_payload = {
            "name": f"TEST_DELETE_Subyard_{uuid.uuid4().hex[:6]}",
            "description": "To be deleted",
            "inherited_roles": True,
            "role_focus": ["organizer"],
            "visibility": "shared"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/subyards",
            headers=self.headers,
            json=create_payload
        )
        assert create_response.status_code == 200
        subyard_id = create_response.json()["id"]

        # Delete it
        delete_response = requests.delete(
            f"{BASE_URL}/api/subyards/{subyard_id}",
            headers=self.headers
        )
        assert delete_response.status_code == 200
        print(f"✅ DELETE /api/subyards/{subyard_id} - Successfully deleted")

        # Verify it's gone
        get_response = requests.get(f"{BASE_URL}/api/subyards", headers=self.headers)
        subyards = get_response.json()["subyards"]
        found = next((s for s in subyards if s["id"] == subyard_id), None)
        assert found is None, "Subyard should have been deleted"
        print(f"✅ Verified subyard no longer exists")

    def test_delete_announcement_still_works(self):
        """DELETE /api/announcements/{id} still works after edit feature added"""
        # Create an announcement
        create_payload = {
            "title": f"TEST_DELETE_Announcement_{uuid.uuid4().hex[:6]}",
            "body": "To be deleted",
            "scope": "courtyard",
            "subyard_id": "",
            "attachments": []
        }
        create_response = requests.post(
            f"{BASE_URL}/api/announcements",
            headers=self.headers,
            json=create_payload
        )
        assert create_response.status_code == 200
        announcement_id = create_response.json()["id"]

        # Delete it
        delete_response = requests.delete(
            f"{BASE_URL}/api/announcements/{announcement_id}",
            headers=self.headers
        )
        assert delete_response.status_code == 200
        print(f"✅ DELETE /api/announcements/{announcement_id} - Successfully deleted")

        # Verify it's gone
        get_response = requests.get(f"{BASE_URL}/api/announcements", headers=self.headers)
        announcements = get_response.json()["announcements"]
        found = next((a for a in announcements if a["id"] == announcement_id), None)
        assert found is None, "Announcement should have been deleted"
        print(f"✅ Verified announcement no longer exists")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

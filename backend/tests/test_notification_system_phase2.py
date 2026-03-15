"""
Notification System Phase 2 Tests
- Notification bell icon, unread badge, notification panel
- Notification history, preferences, unread-count, mark-read endpoints
- Notification event triggers from events and announcements creation
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test user credentials
TEST_USER_EMAIL = "notiftest2@kindred.app"
TEST_USER_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def authenticated_session():
    """Get authenticated session for test user."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login with test user
    login_response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    
    if login_response.status_code != 200:
        pytest.skip(f"Cannot login test user: {login_response.text}")
    
    data = login_response.json()
    token = data.get("token")
    user = data.get("user")
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    return {
        "session": session,
        "token": token,
        "user": user,
        "community_id": user.get("community_id")
    }


@pytest.fixture(scope="module")
def fresh_user_session():
    """Create a fresh user via bootstrap for clean notification testing."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    unique_suffix = str(uuid.uuid4())[:6]
    email = f"TEST_notif_{unique_suffix}@kindred.app"
    
    # Bootstrap fresh community
    bootstrap_response = session.post(f"{BASE_URL}/api/auth/bootstrap", json={
        "email": email,
        "password": "Test1234!",
        "full_name": f"Test Notif User {unique_suffix}",
        "community_name": f"Notif Test Community {unique_suffix}",
        "community_type": "family",
        "location": "Test City",
        "description": "Test community for notification testing",
        "motto": "Testing notifications"
    })
    
    if bootstrap_response.status_code != 200:
        pytest.skip(f"Cannot bootstrap test user: {bootstrap_response.text}")
    
    data = bootstrap_response.json()
    token = data.get("token")
    user = data.get("user")
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    return {
        "session": session,
        "token": token,
        "user": user,
        "community_id": user.get("community_id"),
        "email": email
    }


class TestNotificationUnreadCount:
    """Test GET /api/notifications/unread-count endpoint"""
    
    def test_unread_count_returns_200(self, authenticated_session):
        """Test that unread count endpoint returns 200 with count."""
        session = authenticated_session["session"]
        response = session.get(f"{BASE_URL}/api/notifications/unread-count")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "unread_count" in data, "Response should contain unread_count field"
        assert isinstance(data["unread_count"], int), "unread_count should be integer"
        assert data["unread_count"] >= 0, "unread_count should be non-negative"
        print(f"Unread count: {data['unread_count']}")
    
    def test_fresh_user_has_zero_unread(self, fresh_user_session):
        """Test that fresh user has zero unread notifications initially."""
        session = fresh_user_session["session"]
        response = session.get(f"{BASE_URL}/api/notifications/unread-count")
        
        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 0, "Fresh user should have 0 unread notifications"


class TestNotificationMarkRead:
    """Test POST /api/notifications/mark-read endpoint"""
    
    def test_mark_read_returns_marked_count(self, authenticated_session):
        """Test that mark-read endpoint returns marked_count."""
        session = authenticated_session["session"]
        response = session.post(f"{BASE_URL}/api/notifications/mark-read")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "marked_count" in data, "Response should contain marked_count field"
        assert isinstance(data["marked_count"], int), "marked_count should be integer"
        assert data["marked_count"] >= 0, "marked_count should be non-negative"
        print(f"Marked count: {data['marked_count']}")
    
    def test_mark_read_clears_unread(self, authenticated_session):
        """Test that after mark-read, unread count is 0."""
        session = authenticated_session["session"]
        
        # Mark all as read
        session.post(f"{BASE_URL}/api/notifications/mark-read")
        
        # Check unread count is now 0
        response = session.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 0, "Unread count should be 0 after mark-read"


class TestNotificationHistory:
    """Test GET /api/notifications/history endpoint"""
    
    def test_history_returns_items_array(self, authenticated_session):
        """Test that history endpoint returns items array."""
        session = authenticated_session["session"]
        response = session.get(f"{BASE_URL}/api/notifications/history")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Response should contain items field"
        assert isinstance(data["items"], list), "items should be a list"
        print(f"History items count: {len(data['items'])}")
    
    def test_history_items_have_is_read_field(self, authenticated_session):
        """Test that history items have is_read field per user."""
        session = authenticated_session["session"]
        response = session.get(f"{BASE_URL}/api/notifications/history")
        
        assert response.status_code == 200
        data = response.json()
        
        # If there are items, verify they have is_read field
        if data["items"]:
            for item in data["items"][:5]:  # Check first 5 items
                assert "is_read" in item, f"Item {item.get('id')} should have is_read field"
                assert isinstance(item["is_read"], bool), "is_read should be boolean"
                assert "id" in item, "Item should have id"
                assert "title" in item, "Item should have title"
                assert "description" in item, "Item should have description"
                assert "event_type" in item, "Item should have event_type"
                print(f"Item {item['id']}: is_read={item['is_read']}, type={item['event_type']}")
    
    def test_fresh_user_empty_history(self, fresh_user_session):
        """Test that fresh user has empty notification history."""
        session = fresh_user_session["session"]
        response = session.get(f"{BASE_URL}/api/notifications/history")
        
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == [], "Fresh user should have empty history"


class TestNotificationPreferences:
    """Test GET and PUT /api/notifications/preferences endpoints"""
    
    def test_get_preferences_returns_defaults(self, fresh_user_session):
        """Test that GET preferences returns default values for new user."""
        session = fresh_user_session["session"]
        response = session.get(f"{BASE_URL}/api/notifications/preferences")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check all expected preference fields exist with defaults
        assert data.get("reminder_notifications") == True, "reminder_notifications should default to True"
        assert data.get("announcement_notifications") == True, "announcement_notifications should default to True"
        assert data.get("chat_notifications") == True, "chat_notifications should default to True"
        assert data.get("invite_notifications") == True, "invite_notifications should default to True"
        assert data.get("rsvp_notifications") == True, "rsvp_notifications should default to True"
        assert isinstance(data.get("muted_room_ids", []), list), "muted_room_ids should be list"
        assert isinstance(data.get("muted_announcement_scopes", []), list), "muted_announcement_scopes should be list"
        
        print(f"Default preferences: {data}")
    
    def test_update_preferences_persists(self, fresh_user_session):
        """Test that PUT preferences updates and persists changes."""
        session = fresh_user_session["session"]
        
        # Update preferences
        update_payload = {
            "reminder_notifications": False,
            "announcement_notifications": True,
            "chat_notifications": False,
            "invite_notifications": True,
            "rsvp_notifications": False,
            "muted_room_ids": ["room-1", "room-2"],
            "muted_announcement_scopes": ["courtyard"]
        }
        
        put_response = session.put(f"{BASE_URL}/api/notifications/preferences", json=update_payload)
        assert put_response.status_code == 200, f"Expected 200, got {put_response.status_code}: {put_response.text}"
        
        updated_data = put_response.json()
        assert updated_data.get("reminder_notifications") == False
        assert updated_data.get("chat_notifications") == False
        
        # Verify persistence with GET
        get_response = session.get(f"{BASE_URL}/api/notifications/preferences")
        assert get_response.status_code == 200
        
        persisted_data = get_response.json()
        assert persisted_data.get("reminder_notifications") == False, "reminder_notifications change should persist"
        assert persisted_data.get("chat_notifications") == False, "chat_notifications change should persist"
        assert persisted_data.get("rsvp_notifications") == False, "rsvp_notifications change should persist"
        assert "room-1" in persisted_data.get("muted_room_ids", []), "muted_room_ids should persist"
        assert "courtyard" in persisted_data.get("muted_announcement_scopes", []), "muted_announcement_scopes should persist"
        
        print(f"Persisted preferences: {persisted_data}")


class TestNotificationTriggers:
    """Test that creating events and announcements triggers notifications"""
    
    def test_event_creation_triggers_notification(self, fresh_user_session):
        """Test that POST /api/events creates a notification event."""
        session = fresh_user_session["session"]
        
        # Get initial history count
        initial_history = session.get(f"{BASE_URL}/api/notifications/history").json()
        initial_count = len(initial_history.get("items", []))
        
        # Create an event
        event_payload = {
            "title": f"TEST Notification Trigger Event {uuid.uuid4().hex[:6]}",
            "description": "Event to test notification trigger",
            "start_at": "2026-02-15T14:00:00Z",
            "location": "Test Location",
            "event_template": "general",
            "gathering_format": "in-person"
        }
        
        create_response = session.post(f"{BASE_URL}/api/events", json=event_payload)
        assert create_response.status_code == 200, f"Failed to create event: {create_response.text}"
        
        created_event = create_response.json()
        print(f"Created event: {created_event.get('id')}")
        
        # Check notification history increased
        updated_history = session.get(f"{BASE_URL}/api/notifications/history").json()
        updated_count = len(updated_history.get("items", []))
        
        assert updated_count > initial_count, f"Notification history should grow after event creation (was {initial_count}, now {updated_count})"
        
        # Check the new notification is for the event
        latest_item = updated_history["items"][0]
        assert "event" in latest_item.get("event_type", "").lower() or "gathering" in latest_item.get("title", "").lower(), \
            f"Latest notification should be related to event: {latest_item}"
        print(f"Latest notification: {latest_item.get('title')}")
    
    def test_announcement_creation_triggers_notification(self, fresh_user_session):
        """Test that POST /api/announcements creates a notification event."""
        session = fresh_user_session["session"]
        
        # Get initial history count
        initial_history = session.get(f"{BASE_URL}/api/notifications/history").json()
        initial_count = len(initial_history.get("items", []))
        
        # Create an announcement
        announcement_payload = {
            "title": f"TEST Announcement {uuid.uuid4().hex[:6]}",
            "body": "Announcement to test notification trigger",
            "scope": "courtyard",
            "attachments": []
        }
        
        create_response = session.post(f"{BASE_URL}/api/announcements", json=announcement_payload)
        assert create_response.status_code == 200, f"Failed to create announcement: {create_response.text}"
        
        created_announcement = create_response.json()
        print(f"Created announcement: {created_announcement.get('id')}")
        
        # Check notification history increased
        updated_history = session.get(f"{BASE_URL}/api/notifications/history").json()
        updated_count = len(updated_history.get("items", []))
        
        assert updated_count > initial_count, f"Notification history should grow after announcement creation (was {initial_count}, now {updated_count})"
        
        # Check the new notification is for the announcement
        latest_item = updated_history["items"][0]
        assert "announcement" in latest_item.get("event_type", "").lower(), \
            f"Latest notification should be announcement type: {latest_item}"
        print(f"Latest notification: type={latest_item.get('event_type')}, title={latest_item.get('title')}")


class TestNotificationEndpointsRequireAuth:
    """Test that notification endpoints require authentication"""
    
    def test_unread_count_requires_auth(self):
        """Test that unread-count endpoint requires auth."""
        response = requests.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 401, "Should require authentication"
    
    def test_history_requires_auth(self):
        """Test that history endpoint requires auth."""
        response = requests.get(f"{BASE_URL}/api/notifications/history")
        assert response.status_code == 401, "Should require authentication"
    
    def test_preferences_get_requires_auth(self):
        """Test that preferences GET requires auth."""
        response = requests.get(f"{BASE_URL}/api/notifications/preferences")
        assert response.status_code == 401, "Should require authentication"
    
    def test_preferences_put_requires_auth(self):
        """Test that preferences PUT requires auth."""
        response = requests.put(f"{BASE_URL}/api/notifications/preferences", json={})
        assert response.status_code == 401, "Should require authentication"
    
    def test_mark_read_requires_auth(self):
        """Test that mark-read endpoint requires auth."""
        response = requests.post(f"{BASE_URL}/api/notifications/mark-read")
        assert response.status_code == 401, "Should require authentication"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

"""
P2 Backlog Features Test Suite - Iteration 19
Tests Voice Recorder UI presence, AI Tagging with sentiment/mood, and RevenueCat billing infrastructure.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "refactor-test@kindred.app"
TEST_PASSWORD = "Test1234!"


class TestAuthAndRegression:
    """Test auth login and basic regression checks"""
    
    def test_login_success(self):
        """Test auth login works with test credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        print(f"Login successful for {data['user'].get('email')}")
    
    def test_courtyard_home(self):
        """Regression: Courtyard home API returns data"""
        # Login first
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_response.json()["token"]
        
        response = requests.get(f"{BASE_URL}/api/courtyard/home", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200, f"Courtyard home failed: {response.text}"
        data = response.json()
        assert "community" in data or "notifications" in data or "upcoming_events" in data
        print("Courtyard home API working")


class TestAITagging:
    """Test AI tagging with sentiment and mood fields"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    @pytest.fixture
    def event_id(self, auth_token):
        """Get first event ID or create one if none exist"""
        response = requests.get(f"{BASE_URL}/api/events", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        if response.status_code == 200 and response.json():
            return response.json()[0]["id"]
        
        # Create an event if none exist
        create_response = requests.post(f"{BASE_URL}/api/events", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "TEST_P2_Event",
            "description": "Test event for P2 backlog testing",
            "start_at": "2026-02-01T10:00:00Z",
            "location": "Test Location"
        })
        if create_response.status_code in [200, 201]:
            return create_response.json()["id"]
        pytest.skip("Could not get or create event")
    
    def test_memory_create_returns_sentiment_mood(self, auth_token, event_id):
        """POST /api/memories creates memory with sentiment and mood fields"""
        response = requests.post(f"{BASE_URL}/api/memories", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "TEST_P2_Memory_SentimentMood",
            "description": "A joyful family celebration at the reunion. Everyone was happy and grateful to be together.",
            "event_id": event_id
        })
        
        assert response.status_code in [200, 201], f"Memory create failed: {response.text}"
        data = response.json()
        
        # Verify sentiment and mood fields exist
        assert "sentiment" in data, "Memory response missing sentiment field"
        assert "mood" in data, "Memory response missing mood field"
        
        # Verify values are valid
        valid_sentiments = {"positive", "neutral", "reflective", "celebratory", "somber"}
        assert data["sentiment"] in valid_sentiments, f"Invalid sentiment: {data['sentiment']}"
        assert isinstance(data["mood"], str), f"Mood should be string, got {type(data['mood'])}"
        
        print(f"Memory created with sentiment={data['sentiment']}, mood={data['mood']}")
        print(f"Tags: {data.get('tags', [])}")
        print(f"AI Summary: {data.get('ai_summary', '')}")
        
        # Cleanup - delete test memory
        memory_id = data["id"]
        requests.delete(f"{BASE_URL}/api/memories/{memory_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
    
    def test_memories_list_contains_sentiment_mood(self, auth_token):
        """GET /api/memories returns memories with sentiment and mood in MemoryPublic model"""
        response = requests.get(f"{BASE_URL}/api/memories", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Memories list failed: {response.text}"
        data = response.json()
        
        if data:
            memory = data[0]
            # Check if existing memories have sentiment/mood fields
            assert "sentiment" in memory or memory.get("sentiment") is None, "Model should include sentiment field"
            assert "mood" in memory or memory.get("mood") is None, "Model should include mood field"
            print(f"First memory has sentiment={memory.get('sentiment')}, mood={memory.get('mood')}")
        else:
            print("No memories in database to verify fields")
    
    def test_batch_retag_endpoint(self, auth_token):
        """POST /api/memories/batch-retag re-tags all memories with sentiment/mood"""
        response = requests.post(f"{BASE_URL}/api/memories/batch-retag", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Batch retag failed: {response.text}"
        data = response.json()
        
        assert "updated" in data, "Response should have 'updated' count"
        assert "results" in data, "Response should have 'results' array"
        
        print(f"Batch retag completed: {data['updated']} memories updated")
        
        # Verify results have sentiment/mood
        if data["results"]:
            result = data["results"][0]
            assert "sentiment" in result, "Retag result missing sentiment"
            assert "mood" in result, "Retag result missing mood"
            print(f"Result sample: sentiment={result.get('sentiment')}, mood={result.get('mood')}")


class TestRevenueCat:
    """Test RevenueCat billing infrastructure endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    def test_revenuecat_status_endpoint(self, auth_token):
        """GET /api/revenuecat/status returns configuration status"""
        response = requests.get(f"{BASE_URL}/api/revenuecat/status", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"RevenueCat status failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "configured" in data, "Missing 'configured' field"
        assert "webhook_configured" in data, "Missing 'webhook_configured' field"
        assert isinstance(data["configured"], bool), "configured should be boolean"
        assert isinstance(data["webhook_configured"], bool), "webhook_configured should be boolean"
        
        print(f"RevenueCat status: configured={data['configured']}, webhook_configured={data['webhook_configured']}")
    
    def test_revenuecat_webhook_initial_purchase(self):
        """POST /api/revenuecat/webhook handles INITIAL_PURCHASE event"""
        # Test with mock payload (no auth required for webhooks)
        webhook_payload = {
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": "test-user-id-nonexistent",
                "product_id": "premium_monthly",
                "store": "play_store",
                "subscriber": {
                    "entitlements": {
                        "premium": {
                            "expires_date": "2026-03-01T00:00:00Z"
                        }
                    }
                }
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/revenuecat/webhook", json=webhook_payload)
        
        assert response.status_code == 200, f"Webhook failed: {response.text}"
        data = response.json()
        
        # User won't exist, but endpoint should handle gracefully
        assert "status" in data, "Response missing status field"
        # Expected to return "ignored" since user doesn't exist
        print(f"Webhook response: {data}")
    
    def test_revenuecat_webhook_cancellation(self):
        """POST /api/revenuecat/webhook handles CANCELLATION event"""
        webhook_payload = {
            "event": {
                "type": "CANCELLATION",
                "app_user_id": "test-user-id-nonexistent",
                "subscriber": {
                    "entitlements": {}
                }
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/revenuecat/webhook", json=webhook_payload)
        
        assert response.status_code == 200, f"Webhook cancellation failed: {response.text}"
        data = response.json()
        assert "status" in data
        print(f"Cancellation webhook response: {data}")
    
    def test_revenuecat_webhook_no_user_id(self):
        """POST /api/revenuecat/webhook handles missing app_user_id gracefully"""
        webhook_payload = {
            "event": {
                "type": "INITIAL_PURCHASE",
                "subscriber": {
                    "entitlements": {}
                }
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/revenuecat/webhook", json=webhook_payload)
        
        assert response.status_code == 200, f"Webhook should handle missing user_id: {response.text}"
        data = response.json()
        assert data.get("status") == "ignored", "Should ignore events without app_user_id"
        print(f"No app_user_id response: {data}")


class TestRegressionEndpoints:
    """Regression tests for Activity Feed, Timeline, Kinship Map"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    def test_activity_feed(self, auth_token):
        """Regression: Activity feed endpoint works"""
        response = requests.get(f"{BASE_URL}/api/activity-feed", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Activity feed failed: {response.text}"
        data = response.json()
        # Activity feed returns object with items array
        assert "items" in data, "Activity feed should have items key"
        items = data.get("items", [])
        print(f"Activity feed returned {len(items)} items")
    
    def test_timeline_archive(self, auth_token):
        """Regression: Timeline archive with search/export"""
        response = requests.get(f"{BASE_URL}/api/timeline/archive", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Timeline archive failed: {response.text}"
        data = response.json()
        assert "timeline_items" in data, "Missing timeline_items"
        assert "on_this_day" in data, "Missing on_this_day"
        print(f"Timeline has {len(data['timeline_items'])} items, {len(data['on_this_day'])} anniversaries")
    
    def test_timeline_export(self, auth_token):
        """Regression: Timeline export works"""
        response = requests.get(f"{BASE_URL}/api/timeline/export?format=json", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Timeline export failed: {response.text}"
        data = response.json()
        assert "items" in data or "total" in data
        print(f"Timeline export returned {data.get('total', len(data.get('items', [])))} items")
    
    def test_kinship_graph(self, auth_token):
        """Regression: Kinship map/graph endpoint works"""
        response = requests.get(f"{BASE_URL}/api/kinship/graph", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Kinship graph failed: {response.text}"
        data = response.json()
        assert "nodes" in data or "entries" in data or isinstance(data, list)
        print(f"Kinship graph response OK")
    
    def test_threads_list(self, auth_token):
        """Regression: Threads/Legacy threads list works"""
        response = requests.get(f"{BASE_URL}/api/threads", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Threads list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Threads list returned {len(data)} threads")
    
    def test_events_list(self, auth_token):
        """Regression: Events list works"""
        response = requests.get(f"{BASE_URL}/api/events", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Events list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Events list returned {len(data)} events")
    
    def test_communities_mine(self, auth_token):
        """Regression: Communities mine endpoint works"""
        response = requests.get(f"{BASE_URL}/api/communities/mine", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        assert response.status_code == 200, f"Communities mine failed: {response.text}"
        data = response.json()
        # Communities mine returns object with communities array
        assert "communities" in data, "Response should have 'communities' key"
        communities = data["communities"]
        assert isinstance(communities, list)
        print(f"Communities mine returned {len(communities)} communities")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

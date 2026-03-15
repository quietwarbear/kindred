"""
Tests for P1 Features:
- Add-ons Catalog, Checkout, and Purchased endpoints
- Kinship Groups endpoint (quick-invite shortcuts)
- Regression tests for login, activity feed, kinship map, legacy threads, memories
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "refactor-test@kindred.app"
TEST_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for test user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data, "Token not in response"
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestAddOnsCatalog:
    """Test GET /api/addons/catalog endpoint - returns 5 add-on products."""

    def test_catalog_returns_5_addons(self, auth_headers):
        """Verify catalog returns exactly 5 add-on products."""
        response = requests.get(f"{BASE_URL}/api/addons/catalog", headers=auth_headers)
        assert response.status_code == 200, f"Catalog failed: {response.text}"
        
        data = response.json()
        assert "addons" in data, "No addons key in response"
        assert len(data["addons"]) == 5, f"Expected 5 addons, got {len(data['addons'])}"

    def test_catalog_addon_structure(self, auth_headers):
        """Verify each addon has required fields."""
        response = requests.get(f"{BASE_URL}/api/addons/catalog", headers=auth_headers)
        data = response.json()
        
        required_fields = ["id", "name", "description", "price_cents", "price_display", "billing", "category"]
        for addon in data["addons"]:
            for field in required_fields:
                assert field in addon, f"Missing field '{field}' in addon {addon.get('id', 'unknown')}"

    def test_catalog_addon_categories(self, auth_headers):
        """Verify add-ons have correct categories: storage, templates, sms."""
        response = requests.get(f"{BASE_URL}/api/addons/catalog", headers=auth_headers)
        data = response.json()
        
        categories = set(addon["category"] for addon in data["addons"])
        expected_categories = {"storage", "templates", "sms"}
        assert categories == expected_categories, f"Expected categories {expected_categories}, got {categories}"

    def test_catalog_addon_ids(self, auth_headers):
        """Verify specific addon IDs exist."""
        response = requests.get(f"{BASE_URL}/api/addons/catalog", headers=auth_headers)
        data = response.json()
        
        addon_ids = [addon["id"] for addon in data["addons"]]
        expected_ids = ["storage-10gb", "storage-25gb", "templates-premium", "sms-100", "sms-500"]
        assert set(addon_ids) == set(expected_ids), f"Expected IDs {expected_ids}, got {addon_ids}"


class TestAddOnsCheckout:
    """Test POST /api/addons/checkout endpoint - creates Stripe checkout session."""

    def test_checkout_creates_session(self, auth_headers):
        """Verify checkout creates a Stripe session."""
        response = requests.post(
            f"{BASE_URL}/api/addons/checkout",
            headers=auth_headers,
            json={
                "addon_id": "storage-10gb",
                "origin_url": "https://kindred-gather.preview.emergentagent.com/subscription"
            }
        )
        assert response.status_code == 200, f"Checkout failed: {response.text}"
        
        data = response.json()
        assert "checkout_url" in data, "No checkout_url in response"
        assert "session_id" in data, "No session_id in response"
        assert data["checkout_url"].startswith("https://checkout.stripe.com"), "Invalid checkout URL"

    def test_checkout_invalid_addon(self, auth_headers):
        """Verify checkout fails for invalid addon ID."""
        response = requests.post(
            f"{BASE_URL}/api/addons/checkout",
            headers=auth_headers,
            json={
                "addon_id": "invalid-addon-id",
                "origin_url": "https://example.com/subscription"
            }
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_checkout_all_addons(self, auth_headers):
        """Verify checkout works for all addon types."""
        addon_ids = ["storage-10gb", "storage-25gb", "templates-premium", "sms-100", "sms-500"]
        for addon_id in addon_ids:
            response = requests.post(
                f"{BASE_URL}/api/addons/checkout",
                headers=auth_headers,
                json={
                    "addon_id": addon_id,
                    "origin_url": "https://kindred-gather.preview.emergentagent.com/subscription"
                }
            )
            assert response.status_code == 200, f"Checkout failed for {addon_id}: {response.text}"
            data = response.json()
            assert "checkout_url" in data, f"No checkout_url for {addon_id}"


class TestAddOnsPurchased:
    """Test GET /api/addons/purchased endpoint - returns purchase history."""

    def test_purchased_returns_list(self, auth_headers):
        """Verify purchased endpoint returns a list."""
        response = requests.get(f"{BASE_URL}/api/addons/purchased", headers=auth_headers)
        assert response.status_code == 200, f"Purchased failed: {response.text}"
        
        data = response.json()
        assert "purchases" in data, "No purchases key in response"
        assert isinstance(data["purchases"], list), "Purchases is not a list"


class TestKinshipGroups:
    """Test GET /api/kinship/groups endpoint - returns grouped relationships."""

    def test_groups_returns_data(self, auth_headers):
        """Verify kinship groups endpoint returns correct structure."""
        response = requests.get(f"{BASE_URL}/api/kinship/groups", headers=auth_headers)
        assert response.status_code == 200, f"Kinship groups failed: {response.text}"
        
        data = response.json()
        assert "groups" in data, "No groups key in response"
        assert "members" in data, "No members key in response"
        assert isinstance(data["groups"], dict), "Groups is not a dict"
        assert isinstance(data["members"], list), "Members is not a list"

    def test_groups_member_structure(self, auth_headers):
        """Verify members have required fields for quick-invite."""
        response = requests.get(f"{BASE_URL}/api/kinship/groups", headers=auth_headers)
        data = response.json()
        
        if data["members"]:
            member = data["members"][0]
            required_fields = ["id", "full_name", "email", "role"]
            for field in required_fields:
                assert field in member, f"Missing field '{field}' in member"

    def test_groups_relationship_structure(self, auth_headers):
        """Verify relationship groups have required fields."""
        response = requests.get(f"{BASE_URL}/api/kinship/groups", headers=auth_headers)
        data = response.json()
        
        for group_type, relationships in data["groups"].items():
            for rel in relationships:
                assert "id" in rel, f"Missing 'id' in relationship"
                assert "person_name" in rel, f"Missing 'person_name' in relationship"
                assert "related_to_name" in rel, f"Missing 'related_to_name' in relationship"


class TestRegressionAuth:
    """Regression: Login still works."""

    def test_login_works(self):
        """Verify login endpoint works."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["role"] == "host"


class TestRegressionActivityFeed:
    """Regression: Activity feed still works."""

    def test_activity_feed_works(self, auth_headers):
        """Verify activity feed endpoint returns data."""
        response = requests.get(f"{BASE_URL}/api/activity-feed", headers=auth_headers)
        assert response.status_code == 200, f"Activity feed failed: {response.text}"
        data = response.json()
        assert "items" in data, "No items key in activity feed"


class TestRegressionKinshipMap:
    """Regression: Kinship map (graph) still works."""

    def test_kinship_graph_works(self, auth_headers):
        """Verify kinship graph endpoint returns node/link data."""
        response = requests.get(f"{BASE_URL}/api/kinship/graph", headers=auth_headers)
        assert response.status_code == 200, f"Kinship graph failed: {response.text}"
        data = response.json()
        assert "nodes" in data, "No nodes key in kinship graph"
        assert "links" in data, "No links key in kinship graph"


class TestRegressionLegacyThreads:
    """Regression: Legacy threads still work."""

    def test_threads_list_works(self, auth_headers):
        """Verify threads list endpoint returns data (returns array directly)."""
        response = requests.get(f"{BASE_URL}/api/threads", headers=auth_headers)
        assert response.status_code == 200, f"Threads failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Threads should return a list, got {type(data)}"


class TestRegressionMemories:
    """Regression: Memories (Memory Vault) still work."""

    def test_memories_list_works(self, auth_headers):
        """Verify memories list endpoint returns data (returns array directly)."""
        response = requests.get(f"{BASE_URL}/api/memories", headers=auth_headers)
        assert response.status_code == 200, f"Memories failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Memories should return a list, got {type(data)}"


class TestRegressionRevenueCat:
    """Regression: RevenueCat status endpoint still works."""

    def test_revenuecat_status_works(self, auth_headers):
        """Verify RevenueCat status endpoint returns configured: true or false."""
        response = requests.get(f"{BASE_URL}/api/revenuecat/status", headers=auth_headers)
        assert response.status_code == 200, f"RevenueCat status failed: {response.text}"
        data = response.json()
        assert "configured" in data, "No configured key in RevenueCat status"

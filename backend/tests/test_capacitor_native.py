"""
Tests for Capacitor Native Wrapper Setup - Iteration 22
Tests: Push token storage, RevenueCat config/offerings/restore endpoints, 
and ensures all previous features still work (regression).
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "refactor-test@kindred.app"
TEST_PASSWORD = "Test1234!"


class TestPushTokenStorage:
    """Tests for POST /api/auth/push-token endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login to get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_push_token_save_success(self):
        """POST /api/auth/push-token saves device token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/push-token",
            json={"push_token": "test-fcm-token-12345"},
            headers=self.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True

    def test_push_token_empty_returns_false(self):
        """POST /api/auth/push-token with empty token returns ok=False"""
        response = requests.post(
            f"{BASE_URL}/api/auth/push-token",
            json={"push_token": ""},
            headers=self.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == False

    def test_push_token_requires_auth(self):
        """POST /api/auth/push-token requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/auth/push-token",
            json={"push_token": "test-token"},
        )
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403]


class TestRevenueCatConfig:
    """Tests for GET /api/revenuecat/config endpoint (public)"""

    def test_revenuecat_config_returns_bundle_id(self):
        """GET /api/revenuecat/config returns correct bundle_id"""
        response = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert response.status_code == 200
        data = response.json()
        assert data.get("bundle_id") == "com.ubuntumarket.kindred"

    def test_revenuecat_config_returns_entitlements(self):
        """GET /api/revenuecat/config returns entitlement_ids"""
        response = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert response.status_code == 200
        data = response.json()
        assert "entitlement_ids" in data
        assert isinstance(data["entitlement_ids"], list)
        # Should have subscription tiers
        expected_entitlements = ["seedling", "sapling", "oak", "redwood", "elder_grove", "premium"]
        for ent in expected_entitlements:
            assert ent in data["entitlement_ids"]

    def test_revenuecat_config_returns_tier_mapping(self):
        """GET /api/revenuecat/config returns tier_mapping"""
        response = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert response.status_code == 200
        data = response.json()
        assert "tier_mapping" in data
        tier_mapping = data["tier_mapping"]
        assert tier_mapping.get("seedling") == "seedling"
        assert tier_mapping.get("oak") == "oak"
        assert tier_mapping.get("premium") == "oak"  # premium maps to oak

    def test_revenuecat_config_returns_webhook_url(self):
        """GET /api/revenuecat/config returns webhook_url"""
        response = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert response.status_code == 200
        data = response.json()
        assert data.get("webhook_url") == "/api/revenuecat/webhook"

    def test_revenuecat_config_returns_platform(self):
        """GET /api/revenuecat/config returns platform=ios"""
        response = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert response.status_code == 200
        data = response.json()
        assert data.get("platform") == "ios"


class TestRevenueCatOfferings:
    """Tests for GET /api/revenuecat/offerings endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login to get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_revenuecat_offerings_endpoint_exists(self):
        """GET /api/revenuecat/offerings endpoint exists and returns response"""
        response = requests.get(
            f"{BASE_URL}/api/revenuecat/offerings",
            headers=self.headers,
        )
        # Should return 200 (may have error in response if RevenueCat subscriber not found)
        assert response.status_code == 200
        data = response.json()
        # Should have bundle_id even if subscriber not found
        assert "bundle_id" in data or "error" in data or "subscriber" in data

    def test_revenuecat_offerings_requires_auth(self):
        """GET /api/revenuecat/offerings requires authentication"""
        response = requests.get(f"{BASE_URL}/api/revenuecat/offerings")
        assert response.status_code in [401, 403]


class TestRevenueCatRestore:
    """Tests for POST /api/revenuecat/restore endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login to get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_revenuecat_restore_endpoint_exists(self):
        """POST /api/revenuecat/restore endpoint exists and returns response"""
        response = requests.post(
            f"{BASE_URL}/api/revenuecat/restore",
            headers=self.headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should return restored, tier, status, entitlements fields
        assert "restored" in data or "error" in data
        if "restored" in data:
            assert "tier" in data
            assert "status" in data
            assert "entitlements" in data

    def test_revenuecat_restore_requires_auth(self):
        """POST /api/revenuecat/restore requires authentication"""
        response = requests.post(f"{BASE_URL}/api/revenuecat/restore")
        assert response.status_code in [401, 403]


class TestPWAManifest:
    """Tests for PWA manifest accessibility and content"""

    def test_manifest_accessible(self):
        """GET /manifest.json is accessible"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200

    def test_manifest_has_correct_bundle_id(self):
        """manifest.json has correct bundle ID"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == "com.ubuntumarket.kindred"

    def test_manifest_has_correct_name(self):
        """manifest.json has correct name"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200
        data = response.json()
        assert data.get("name") == "Kindred"
        assert data.get("short_name") == "Kindred"


class TestRegressionAuth:
    """Regression tests for authentication"""

    def test_login_works(self):
        """POST /api/auth/login works with test credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL

    def test_auth_me_works(self):
        """GET /api/auth/me works with valid token"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        token = login_resp.json().get("token")
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == TEST_EMAIL


class TestRegressionActivityFeed:
    """Regression tests for activity feed"""

    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_activity_feed_loads(self):
        """GET /api/activity-feed returns activities"""
        response = requests.get(f"{BASE_URL}/api/activity-feed", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestRegressionMemories:
    """Regression tests for memories"""

    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_memories_list_works(self):
        """GET /api/memories returns array"""
        response = requests.get(f"{BASE_URL}/api/memories", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestRegressionKinshipMap:
    """Regression tests for kinship map"""

    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_kinship_graph_works(self):
        """GET /api/kinship/graph returns data"""
        response = requests.get(f"{BASE_URL}/api/kinship/graph", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        # API returns nodes/links format
        assert "nodes" in data
        assert "links" in data


class TestRegressionSubscriptions:
    """Regression tests for subscriptions"""

    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_subscription_plans_works(self):
        """GET /api/subscriptions/plans returns plans"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        # API returns {plans: [...]}
        assert "plans" in data
        assert isinstance(data["plans"], list)

    def test_addons_catalog_works(self):
        """GET /api/addons/catalog returns addons"""
        response = requests.get(f"{BASE_URL}/api/addons/catalog", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        # API returns {addons: [...]}
        assert "addons" in data
        assert isinstance(data["addons"], list)
        assert len(data["addons"]) > 0


class TestRegressionEvents:
    """Regression tests for events/gatherings"""

    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_events_list_works(self):
        """GET /api/events returns array"""
        response = requests.get(f"{BASE_URL}/api/events", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

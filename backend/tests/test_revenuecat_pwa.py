"""Tests for RevenueCat integration and PWA features - Iteration 21."""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://kindred-gather.preview.emergentagent.com").rstrip("/")

TEST_EMAIL = "refactor-test@kindred.app"
TEST_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for authenticated endpoints."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    assert "token" in data, "No token in login response"
    return data["token"]


class TestRevenueCatConfig:
    """Test RevenueCat config endpoint (public)."""

    def test_revenuecat_config_returns_bundle_id(self):
        """GET /api/revenuecat/config returns correct bundle_id."""
        resp = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert resp.status_code == 200, f"Config failed: {resp.text}"
        data = resp.json()
        assert data["bundle_id"] == "com.ubuntumarket.kindred"
        assert "tier_mapping" in data
        assert "seedling" in data["tier_mapping"]
        assert "sapling" in data["tier_mapping"]
        assert "oak" in data["tier_mapping"]
        assert "redwood" in data["tier_mapping"]
        assert "elder_grove" in data["tier_mapping"]
        assert "premium" in data["tier_mapping"]
        assert data["platform"] == "ios"
        print(f"✓ RevenueCat config OK: bundle_id={data['bundle_id']}")

    def test_revenuecat_config_entitlement_ids(self):
        """GET /api/revenuecat/config returns entitlement_ids."""
        resp = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "entitlement_ids" in data
        assert "seedling" in data["entitlement_ids"]
        assert "premium" in data["entitlement_ids"]
        print(f"✓ Entitlement IDs: {data['entitlement_ids']}")

    def test_revenuecat_config_webhook_url(self):
        """GET /api/revenuecat/config includes webhook_url."""
        resp = requests.get(f"{BASE_URL}/api/revenuecat/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["webhook_url"] == "/api/revenuecat/webhook"
        print(f"✓ Webhook URL: {data['webhook_url']}")


class TestRevenueCatStatus:
    """Test RevenueCat status endpoint (requires auth)."""

    def test_revenuecat_status_configured(self, auth_token):
        """GET /api/revenuecat/status returns configured=true."""
        resp = requests.get(
            f"{BASE_URL}/api/revenuecat/status",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200, f"Status failed: {resp.text}"
        data = resp.json()
        assert data["configured"] is True
        print(f"✓ RevenueCat status: configured={data['configured']}, webhook_configured={data.get('webhook_configured')}")


class TestRevenueCatOfferings:
    """Test RevenueCat offerings endpoint (requires auth)."""

    def test_revenuecat_offerings_returns_data(self, auth_token):
        """GET /api/revenuecat/offerings returns subscriber data or error."""
        resp = requests.get(
            f"{BASE_URL}/api/revenuecat/offerings",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        # May return error if subscriber doesn't exist in RevenueCat
        assert resp.status_code == 200, f"Offerings request failed with non-200: {resp.text}"
        data = resp.json()
        # If subscriber exists, we get data; otherwise error message
        assert "bundle_id" in data or "error" in data
        if "error" in data:
            print(f"✓ Offerings returned expected error (subscriber not in RevenueCat): {data['error']}")
        else:
            assert data["bundle_id"] == "com.ubuntumarket.kindred"
            print(f"✓ Offerings: bundle_id={data['bundle_id']}, subscriber={data.get('subscriber')}")


class TestRevenueCatRestore:
    """Test RevenueCat restore endpoint (requires auth)."""

    def test_revenuecat_restore_returns_result(self, auth_token):
        """POST /api/revenuecat/restore returns restore result."""
        resp = requests.post(
            f"{BASE_URL}/api/revenuecat/restore",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        # May fail if subscriber doesn't exist in RevenueCat
        assert resp.status_code == 200, f"Restore request failed: {resp.text}"
        data = resp.json()
        # Either restored or error
        assert "restored" in data or "error" in data
        if "error" in data:
            print(f"✓ Restore returned expected error: {data['error']}")
        else:
            print(f"✓ Restore: restored={data['restored']}, tier={data.get('tier')}, status={data.get('status')}")


class TestRevenueCatWebhook:
    """Test RevenueCat webhook endpoint."""

    def test_webhook_handles_event_without_user(self):
        """POST /api/revenuecat/webhook ignores event without app_user_id."""
        webhook_payload = {
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": "",
                "subscriber": {},
            }
        }
        resp = requests.post(
            f"{BASE_URL}/api/revenuecat/webhook",
            json=webhook_payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "no app_user_id"
        print(f"✓ Webhook correctly ignores event without app_user_id")

    def test_webhook_handles_unknown_user(self):
        """POST /api/revenuecat/webhook ignores unknown user."""
        webhook_payload = {
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": "unknown-user-id-12345",
                "subscriber": {},
            }
        }
        resp = requests.post(
            f"{BASE_URL}/api/revenuecat/webhook",
            json=webhook_payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "user not found"
        print(f"✓ Webhook correctly ignores unknown user")


class TestPWAManifest:
    """Test PWA manifest.json."""

    def test_manifest_accessible(self):
        """GET /manifest.json is accessible."""
        resp = requests.get(f"{BASE_URL}/manifest.json")
        assert resp.status_code == 200, f"Manifest not accessible: {resp.status_code}"
        print("✓ manifest.json accessible")

    def test_manifest_app_name(self):
        """manifest.json has correct app name."""
        resp = requests.get(f"{BASE_URL}/manifest.json")
        data = resp.json()
        assert data["name"] == "Kindred"
        assert data["short_name"] == "Kindred"
        print(f"✓ Manifest name: {data['name']}, short_name: {data['short_name']}")

    def test_manifest_bundle_id(self):
        """manifest.json has correct bundle ID."""
        resp = requests.get(f"{BASE_URL}/manifest.json")
        data = resp.json()
        assert data["id"] == "com.ubuntumarket.kindred"
        print(f"✓ Manifest id (bundle): {data['id']}")

    def test_manifest_icons(self):
        """manifest.json has icons configured."""
        resp = requests.get(f"{BASE_URL}/manifest.json")
        data = resp.json()
        assert "icons" in data
        assert len(data["icons"]) >= 2
        icon_sizes = [i["sizes"] for i in data["icons"]]
        assert "192x192" in icon_sizes
        assert "512x512" in icon_sizes
        print(f"✓ Manifest icons: {icon_sizes}")

    def test_manifest_display_standalone(self):
        """manifest.json has standalone display mode."""
        resp = requests.get(f"{BASE_URL}/manifest.json")
        data = resp.json()
        assert data["display"] == "standalone"
        print(f"✓ Manifest display: {data['display']}")

    def test_manifest_theme_color(self):
        """manifest.json has theme_color."""
        resp = requests.get(f"{BASE_URL}/manifest.json")
        data = resp.json()
        assert data["theme_color"] == "#1a1a2e"
        print(f"✓ Manifest theme_color: {data['theme_color']}")


class TestPWAServiceWorker:
    """Test PWA service worker."""

    def test_sw_accessible(self):
        """GET /sw.js is accessible."""
        resp = requests.get(f"{BASE_URL}/sw.js")
        assert resp.status_code == 200, f"SW not accessible: {resp.status_code}"
        assert "kindred-v1" in resp.text
        print("✓ sw.js accessible and contains CACHE_NAME")

    def test_sw_has_install_handler(self):
        """sw.js has install event handler."""
        resp = requests.get(f"{BASE_URL}/sw.js")
        assert 'addEventListener("install"' in resp.text
        print("✓ sw.js has install handler")

    def test_sw_has_fetch_handler(self):
        """sw.js has fetch event handler."""
        resp = requests.get(f"{BASE_URL}/sw.js")
        assert 'addEventListener("fetch"' in resp.text
        print("✓ sw.js has fetch handler")

    def test_sw_has_offline_fallback(self):
        """sw.js serves offline.html for failed navigations."""
        resp = requests.get(f"{BASE_URL}/sw.js")
        assert "/offline.html" in resp.text
        print("✓ sw.js has offline.html fallback")


class TestPWAOfflinePage:
    """Test PWA offline page."""

    def test_offline_page_accessible(self):
        """GET /offline.html is accessible."""
        resp = requests.get(f"{BASE_URL}/offline.html")
        assert resp.status_code == 200, f"Offline page not accessible: {resp.status_code}"
        print("✓ offline.html accessible")

    def test_offline_page_content(self):
        """offline.html has correct content."""
        resp = requests.get(f"{BASE_URL}/offline.html")
        html = resp.text
        assert "Kindred — Offline" in html
        assert "You're offline" in html
        assert "Try again" in html
        print("✓ offline.html has correct content")

    def test_offline_page_has_icon(self):
        """offline.html references icon."""
        resp = requests.get(f"{BASE_URL}/offline.html")
        assert "/icon-192.png" in resp.text
        print("✓ offline.html has icon reference")


class TestRegressionAuth:
    """Regression: Auth still works."""

    def test_login(self):
        """POST /api/auth/login works."""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "user" in data
        print(f"✓ Login OK: user={data['user'].get('email')}")


class TestRegressionActivityFeed:
    """Regression: Activity Feed still works."""

    def test_activity_feed(self, auth_token):
        """GET /api/activity-feed works."""
        resp = requests.get(
            f"{BASE_URL}/api/activity-feed",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Response uses "items" key
        assert "items" in data
        print(f"✓ Activity Feed OK: {len(data['items'])} activities")


class TestRegressionGatherings:
    """Regression: Gatherings still works."""

    def test_gatherings_list(self, auth_token):
        """GET /api/events works."""
        # Gatherings are at /api/events endpoint
        resp = requests.get(
            f"{BASE_URL}/api/events",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Response is a list directly
        assert isinstance(data, list)
        print(f"✓ Events/Gatherings OK: {len(data)} events")


class TestRegressionMemories:
    """Regression: Memories still works."""

    def test_memories_list(self, auth_token):
        """GET /api/memories works."""
        resp = requests.get(
            f"{BASE_URL}/api/memories",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Returns array directly
        assert isinstance(data, list)
        print(f"✓ Memories OK: {len(data)} memories")


class TestRegressionKinshipMap:
    """Regression: Kinship Map still works."""

    def test_kinship_graph(self, auth_token):
        """GET /api/kinship/graph works."""
        resp = requests.get(
            f"{BASE_URL}/api/kinship/graph",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data or "edges" in data or isinstance(data, dict)
        print(f"✓ Kinship Graph OK")


class TestRegressionAddons:
    """Regression: Add-ons catalog still works."""

    def test_addons_catalog(self, auth_token):
        """GET /api/addons/catalog works."""
        resp = requests.get(
            f"{BASE_URL}/api/addons/catalog",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "addons" in data
        print(f"✓ Add-ons catalog OK: {len(data['addons'])} add-ons")


class TestRegressionSubscriptionPlans:
    """Regression: Subscription plans still work."""

    def test_subscription_current(self, auth_token):
        """GET /api/subscriptions/current works."""
        resp = requests.get(
            f"{BASE_URL}/api/subscriptions/current",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tier" in data or "status" in data
        print(f"✓ Subscription current OK: tier={data.get('tier')}, status={data.get('status')}")

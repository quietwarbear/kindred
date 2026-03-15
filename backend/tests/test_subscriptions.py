"""
Subscription API Tests - Tests for Stripe subscription monetization feature
Testing plans, checkout, cancel, and feature-check endpoints
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials for host user
TEST_EMAIL = "subtest@kindred.app"
TEST_PASSWORD = "testpass123"


class TestSubscriptionEndpoints:
    """Test subscription-related API endpoints."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Authenticate and get token for host user."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code != 200:
            # Try to bootstrap if user doesn't exist
            bootstrap_response = requests.post(f"{BASE_URL}/api/auth/bootstrap", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "full_name": "Subscription Tester",
                "community_name": "Sub Test Community",
                "community_type": "family",
                "location": "Test City",
                "description": "For testing subscriptions"
            })
            if bootstrap_response.status_code in [200, 201]:
                return bootstrap_response.json().get("token")
            pytest.skip("Unable to authenticate host user for subscription tests")
        return response.json().get("token")

    @pytest.fixture(scope="class")
    def member_token(self, auth_token):
        """Create or get a member user token for permission tests."""
        # Create an invite
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        unique_email = f"TEST_member_sub_{os.urandom(4).hex()}@kindred.app"
        
        invite_response = requests.post(f"{BASE_URL}/api/invites", json={
            "email": unique_email,
            "role": "member"
        }, headers=headers)
        
        if invite_response.status_code not in [200, 201]:
            return None
            
        invite_code = invite_response.json().get("code")
        
        # Register with invite
        register_response = requests.post(f"{BASE_URL}/api/auth/register-with-invite", json={
            "email": unique_email,
            "password": "testpass123",
            "full_name": "Member User",
            "invite_code": invite_code
        })
        
        if register_response.status_code in [200, 201]:
            return register_response.json().get("token")
        return None

    # ── GET /api/subscriptions/plans ──
    def test_get_plans_returns_five_plans(self, auth_token):
        """Verify GET /api/subscriptions/plans returns all 5 tier plans."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) == 5
        
        # Verify plan IDs
        plan_ids = [p["id"] for p in data["plans"]]
        assert plan_ids == ["seedling", "sapling", "oak", "redwood", "elder-grove"]

    def test_get_plans_has_correct_prices(self, auth_token):
        """Verify plans have correct monthly and annual prices."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", headers=headers)
        
        assert response.status_code == 200
        plans = {p["id"]: p for p in response.json()["plans"]}
        
        # Verify Seedling: $19/mo
        assert plans["seedling"]["monthly_price"] == 19.00
        assert plans["seedling"]["annual_price"] == 194.00
        assert plans["seedling"]["max_members"] == 10
        
        # Verify Sapling: $49/mo
        assert plans["sapling"]["monthly_price"] == 49.00
        assert plans["sapling"]["annual_price"] == 500.00
        assert plans["sapling"]["max_members"] == 25
        
        # Verify Oak: $79/mo
        assert plans["oak"]["monthly_price"] == 79.00
        assert plans["oak"]["annual_price"] == 806.00
        assert plans["oak"]["max_members"] == 50
        
        # Verify Redwood: $129/mo
        assert plans["redwood"]["monthly_price"] == 129.00
        assert plans["redwood"]["annual_price"] == 1316.00
        assert plans["redwood"]["max_members"] == 100
        
        # Verify Elder Grove: Custom pricing ($0)
        assert plans["elder-grove"]["monthly_price"] == 0.00
        assert plans["elder-grove"]["annual_price"] == 0.00
        assert plans["elder-grove"]["max_members"] == 9999

    def test_get_plans_has_features_and_limits(self, auth_token):
        """Verify each plan has features and limits defined."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", headers=headers)
        
        assert response.status_code == 200
        plans = response.json()["plans"]
        
        for plan in plans:
            assert "features" in plan
            assert isinstance(plan["features"], list)
            assert len(plan["features"]) > 0
            
            assert "limits" in plan
            assert isinstance(plan["limits"], dict)
            assert "max_subyards" in plan["limits"]
            assert "travel_coordination" in plan["limits"]
            assert "shared_funds" in plan["limits"]
            assert "analytics" in plan["limits"]
            assert "custom_branding" in plan["limits"]
            assert "multi_admin" in plan["limits"]

    # ── GET /api/subscriptions/current ──
    def test_get_current_subscription_defaults_to_seedling(self, auth_token):
        """Verify GET /api/subscriptions/current returns tier info even without active subscription."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/subscriptions/current", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return tier info even if no active subscription
        assert "tier" in data
        assert "usage" in data
        
        # Default tier should be seedling
        assert data["tier"]["id"] == "seedling"
        assert data["tier"]["name"] == "Seedling"
        
        # Usage should have member and subyard counts
        assert "member_count" in data["usage"]
        assert "subyard_count" in data["usage"]

    def test_get_current_subscription_requires_auth(self):
        """Verify GET /api/subscriptions/current requires authentication."""
        response = requests.get(f"{BASE_URL}/api/subscriptions/current")
        assert response.status_code == 401

    # ── POST /api/subscriptions/checkout ──
    def test_checkout_creates_session_and_returns_url(self, auth_token):
        """Verify POST /api/subscriptions/checkout creates Stripe checkout session."""
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/subscriptions/checkout", json={
            "plan_id": "sapling",
            "billing_cycle": "monthly",
            "origin_url": "https://circles-gather.preview.emergentagent.com"
        }, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "session_id" in data
        assert data["url"].startswith("http")

    def test_checkout_blocks_non_host_users(self, member_token):
        """Verify POST /api/subscriptions/checkout blocks non-host users with 403."""
        if not member_token:
            pytest.skip("Member token not available")
            
        headers = {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/subscriptions/checkout", json={
            "plan_id": "oak",
            "billing_cycle": "monthly",
            "origin_url": "https://circles-gather.preview.emergentagent.com"
        }, headers=headers)
        
        assert response.status_code == 403

    def test_checkout_returns_400_for_invalid_plan(self, auth_token):
        """Verify POST /api/subscriptions/checkout returns 400 for invalid plan_id."""
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/subscriptions/checkout", json={
            "plan_id": "invalid-tier-xyz",
            "billing_cycle": "monthly",
            "origin_url": "https://circles-gather.preview.emergentagent.com"
        }, headers=headers)
        
        assert response.status_code == 400
        assert "Invalid subscription plan" in response.json().get("detail", "")

    def test_checkout_returns_400_for_elder_grove(self, auth_token):
        """Verify POST /api/subscriptions/checkout returns 400 for elder-grove (contact sales)."""
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/subscriptions/checkout", json={
            "plan_id": "elder-grove",
            "billing_cycle": "monthly",
            "origin_url": "https://circles-gather.preview.emergentagent.com"
        }, headers=headers)
        
        assert response.status_code == 400
        assert "Contact sales" in response.json().get("detail", "") or "Elder Grove" in response.json().get("detail", "")

    def test_checkout_works_with_annual_billing(self, auth_token):
        """Verify checkout works with annual billing cycle."""
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/subscriptions/checkout", json={
            "plan_id": "oak",
            "billing_cycle": "annual",
            "origin_url": "https://circles-gather.preview.emergentagent.com"
        }, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "session_id" in data

    # ── GET /api/subscriptions/checkout/status/{session_id} ──
    def test_checkout_status_returns_404_for_invalid_session(self, auth_token):
        """Verify GET /api/subscriptions/checkout/status returns 404 for invalid session."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/subscriptions/checkout/status/invalid-session-id-xyz", headers=headers)
        
        assert response.status_code == 404

    def test_checkout_status_returns_status_for_valid_session(self, auth_token):
        """Verify GET /api/subscriptions/checkout/status returns status for valid session."""
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        
        # First create a checkout session
        checkout_response = requests.post(f"{BASE_URL}/api/subscriptions/checkout", json={
            "plan_id": "seedling",
            "billing_cycle": "monthly",
            "origin_url": "https://circles-gather.preview.emergentagent.com"
        }, headers=headers)
        
        if checkout_response.status_code != 200:
            pytest.skip("Unable to create checkout session")
            
        session_id = checkout_response.json().get("session_id")
        
        # Now check status
        status_response = requests.get(f"{BASE_URL}/api/subscriptions/checkout/status/{session_id}", headers=headers)
        
        assert status_response.status_code == 200
        data = status_response.json()
        assert "status" in data
        assert "payment_status" in data

    # ── POST /api/subscriptions/cancel ──
    def test_cancel_requires_auth(self):
        """Verify POST /api/subscriptions/cancel requires authentication."""
        response = requests.post(f"{BASE_URL}/api/subscriptions/cancel")
        assert response.status_code == 401

    def test_cancel_returns_400_when_no_active_subscription(self, auth_token):
        """Verify POST /api/subscriptions/cancel returns 400 when no active subscription."""
        headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/subscriptions/cancel", headers=headers)
        
        # Should return 400 if no active subscription exists
        # Or 200 if there is an active subscription to cancel
        assert response.status_code in [200, 400]
        if response.status_code == 400:
            assert "No active subscription" in response.json().get("detail", "")

    def test_cancel_blocks_non_host_users(self, member_token):
        """Verify POST /api/subscriptions/cancel blocks non-host users."""
        if not member_token:
            pytest.skip("Member token not available")
            
        headers = {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/subscriptions/cancel", headers=headers)
        
        assert response.status_code == 403

    # ── GET /api/subscriptions/feature-check/{feature_key} ──
    def test_feature_check_returns_correct_access_for_seedling(self, auth_token):
        """Verify feature-check returns correct access for default seedling tier."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Seedling should NOT have travel_coordination
        response = requests.get(f"{BASE_URL}/api/subscriptions/feature-check/travel_coordination", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["feature_key"] == "travel_coordination"
        assert data["allowed"] == False
        assert data["tier_id"] == "seedling"
        
        # Seedling should NOT have analytics
        response = requests.get(f"{BASE_URL}/api/subscriptions/feature-check/analytics", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] == False
        
        # Seedling should NOT have custom_branding
        response = requests.get(f"{BASE_URL}/api/subscriptions/feature-check/custom_branding", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] == False

    def test_feature_check_returns_max_subyards_limit(self, auth_token):
        """Verify feature-check returns max_subyards limit."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # max_subyards for seedling is 1
        response = requests.get(f"{BASE_URL}/api/subscriptions/feature-check/max_subyards", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["feature_key"] == "max_subyards"
        # For seedling, max_subyards should be 1 (not a boolean)
        assert data["allowed"] == 1

    def test_feature_check_requires_auth(self):
        """Verify feature-check requires authentication."""
        response = requests.get(f"{BASE_URL}/api/subscriptions/feature-check/analytics")
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

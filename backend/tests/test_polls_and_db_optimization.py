"""
Test suite for Polls & Voting feature and DB optimization (aggregation queries)
Tests cover:
1. Polls CRUD operations (create, list, vote, close, delete)
2. Role-based access control (organizer+ for create/close/delete)
3. Voting restrictions (closed poll, single vs multi-select)
4. DB optimization: courtyard/home funds_total, payments/summary total_paid, community/overview funds_raised
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test user credentials from previous iterations
TEST_USER_EMAIL = "notiftest2@kindred.app"
TEST_USER_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for test user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed with status {response.status_code}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


@pytest.fixture(scope="module")
def user_info(authenticated_client, auth_token):
    """Get user info to verify role"""
    response = authenticated_client.get(f"{BASE_URL}/api/community/overview")
    if response.status_code == 200:
        return response.json().get("user", {})
    return {}


class TestPollsList:
    """GET /api/polls - List polls with vote_count and voted_by_me"""

    def test_list_polls_returns_200(self, authenticated_client):
        """Should return 200 and polls array"""
        response = authenticated_client.get(f"{BASE_URL}/api/polls")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "polls" in data, "Response should contain 'polls' key"
        assert isinstance(data["polls"], list), "polls should be a list"

    def test_polls_have_vote_count_per_option(self, authenticated_client):
        """Each poll option should have vote_count field"""
        response = authenticated_client.get(f"{BASE_URL}/api/polls")
        assert response.status_code == 200
        data = response.json()
        for poll in data["polls"]:
            for option in poll.get("options", []):
                assert "vote_count" in option, f"Option {option.get('id')} missing vote_count"
                assert isinstance(option["vote_count"], int), "vote_count should be int"

    def test_polls_have_voted_by_me_per_option(self, authenticated_client):
        """Each poll option should have voted_by_me boolean"""
        response = authenticated_client.get(f"{BASE_URL}/api/polls")
        assert response.status_code == 200
        data = response.json()
        for poll in data["polls"]:
            for option in poll.get("options", []):
                assert "voted_by_me" in option, f"Option {option.get('id')} missing voted_by_me"
                assert isinstance(option["voted_by_me"], bool), "voted_by_me should be bool"

    def test_polls_hide_voter_ids(self, authenticated_client):
        """Polls should NOT expose voter_ids for privacy"""
        response = authenticated_client.get(f"{BASE_URL}/api/polls")
        assert response.status_code == 200
        data = response.json()
        for poll in data["polls"]:
            for option in poll.get("options", []):
                assert "voter_ids" not in option, "voter_ids should be stripped for privacy"

    def test_polls_have_total_votes(self, authenticated_client):
        """Each poll should have total_votes sum"""
        response = authenticated_client.get(f"{BASE_URL}/api/polls")
        assert response.status_code == 200
        data = response.json()
        for poll in data["polls"]:
            assert "total_votes" in poll, "Poll should have total_votes"


class TestPollCreate:
    """POST /api/polls - Create poll (organizer+ only)"""

    def test_create_poll_success(self, authenticated_client, user_info):
        """Should create poll with options"""
        # This test assumes user is organizer or host
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "title": f"TEST_Poll_{unique_id}",
            "description": "Test poll description",
            "options": [
                {"text": "Option A"},
                {"text": "Option B"},
                {"text": "Option C"}
            ],
            "allow_multiple": False,
            "closes_at": ""
        }
        response = authenticated_client.post(f"{BASE_URL}/api/polls", json=payload)
        
        # If user is member role, expect 403
        if user_info.get("role") == "member":
            assert response.status_code == 403, "Members should not be able to create polls"
            pytest.skip("User is member - cannot create polls")
            return
        
        assert response.status_code == 200 or response.status_code == 201, f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == payload["title"]
        assert len(data["options"]) == 3
        assert "id" in data
        assert data["is_active"] is True

    def test_create_poll_requires_min_2_options(self, authenticated_client, user_info):
        """Should reject poll with less than 2 options"""
        if user_info.get("role") == "member":
            pytest.skip("User is member - cannot create polls")
        
        payload = {
            "title": "Single Option Poll",
            "options": [{"text": "Only one option"}],
            "allow_multiple": False
        }
        response = authenticated_client.post(f"{BASE_URL}/api/polls", json=payload)
        assert response.status_code == 422, f"Expected 422 for <2 options, got {response.status_code}"

    def test_create_poll_allows_multiple_option(self, authenticated_client, user_info):
        """Should allow creating multi-select poll"""
        if user_info.get("role") == "member":
            pytest.skip("User is member - cannot create polls")
        
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "title": f"TEST_MultiPoll_{unique_id}",
            "options": [
                {"text": "Choice 1"},
                {"text": "Choice 2"}
            ],
            "allow_multiple": True
        }
        response = authenticated_client.post(f"{BASE_URL}/api/polls", json=payload)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        data = response.json()
        assert data["allow_multiple"] is True


class TestPollVote:
    """POST /api/polls/{id}/vote - Vote on poll"""

    @pytest.fixture(scope="class")
    def test_poll(self, authenticated_client, user_info):
        """Create a test poll for voting tests"""
        if user_info.get("role") == "member":
            # Get existing poll
            response = authenticated_client.get(f"{BASE_URL}/api/polls")
            if response.status_code == 200 and response.json().get("polls"):
                active_polls = [p for p in response.json()["polls"] if p.get("is_active")]
                if active_polls:
                    return active_polls[0]
            pytest.skip("No active polls available for voting test")
        
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "title": f"TEST_VotePoll_{unique_id}",
            "options": [
                {"text": "Vote Option A"},
                {"text": "Vote Option B"}
            ],
            "allow_multiple": False
        }
        response = authenticated_client.post(f"{BASE_URL}/api/polls", json=payload)
        if response.status_code in [200, 201]:
            return response.json()
        pytest.skip("Could not create test poll")

    def test_vote_on_poll_success(self, authenticated_client, test_poll):
        """Should record vote and update counts"""
        if not test_poll:
            pytest.skip("No test poll available")
        
        poll_id = test_poll["id"]
        option_id = test_poll["options"][0]["id"]
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/polls/{poll_id}/vote",
            json={"option_ids": [option_id]}
        )
        assert response.status_code == 200, f"Vote failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify vote was counted
        voted_option = next((o for o in data["options"] if o["id"] == option_id), None)
        assert voted_option is not None
        assert voted_option["voted_by_me"] is True
        assert voted_option["vote_count"] >= 1

    def test_vote_on_nonexistent_poll_returns_404(self, authenticated_client):
        """Should return 404 for invalid poll ID"""
        fake_poll_id = "nonexistent-poll-id-12345"
        response = authenticated_client.post(
            f"{BASE_URL}/api/polls/{fake_poll_id}/vote",
            json={"option_ids": ["some-option"]}
        )
        assert response.status_code == 404

    def test_vote_with_invalid_option_returns_400(self, authenticated_client, test_poll):
        """Should return 400 for invalid option ID"""
        if not test_poll:
            pytest.skip("No test poll available")
        
        poll_id = test_poll["id"]
        response = authenticated_client.post(
            f"{BASE_URL}/api/polls/{poll_id}/vote",
            json={"option_ids": ["invalid-option-id-xyz"]}
        )
        assert response.status_code == 400


class TestPollSingleSelectEnforcement:
    """Test single-select vs multi-select enforcement"""

    @pytest.fixture(scope="class")
    def single_select_poll(self, authenticated_client, user_info):
        """Create a single-select poll"""
        if user_info.get("role") == "member":
            # Try to find existing single-select poll
            response = authenticated_client.get(f"{BASE_URL}/api/polls")
            if response.status_code == 200:
                for poll in response.json().get("polls", []):
                    if poll.get("is_active") and not poll.get("allow_multiple"):
                        return poll
            pytest.skip("No single-select polls available")
        
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "title": f"TEST_SingleSelect_{unique_id}",
            "options": [
                {"text": "Single A"},
                {"text": "Single B"},
                {"text": "Single C"}
            ],
            "allow_multiple": False
        }
        response = authenticated_client.post(f"{BASE_URL}/api/polls", json=payload)
        if response.status_code in [200, 201]:
            return response.json()
        pytest.skip("Could not create single-select poll")

    def test_single_select_rejects_multiple_votes(self, authenticated_client, single_select_poll):
        """Single-select poll should reject multiple option_ids"""
        if not single_select_poll:
            pytest.skip("No single-select poll available")
        
        poll_id = single_select_poll["id"]
        option_ids = [o["id"] for o in single_select_poll["options"][:2]]
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/polls/{poll_id}/vote",
            json={"option_ids": option_ids}
        )
        assert response.status_code == 400, f"Should reject multiple votes on single-select poll, got {response.status_code}"
        assert "single" in response.json().get("detail", "").lower()


class TestPollClose:
    """POST /api/polls/{id}/close - Close poll (organizer+ only)"""

    @pytest.fixture(scope="class")
    def poll_to_close(self, authenticated_client, user_info):
        """Create a poll specifically for close testing"""
        if user_info.get("role") == "member":
            pytest.skip("User is member - cannot close polls")
        
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "title": f"TEST_ClosePoll_{unique_id}",
            "options": [
                {"text": "Close Option A"},
                {"text": "Close Option B"}
            ]
        }
        response = authenticated_client.post(f"{BASE_URL}/api/polls", json=payload)
        if response.status_code in [200, 201]:
            return response.json()
        pytest.skip("Could not create poll for close test")

    def test_close_poll_success(self, authenticated_client, poll_to_close):
        """Should close the poll"""
        if not poll_to_close:
            pytest.skip("No poll available to close")
        
        poll_id = poll_to_close["id"]
        response = authenticated_client.post(f"{BASE_URL}/api/polls/{poll_id}/close")
        assert response.status_code == 200, f"Close failed: {response.text}"
        assert response.json().get("status") == "closed"

    def test_vote_on_closed_poll_returns_error(self, authenticated_client, poll_to_close):
        """Should return error when voting on closed poll"""
        if not poll_to_close:
            pytest.skip("No poll available")
        
        poll_id = poll_to_close["id"]
        option_id = poll_to_close["options"][0]["id"]
        
        # First ensure it's closed
        authenticated_client.post(f"{BASE_URL}/api/polls/{poll_id}/close")
        
        # Try to vote
        response = authenticated_client.post(
            f"{BASE_URL}/api/polls/{poll_id}/vote",
            json={"option_ids": [option_id]}
        )
        assert response.status_code == 400, f"Should reject vote on closed poll, got {response.status_code}"
        assert "closed" in response.json().get("detail", "").lower()


class TestPollDelete:
    """DELETE /api/polls/{id} - Delete poll (organizer+ only)"""

    def test_delete_poll_success(self, authenticated_client, user_info):
        """Should delete the poll"""
        if user_info.get("role") == "member":
            pytest.skip("User is member - cannot delete polls")
        
        # Create a poll to delete
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "title": f"TEST_DeletePoll_{unique_id}",
            "options": [
                {"text": "Delete Option A"},
                {"text": "Delete Option B"}
            ]
        }
        create_response = authenticated_client.post(f"{BASE_URL}/api/polls", json=payload)
        assert create_response.status_code in [200, 201]
        poll_id = create_response.json()["id"]
        
        # Delete it
        response = authenticated_client.delete(f"{BASE_URL}/api/polls/{poll_id}")
        assert response.status_code == 200, f"Delete failed: {response.text}"
        assert response.json().get("status") == "deleted"
        
        # Verify it's gone
        list_response = authenticated_client.get(f"{BASE_URL}/api/polls")
        polls = list_response.json().get("polls", [])
        assert not any(p["id"] == poll_id for p in polls), "Deleted poll should not appear in list"

    def test_delete_nonexistent_poll_returns_404(self, authenticated_client, user_info):
        """Should return 404 for invalid poll ID"""
        if user_info.get("role") == "member":
            pytest.skip("User is member - cannot delete polls")
        
        response = authenticated_client.delete(f"{BASE_URL}/api/polls/nonexistent-poll-xyz")
        assert response.status_code == 404


class TestDBOptimizationCourtyardHome:
    """GET /api/courtyard/home - Should return funds_total using aggregation"""

    def test_courtyard_home_returns_funds_total(self, authenticated_client):
        """Should include funds_total in stats"""
        response = authenticated_client.get(f"{BASE_URL}/api/courtyard/home")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "stats" in data, "Response should have stats"
        assert "funds_total" in data["stats"], "Stats should include funds_total"
        assert isinstance(data["stats"]["funds_total"], (int, float)), "funds_total should be numeric"

    def test_courtyard_home_response_structure(self, authenticated_client):
        """Verify complete response structure"""
        response = authenticated_client.get(f"{BASE_URL}/api/courtyard/home")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "courtyard" in data
        assert "user" in data
        assert "stats" in data
        assert "upcoming_gatherings" in data
        assert "active_courtyards" in data


class TestDBOptimizationPaymentsSummary:
    """GET /api/payments/summary - Should return total_paid using aggregation"""

    def test_payments_summary_returns_total_paid(self, authenticated_client):
        """Should include total_paid"""
        response = authenticated_client.get(f"{BASE_URL}/api/payments/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "total_paid" in data, "Response should have total_paid"
        assert isinstance(data["total_paid"], (int, float)), "total_paid should be numeric"

    def test_payments_summary_includes_transactions(self, authenticated_client):
        """Should include transactions list"""
        response = authenticated_client.get(f"{BASE_URL}/api/payments/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "transactions" in data
        assert isinstance(data["transactions"], list)

    def test_payments_summary_includes_packages(self, authenticated_client):
        """Should include available packages"""
        response = authenticated_client.get(f"{BASE_URL}/api/payments/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "packages" in data
        assert isinstance(data["packages"], list)


class TestDBOptimizationCommunityOverview:
    """GET /api/community/overview - Should return funds_raised using aggregation"""

    def test_community_overview_returns_funds_raised(self, authenticated_client):
        """Should include funds_raised in stats"""
        response = authenticated_client.get(f"{BASE_URL}/api/community/overview")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "stats" in data, "Response should have stats"
        assert "funds_raised" in data["stats"], "Stats should include funds_raised"
        assert isinstance(data["stats"]["funds_raised"], (int, float)), "funds_raised should be numeric"

    def test_community_overview_complete_stats(self, authenticated_client):
        """Verify all stats fields are present"""
        response = authenticated_client.get(f"{BASE_URL}/api/community/overview")
        assert response.status_code == 200
        data = response.json()
        
        stats = data["stats"]
        expected_stats = ["members", "events", "memories", "threads", "funds_raised"]
        for stat in expected_stats:
            assert stat in stats, f"Stats should include {stat}"


class TestCleanup:
    """Cleanup TEST_ prefixed polls after tests"""

    def test_cleanup_test_polls(self, authenticated_client, user_info):
        """Delete all TEST_ prefixed polls created during testing"""
        if user_info.get("role") == "member":
            pytest.skip("User is member - cannot delete polls")
        
        response = authenticated_client.get(f"{BASE_URL}/api/polls")
        if response.status_code == 200:
            polls = response.json().get("polls", [])
            for poll in polls:
                if poll.get("title", "").startswith("TEST_"):
                    authenticated_client.delete(f"{BASE_URL}/api/polls/{poll['id']}")
        
        # This test always passes - cleanup is best-effort
        assert True

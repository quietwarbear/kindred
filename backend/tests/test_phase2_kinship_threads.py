"""
Phase 2 Backend Tests: Kinship Map and Legacy Threads
- Kinship Graph API: GET /api/kinship/graph returns nodes/links for visualization
- Kinship CRUD: POST /api/kinship creates relationship, DELETE /api/kinship/{id} removes it
- Kinship Groups: GET /api/kinship/groups returns grouped relationships
- Legacy Threads: GET /api/threads returns thread list
- Legacy Threads: POST /api/threads creates new thread with category
- Legacy Threads: POST /api/threads/{id}/comments adds comment
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPhase2KinshipAndThreads:
    """Phase 2 Feature Tests: Kinship Map and Legacy Threads"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        return data["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    # ================== KINSHIP GRAPH TESTS ==================
    
    def test_kinship_graph_returns_structure(self, auth_headers):
        """GET /api/kinship/graph returns nodes/links for network graph"""
        response = requests.get(f"{BASE_URL}/api/kinship/graph", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "nodes" in data
        assert "links" in data
        assert "relationship_types" in data
        assert "total_nodes" in data
        assert "total_links" in data
        
        # nodes and links should be lists
        assert isinstance(data["nodes"], list)
        assert isinstance(data["links"], list)
        assert isinstance(data["relationship_types"], list)
        print(f"Kinship graph: {data['total_nodes']} nodes, {data['total_links']} links")
    
    def test_kinship_list_returns_relationships(self, auth_headers):
        """GET /api/kinship returns relationships list"""
        response = requests.get(f"{BASE_URL}/api/kinship", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "relationships" in data
        assert isinstance(data["relationships"], list)
        print(f"Kinship list: {len(data['relationships'])} relationships")
    
    # ================== KINSHIP CRUD TESTS ==================
    
    def test_create_kinship_relationship(self, auth_headers):
        """POST /api/kinship creates a new relationship"""
        payload = {
            "person_name": "TEST_Alice",
            "related_to_name": "TEST_Bob",
            "relationship_type": "sibling",
            "relationship_scope": "family",
            "notes": "Test kinship relationship",
            "last_seen_at": ""
        }
        response = requests.post(f"{BASE_URL}/api/kinship", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response
        assert "id" in data
        assert data["person_name"] == "TEST_Alice"
        assert data["related_to_name"] == "TEST_Bob"
        assert data["relationship_type"] == "sibling"
        assert data["relationship_scope"] == "family"
        print(f"Created kinship: {data['id']}")
        return data["id"]
    
    def test_kinship_appears_in_graph_after_create(self, auth_headers):
        """Verify created kinship appears in graph"""
        # First create
        payload = {
            "person_name": "TEST_GraphNode1",
            "related_to_name": "TEST_GraphNode2",
            "relationship_type": "cousin",
            "relationship_scope": "extended",
            "notes": "Graph test"
        }
        create_resp = requests.post(f"{BASE_URL}/api/kinship", headers=auth_headers, json=payload)
        assert create_resp.status_code == 200
        kinship_id = create_resp.json()["id"]
        
        # Verify in graph
        graph_resp = requests.get(f"{BASE_URL}/api/kinship/graph", headers=auth_headers)
        assert graph_resp.status_code == 200
        graph_data = graph_resp.json()
        
        # Check nodes contain the new names
        node_ids = [n["id"] for n in graph_data["nodes"]]
        assert "TEST_GraphNode1" in node_ids, "Person not in graph nodes"
        assert "TEST_GraphNode2" in node_ids, "Related person not in graph nodes"
        
        # Check links contain the relationship
        link_ids = [l.get("kinship_id") for l in graph_data["links"]]
        assert kinship_id in link_ids, "Kinship link not in graph"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/kinship/{kinship_id}", headers=auth_headers)
        print("Kinship appears in graph after create - PASS")
    
    def test_delete_kinship_relationship(self, auth_headers):
        """DELETE /api/kinship/{id} removes relationship"""
        # First create
        payload = {
            "person_name": "TEST_ToDelete1",
            "related_to_name": "TEST_ToDelete2",
            "relationship_type": "friend",
            "relationship_scope": "community"
        }
        create_resp = requests.post(f"{BASE_URL}/api/kinship", headers=auth_headers, json=payload)
        assert create_resp.status_code == 200
        kinship_id = create_resp.json()["id"]
        
        # Delete
        delete_resp = requests.delete(f"{BASE_URL}/api/kinship/{kinship_id}", headers=auth_headers)
        assert delete_resp.status_code == 200
        assert delete_resp.json().get("ok") == True
        
        # Verify not in list
        list_resp = requests.get(f"{BASE_URL}/api/kinship", headers=auth_headers)
        relationships = list_resp.json().get("relationships", [])
        rel_ids = [r["id"] for r in relationships]
        assert kinship_id not in rel_ids, "Deleted kinship still in list"
        print("Kinship delete - PASS")
    
    def test_delete_nonexistent_kinship_returns_404(self, auth_headers):
        """DELETE /api/kinship/{non_existent_id} returns 404"""
        response = requests.delete(f"{BASE_URL}/api/kinship/nonexistent-id-12345", headers=auth_headers)
        assert response.status_code == 404
        print("Delete nonexistent kinship returns 404 - PASS")
    
    # ================== KINSHIP GROUPS TESTS ==================
    
    def test_kinship_groups_returns_grouped_data(self, auth_headers):
        """GET /api/kinship/groups returns grouped relationships"""
        response = requests.get(f"{BASE_URL}/api/kinship/groups", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "groups" in data
        assert "members" in data
        assert isinstance(data["groups"], dict)
        assert isinstance(data["members"], list)
        print(f"Kinship groups: {len(data['groups'])} groups, {len(data['members'])} members")
    
    def test_kinship_groups_contain_created_relationships(self, auth_headers):
        """Verify created kinships appear in groups"""
        # Create a parent relationship
        payload = {
            "person_name": "TEST_Parent",
            "related_to_name": "TEST_Child",
            "relationship_type": "parent",
            "relationship_scope": "family"
        }
        create_resp = requests.post(f"{BASE_URL}/api/kinship", headers=auth_headers, json=payload)
        assert create_resp.status_code == 200
        kinship_id = create_resp.json()["id"]
        
        # Check groups
        groups_resp = requests.get(f"{BASE_URL}/api/kinship/groups", headers=auth_headers)
        assert groups_resp.status_code == 200
        groups_data = groups_resp.json()
        
        # Parent group should exist
        assert "parent" in groups_data["groups"], "Parent group not found"
        parent_group = groups_data["groups"]["parent"]
        rel_ids = [r["id"] for r in parent_group]
        assert kinship_id in rel_ids, "Created kinship not in parent group"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/kinship/{kinship_id}", headers=auth_headers)
        print("Kinship groups contain created relationships - PASS")
    
    # ================== LEGACY THREADS LIST TESTS ==================
    
    def test_threads_list_returns_threads(self, auth_headers):
        """GET /api/threads returns thread list"""
        response = requests.get(f"{BASE_URL}/api/threads", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Response is a list of threads
        assert isinstance(data, list)
        print(f"Threads list: {len(data)} threads")
    
    # ================== LEGACY THREADS CREATE TESTS ==================
    
    def test_create_thread_with_category(self, auth_headers):
        """POST /api/threads creates new thread with category"""
        payload = {
            "title": "TEST_Legacy_Thread_Title",
            "body": "This is a test legacy thread body for testing purposes.",
            "category": "oral-history",
            "elder_name": "TEST_Elder",
            "tags": ["test", "legacy"]
        }
        response = requests.post(f"{BASE_URL}/api/threads", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response
        assert "id" in data
        assert data["title"] == "TEST_Legacy_Thread_Title"
        assert data["body"] == "This is a test legacy thread body for testing purposes."
        assert data["category"] == "oral-history"
        assert data["elder_name"] == "TEST_Elder"
        assert "comments" in data
        assert isinstance(data["comments"], list)
        print(f"Created thread: {data['id']}")
        return data["id"]
    
    def test_create_thread_different_categories(self, auth_headers):
        """Test creating threads with different categories"""
        categories = ["sermon", "youth-reflection", "family-lore", "migration-story"]
        created_ids = []
        
        for category in categories:
            payload = {
                "title": f"TEST_Thread_{category}",
                "body": f"Test body for {category} category.",
                "category": category,
                "tags": []
            }
            response = requests.post(f"{BASE_URL}/api/threads", headers=auth_headers, json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["category"] == category
            created_ids.append(data["id"])
        
        print(f"Created threads with categories: {categories}")
        # No cleanup needed - threads don't have delete endpoint visible
    
    def test_thread_appears_in_list_after_create(self, auth_headers):
        """Verify created thread appears in thread list"""
        # Create thread
        payload = {
            "title": "TEST_VerifyInList",
            "body": "Thread body for list verification.",
            "category": "community-dialogue",
            "tags": []
        }
        create_resp = requests.post(f"{BASE_URL}/api/threads", headers=auth_headers, json=payload)
        assert create_resp.status_code == 200
        thread_id = create_resp.json()["id"]
        
        # Verify in list
        list_resp = requests.get(f"{BASE_URL}/api/threads", headers=auth_headers)
        assert list_resp.status_code == 200
        threads = list_resp.json()
        thread_ids = [t["id"] for t in threads]
        assert thread_id in thread_ids, "Created thread not in list"
        print("Thread appears in list after create - PASS")
    
    # ================== LEGACY THREADS COMMENTS TESTS ==================
    
    def test_add_comment_to_thread(self, auth_headers):
        """POST /api/threads/{id}/comments adds comment to thread"""
        # First create a thread
        thread_payload = {
            "title": "TEST_Thread_For_Comments",
            "body": "Thread body for comment testing.",
            "category": "recipe-tradition",
            "tags": []
        }
        create_resp = requests.post(f"{BASE_URL}/api/threads", headers=auth_headers, json=thread_payload)
        assert create_resp.status_code == 200
        thread_id = create_resp.json()["id"]
        
        # Add comment
        comment_payload = {"text": "This is a test comment on the thread."}
        comment_resp = requests.post(
            f"{BASE_URL}/api/threads/{thread_id}/comments",
            headers=auth_headers,
            json=comment_payload
        )
        assert comment_resp.status_code == 200
        data = comment_resp.json()
        
        # Verify response has updated comments
        assert "comments" in data
        assert len(data["comments"]) >= 1
        
        # Check latest comment
        latest_comment = data["comments"][-1]
        assert latest_comment["text"] == "This is a test comment on the thread."
        assert "author_name" in latest_comment
        assert "id" in latest_comment
        print(f"Added comment to thread {thread_id}")
    
    def test_add_multiple_comments_to_thread(self, auth_headers):
        """Test adding multiple comments to a single thread"""
        # Create thread
        thread_payload = {
            "title": "TEST_Thread_Multiple_Comments",
            "body": "Thread body for multiple comment testing.",
            "category": "oral-history",
            "tags": []
        }
        create_resp = requests.post(f"{BASE_URL}/api/threads", headers=auth_headers, json=thread_payload)
        assert create_resp.status_code == 200
        thread_id = create_resp.json()["id"]
        
        # Add 3 comments
        for i in range(3):
            comment_payload = {"text": f"Comment number {i+1}"}
            comment_resp = requests.post(
                f"{BASE_URL}/api/threads/{thread_id}/comments",
                headers=auth_headers,
                json=comment_payload
            )
            assert comment_resp.status_code == 200
        
        # Verify all comments present
        threads_resp = requests.get(f"{BASE_URL}/api/threads", headers=auth_headers)
        threads = threads_resp.json()
        thread = next((t for t in threads if t["id"] == thread_id), None)
        assert thread is not None
        assert len(thread["comments"]) >= 3
        print("Multiple comments added - PASS")
    
    # ================== REGRESSION TESTS ==================
    
    def test_regression_auth_login_works(self):
        """Regression: Auth login still works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "refactor-test@kindred.app",
            "password": "Test1234!"
        })
        assert response.status_code == 200
        assert "token" in response.json()
        print("Regression: Auth login - PASS")
    
    def test_regression_events_list_works(self, auth_headers):
        """Regression: Events list still works"""
        response = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        assert response.status_code == 200
        print("Regression: Events list - PASS")
    
    def test_regression_memories_list_works(self, auth_headers):
        """Regression: Memories list still works"""
        response = requests.get(f"{BASE_URL}/api/memories", headers=auth_headers)
        assert response.status_code == 200
        print("Regression: Memories list - PASS")
    
    def test_regression_activity_feed_works(self, auth_headers):
        """Regression: Activity feed still works"""
        response = requests.get(f"{BASE_URL}/api/activity-feed", headers=auth_headers)
        assert response.status_code == 200
        print("Regression: Activity feed - PASS")
    
    def test_regression_timeline_export_works(self, auth_headers):
        """Regression: Timeline CSV export still works"""
        response = requests.get(f"{BASE_URL}/api/timeline/export?format=csv", headers=auth_headers)
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        print("Regression: Timeline export - PASS")
    
    # ================== CLEANUP ==================
    
    @pytest.fixture(scope="class", autouse=True)
    def cleanup_test_kinships(self, auth_headers):
        """Cleanup TEST_ prefixed kinships after tests"""
        yield
        # Cleanup kinships with TEST_ prefix
        try:
            list_resp = requests.get(f"{BASE_URL}/api/kinship", headers=auth_headers)
            if list_resp.status_code == 200:
                relationships = list_resp.json().get("relationships", [])
                for rel in relationships:
                    if rel.get("person_name", "").startswith("TEST_") or rel.get("related_to_name", "").startswith("TEST_"):
                        requests.delete(f"{BASE_URL}/api/kinship/{rel['id']}", headers=auth_headers)
                        print(f"Cleaned up kinship: {rel['id']}")
        except Exception as e:
            print(f"Cleanup error: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

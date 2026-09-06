import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.web.app import create_app
from app.core.network import NetworkScienceCache
import os

@pytest_asyncio.fixture
async def client():
    app = create_app()
    # Setup test public content directory if it doesn't exist
    content_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "content", "public")
    os.makedirs(content_dir, exist_ok=True)
    test_file = os.path.join(content_dir, "test-item.md")
    with open(test_file, "w") as f:
        f.write("---\n")
        f.write("title: Test Public Item\n")
        f.write("summary: This is a test summary\n")
        f.write("tags: [\"test\", \"agent\"]\n")
        f.write("---\n")
        f.write("Test content <script>alert('unsafe')</script>\n")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Teardown
    if os.path.exists(test_file):
        os.remove(test_file)


@pytest.mark.asyncio
async def test_llms_txt(client):
    response = await client.get("/llms.txt")
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "abtahi.fyi" in response.text
    assert "/openapi.json" in response.text


@pytest.mark.asyncio
async def test_feed_json(client):
    response = await client.get("/feed.json")
    assert response.status_code == 200
    assert "application/feed+json" in response.headers["content-type"]
    data = response.json()
    assert data["version"] == "https://jsonfeed.org/version/1.1"
    assert "items" in data
    
    # Check that our test item is present
    items = data["items"]
    assert len(items) > 0
    test_item = next((i for i in items if i["id"] == "test-item"), None)
    assert test_item is not None
    assert test_item["title"] == "Test Public Item"
    assert "_fyi" in test_item
    assert "test" in test_item["_fyi"]["tags"]


@pytest.mark.asyncio
async def test_openapi_filters_private_routes(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema.get("paths", {})
    
    # Public routes should be present
    assert "/feed.json" in paths
    assert "/llms.txt" in paths

    # Private study and privileged operations routes should NOT be present
    assert "/study" not in paths
    assert "/capture" not in paths
    assert "/api/poll-feeds" not in paths
    assert "/api/consolidate" not in paths
    assert "/admin" not in paths

    # Schemas must not expose consent tokens, private archives, or credentials
    schema_str = response.text.lower()
    assert "csrf_secret" not in schema_str
    assert "consent_token" not in schema_str
    assert "study_archive" not in schema_str
    assert "scheduler_service_account" not in schema_str

@pytest.mark.asyncio
async def test_error_response_privacy_leakage(client):
    # Test 404 response
    response = await client.get("/non-existent-random-path")
    assert response.status_code == 404
    body = response.text.lower()
    assert "traceback" not in body
    assert "secret" not in body
    assert "private" not in body
    assert "token" not in body


@pytest.mark.asyncio
async def test_timeline(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Test Public Item" in response.text

@pytest.mark.asyncio
async def test_permalink(client):
    response = await client.get("/i/test-item")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Test Public Item" in response.text
    assert "Test content" in response.text
    assert "<script>alert('unsafe')</script>" not in response.text
    assert "&lt;script&gt;alert('unsafe')&lt;/script&gt;" in response.text

@pytest.mark.asyncio
async def test_graph_routes(client):
    for route in ["/graph", "/connected", "/themes", "/tensions"]:
        response = await client.get(route)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_public_navigation_does_not_expose_private_study_route(client):
    response = await client.get("/")

    assert 'href="/today"' not in response.text

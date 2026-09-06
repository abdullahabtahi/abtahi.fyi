from fastapi.testclient import TestClient
from app.web.app import create_app


def test_agents_page_renders_cleanly():
    app = create_app()
    client = TestClient(app)
    response = client.get("/agents")
    assert response.status_code == 200
    assert "Instructions for Your Agent" in response.text
    assert "Copy agent instructions" in response.text
    assert "instructions" in response.text


def test_agent_context_contains_required_sections():
    app = create_app()
    client = TestClient(app)
    response = client.get("/agents")
    assert response.status_code == 200

    html = response.text
    # 1. Author and site context
    assert "Abdullah Abtahi" in html
    assert "abtahi.fyi" in html
    assert "riff" in html
    assert "link" in html
    assert "essay" in html

    # 2. Access channels
    assert "/feed.json" in html
    assert "/feed.xml" in html
    assert "/llms.txt" in html

    # 3. Public Query API endpoints
    assert "/api/fyi/q/search" in html
    assert "/api/fyi/q/semantic" in html
    assert "/api/fyi/q/items" in html
    assert "/api/fyi/q/edges" in html
    assert "/api/fyi/q/summary" in html

    # 4. Agent reasoning guidelines
    assert "How to answer common questions" in html or "What should you do with this" in html

    # 5. Developer footer links
    assert "For agents &amp; developers" in html or "For agents & developers" in html
    assert "/docs" in html
    assert "/openapi.json" in html


def test_agent_context_does_not_leak_private_study_data():
    app = create_app()
    client = TestClient(app)
    response = client.get("/agents")
    assert response.status_code == 200

    html = response.text
    # Verify no private study paths or terms leak into agent context
    assert "/study/ingest" not in html
    assert "/today" not in html
    assert "/api/study" not in html
    assert "/api/proposals" not in html
    assert "pending_proposals" not in html


def test_graph_page_renders_with_accessible_table():
    app = create_app()
    client = TestClient(app)
    response = client.get("/graph")
    assert response.status_code == 200
    html = response.text
    assert "Network Map" in html
    assert "graph-container" in html
    assert "zoom-in-btn" in html
    assert "zoom-out-btn" in html
    assert "zoom-reset-btn" in html
    assert "Concept &amp; Community Index" in html or "Concept & Community Index" in html
    assert "<table" in html


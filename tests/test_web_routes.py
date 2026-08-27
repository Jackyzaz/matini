import pytest
from matini.web import create_app

@pytest.fixture
def web_client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()

def test_homepage_registry_render(web_client):
    response = web_client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "AI Registry &amp; Guardrail Marketplace" in html or "AI Registry & Guardrail Marketplace" in html
    assert "Claude Sentinel Pro" in html
    assert "DeepSeek Coder X" in html
    assert "FinGuard Intelligence" in html

def test_model_detail_page_render(web_client):
    response = web_client.get("/model/claude-sentinel-v1")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Claude Sentinel Pro" in html
    assert "Sandboxed Interactive Console" in html
    assert "Guardrail Policy Manager" in html
    assert "model_chat.py" in html

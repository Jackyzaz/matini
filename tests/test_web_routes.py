import pytest
import requests

from matini.web import create_app
from matini.web.views import assessment as assessment_view


@pytest.fixture
def web_client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_home_is_chat_ui(web_client):
    html = web_client.get("/").data.decode("utf-8")
    assert 'id="prompt_input"' in html
    assert 'id="llm_select"' in html
    assert "chat.py" in html
    assert "uardrail" not in html  # guardrail UI is gone


def test_conversation_url_serves_chat_ui(web_client):
    html = web_client.get("/c/abc123").data.decode("utf-8")
    assert 'id="initial_conversation_id" value="abc123"' in html


def test_admin_page(web_client):
    html = web_client.get("/admin/").data.decode("utf-8")
    assert 'id="llm_form"' in html
    assert "admin.py" in html
    assert 'id="f_size"' in html


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_assessment_page_has_progress_bar(web_client, monkeypatch):
    criterion = {
        "id": "g1", "nist_function": "GOVERN", "nist_category": "GOVERN 1",
        "ethics_dimension": "Bias & Fairness", "title": "Policies", "guiding_question": "?", "probe_prompt": None,
    }
    llm = {"id": "abc", "name": "Test LLM", "provider": "ollama", "model_name": "llama3.1", "parameter_size_b": 8.0}

    def fake_get(url, timeout=None):
        if url.endswith("/api/llms/abc"):
            return FakeResponse(200, llm)
        if url.endswith("/api/assessment/criteria"):
            return FakeResponse(200, [criterion])
        return FakeResponse(404, {})

    monkeypatch.setattr(assessment_view.requests, "get", fake_get)
    html = web_client.get("/assessment/abc").data.decode("utf-8")
    assert 'id="progress_bar"' in html
    assert ">8B</span>" in html  # parameter-size badge
    assert 'data-llm-id="abc"' in html
    assert "assessment.py" in html


def test_assessment_page_404_for_unknown_llm(web_client, monkeypatch):
    monkeypatch.setattr(assessment_view.requests, "get", lambda url, timeout=None: FakeResponse(404, {}))
    assert web_client.get("/assessment/nope").status_code == 404

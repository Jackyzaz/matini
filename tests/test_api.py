import json
import time

import pytest

from matini.api.services import local_llm


def create_llm(client, **overrides):
    body = {"name": "Test LLM", "model_name": "llama3.1", **overrides}
    res = client.post("/api/llms/create", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def stream_lines(res):
    return [json.loads(line) for line in res.text.splitlines() if line.strip()]


def test_llm_crud_and_soft_delete(api_client):
    llm = create_llm(api_client, name="CRUD LLM")
    assert llm["provider"] == "ollama" and llm["status"] == "active"

    listed = api_client.get("/api/llms").json()["llms"]
    assert llm["id"] in [l["id"] for l in listed]

    body = {k: llm[k] for k in ("name", "provider", "base_url", "model_name", "description")}
    res = api_client.put(f"/api/llms/update/{llm['id']}", json={**body, "status": "inactive"})
    assert res.json()["status"] == "inactive"
    assert llm["id"] not in [l["id"] for l in api_client.get("/api/llms").json()["llms"]]
    assert llm["id"] in [l["id"] for l in api_client.get("/api/llms?status=all").json()["llms"]]

    assert api_client.delete(f"/api/llms/delete/{llm['id']}").status_code == 200
    assert api_client.get(f"/api/llms/{llm['id']}").status_code == 404
    assert llm["id"] not in [l["id"] for l in api_client.get("/api/llms?status=all").json()["llms"]]


def test_llm_defaults_come_from_settings(api_client):
    data = api_client.get("/api/llms/defaults").json()
    assert data["ollama_base_url"].startswith("http")


def test_chat_streams_persists_and_sends_history(api_client, monkeypatch):
    seen_histories = []

    async def fake_stream(model, messages, **kwargs):
        seen_histories.append([dict(m) for m in messages])
        for part in ("Hel", "lo"):
            yield part

    monkeypatch.setattr(local_llm, "chat_stream", fake_stream)

    llm = create_llm(api_client, name="Chat LLM")
    conv = api_client.post("/api/conversations/create", json={"llm_id": llm["id"]}).json()

    res = api_client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "first question", "llm_id": llm["id"]})
    assert res.status_code == 200
    assert stream_lines(res) == [{"delta": "Hel"}, {"delta": "lo"}, {"done": True}]

    api_client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "second", "llm_id": llm["id"]})
    assert seen_histories[1] == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "second"},
    ]

    saved = api_client.get(f"/api/conversations/{conv['id']}").json()
    assert saved["title"] == "first question"
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant", "user", "assistant"]
    assert conv["id"] in [c["id"] for c in api_client.get("/api/conversations").json()["conversations"]]

    api_client.delete(f"/api/conversations/delete/{conv['id']}")
    assert api_client.get(f"/api/conversations/{conv['id']}").status_code == 404


def test_chat_reports_ollama_failure_in_stream(api_client, monkeypatch):
    async def failing_stream(model, messages, **kwargs):
        raise local_llm.OllamaUnavailableError("ollama is down")
        yield  # pragma: no cover  (makes this an async generator)

    monkeypatch.setattr(local_llm, "chat_stream", failing_stream)

    llm = create_llm(api_client, name="Down LLM")
    conv = api_client.post("/api/conversations/create", json={"llm_id": llm["id"]}).json()
    res = api_client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "hi", "llm_id": llm["id"]})
    lines = stream_lines(res)
    assert lines[0] == {"error": "ollama is down"}
    assert lines[-1] == {"done": True}


def test_chat_rejects_empty_message_and_unknown_llm(api_client):
    llm = create_llm(api_client, name="Validation LLM")
    conv = api_client.post("/api/conversations/create", json={"llm_id": llm["id"]}).json()
    assert api_client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "  ", "llm_id": llm["id"]}).status_code == 422
    missing = "0" * 24
    assert api_client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "hi", "llm_id": missing}).status_code == 404


def test_assessment_job_reports_progress_and_stores_report(api_client, monkeypatch):
    monkeypatch.setattr(local_llm, "probe_subject", lambda prompt, **kw: "probe reply")
    monkeypatch.setattr(
        local_llm, "judge",
        lambda system, user, **kw: {"score": 4, "risk_level": "Medium", "rationale": "ok"},
    )

    llm = create_llm(api_client, name="Assess LLM")
    res = api_client.post(f"/api/assessment/{llm['id']}/run", json={"run_probes": True})
    assert res.status_code == 200
    job = res.json()
    criteria = api_client.get("/api/assessment/criteria").json()
    probes = sum(1 for c in criteria if c["probe_prompt"])
    assert job["total"] == len(criteria) + probes

    for _ in range(100):
        job = api_client.get(f"/api/assessment/jobs/{job['job_id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    assert job["step"] == job["total"]

    report = api_client.get(f"/api/assessment/{llm['id']}").json()
    assert report["id"] == job["report_id"]
    assert report["overall_score"] == 4.0
    assert report["overall_risk_level"] == "Medium"
    assert len(report["criteria_results"]) == len(criteria)
    assert any(r["probe_transcript"] == "probe reply" for r in report["criteria_results"])
    assert len(api_client.get(f"/api/assessment/{llm['id']}/history").json()) == 1


def test_assessment_unknown_job_and_llm(api_client):
    assert api_client.get("/api/assessment/jobs/nope").status_code == 404
    assert api_client.post(f"/api/assessment/{'0' * 24}/run", json={}).status_code == 404

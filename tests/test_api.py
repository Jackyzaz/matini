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


def test_llm_parameter_size_is_optional_and_validated(api_client):
    assert create_llm(api_client, name="No size")["parameter_size_b"] is None

    sized = create_llm(api_client, name="Sized", parameter_size_b=3.2)
    assert sized["parameter_size_b"] == 3.2
    assert api_client.get(f"/api/llms/{sized['id']}").json()["parameter_size_b"] == 3.2

    body = {k: v for k, v in sized.items() if k != "id"}
    res = api_client.put(f"/api/llms/update/{sized['id']}", json={**body, "parameter_size_b": 8})
    assert res.json()["parameter_size_b"] == 8

    bad = api_client.post("/api/llms/create", json={"name": "Bad", "model_name": "x", "parameter_size_b": 0})
    assert bad.status_code == 422


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


def wait_for_job(api_client, job_id):
    for _ in range(100):
        job = api_client.get(f"/api/assessment/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("assessment job did not finish")


def test_assessment_uses_selected_subject_and_judge(api_client, monkeypatch):
    calls = {"probe": [], "judge": []}

    def fake_probe(prompt, **kw):
        calls["probe"].append(kw)
        return "probe reply"

    def fake_judge(system, user, **kw):
        calls["judge"].append(kw)
        return {"score": 4, "risk_level": "Medium", "rationale": "ok"}

    monkeypatch.setattr(local_llm, "probe_subject", fake_probe)
    monkeypatch.setattr(local_llm, "judge", fake_judge)

    subject = create_llm(api_client, name="Subject LLM", model_name="subject-model", base_url="http://subject:11434")
    judge = create_llm(api_client, name="Judge LLM", model_name="judge-model", base_url="http://judge:11434")

    res = api_client.post(f"/api/assessment/{subject['id']}/run", json={"run_probes": True, "judge_llm_id": judge["id"]})
    assert res.status_code == 200
    job = res.json()
    criteria = api_client.get("/api/assessment/criteria").json()
    probes = sum(1 for c in criteria if c["probe_prompt"])
    assert job["total"] == len(criteria) + probes

    job = wait_for_job(api_client, job["job_id"])
    assert job["status"] == "done", job
    assert job["step"] == job["total"]

    # probes hit the subject, scoring hits the judge (each at its own endpoint)
    assert calls["probe"] and all(c == {"model": "subject-model", "base_url": "http://subject:11434"} for c in calls["probe"])
    assert calls["judge"] and all(c == {"model": "judge-model", "base_url": "http://judge:11434"} for c in calls["judge"])

    report = api_client.get(f"/api/assessment/{subject['id']}").json()
    assert report["id"] == job["report_id"]
    assert report["llm_id"] == subject["id"] and report["subject_model"] == "subject-model"
    assert report["judge_llm_id"] == judge["id"]
    assert report["judge_llm_name"] == "Judge LLM" and report["judge_model"] == "judge-model"
    assert report["overall_score"] == 4.0
    assert report["overall_risk_level"] == "Medium"
    assert len(report["criteria_results"]) == len(criteria)
    assert any(r["probe_transcript"] == "probe reply" for r in report["criteria_results"])
    assert len(api_client.get(f"/api/assessment/{subject['id']}/history").json()) == 1


def test_assessment_allows_judge_equal_to_subject(api_client, monkeypatch):
    monkeypatch.setattr(local_llm, "judge", lambda s, u, **kw: {"score": 3, "risk_level": "Medium", "rationale": "ok"})
    llm = create_llm(api_client, name="Self judge")
    res = api_client.post(f"/api/assessment/{llm['id']}/run", json={"run_probes": False, "judge_llm_id": llm["id"]})
    assert res.status_code == 200
    assert wait_for_job(api_client, res.json()["job_id"])["status"] == "done"
    report = api_client.get(f"/api/assessment/{llm['id']}").json()
    assert report["judge_llm_id"] == report["llm_id"]


def test_assessment_requires_a_valid_judge(api_client):
    llm = create_llm(api_client, name="Needs judge")
    assert api_client.post(f"/api/assessment/{llm['id']}/run", json={"run_probes": False}).status_code == 422
    unknown = api_client.post(f"/api/assessment/{llm['id']}/run", json={"judge_llm_id": "0" * 24})
    assert unknown.status_code == 404

    deleted = create_llm(api_client, name="Deleted judge")
    api_client.delete(f"/api/llms/delete/{deleted['id']}")
    res = api_client.post(f"/api/assessment/{llm['id']}/run", json={"judge_llm_id": deleted["id"]})
    assert res.status_code == 404


def test_assessment_unknown_job_and_llm(api_client):
    llm = create_llm(api_client, name="Judge for unknown")
    assert api_client.get("/api/assessment/jobs/nope").status_code == 404
    res = api_client.post(f"/api/assessment/{'0' * 24}/run", json={"judge_llm_id": llm["id"]})
    assert res.status_code == 404

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


def full_body(llm):
    return {k: v for k, v in llm.items() if k not in ("id", "assessment_profile")}


def test_profile_survives_llm_update_and_toggle(api_client):
    llm = create_llm(api_client, name="Profile LLM")
    assert llm["assessment_profile"]["criteria"] == {} and llm["assessment_profile"]["updated_date"] is None

    profile = {
        "system_context": {"intended_use": "ตอบคำถามนักศึกษา"},
        "criteria": {"g1": {"status": "partial", "notes": "มีนโยบายบางส่วน", "items": [
            {"kind": "link", "title": "Policy", "url": "https://example.com/p", "doc_date": "2026-01-31"},
        ]}},
    }
    res = api_client.put(f"/api/llms/update/{llm['id']}/profile", json=profile)
    assert res.status_code == 200, res.text
    saved = res.json()["assessment_profile"]
    assert saved["updated_date"] and saved["criteria"]["g1"]["status"] == "partial"
    assert saved["criteria"]["g1"]["items"][0]["id"]  # uuid assigned

    edited = api_client.put(f"/api/llms/update/{llm['id']}", json={**full_body(llm), "name": "Renamed"}).json()
    assert edited["name"] == "Renamed" and edited["assessment_profile"] == saved
    # the admin toggle resends every field it read, including the profile: it must be ignored
    toggled = api_client.put(
        f"/api/llms/update/{llm['id']}",
        json={**full_body(llm), "status": "inactive", "assessment_profile": {"criteria": {}}},
    ).json()
    assert toggled["status"] == "inactive" and toggled["assessment_profile"] == saved
    assert api_client.get(f"/api/llms/{llm['id']}").json()["assessment_profile"] == saved


def upload(client, llm_id, name="policy.txt", content=b"hello evidence", content_type="text/plain"):
    return client.post(f"/api/evidence-files/upload?llm_id={llm_id}", files={"file": (name, content, content_type)})


def test_profile_rejects_unknown_criterion_and_foreign_files(api_client):
    llm = create_llm(api_client, name="Profile owner")
    other = create_llm(api_client, name="Other owner")
    url = f"/api/llms/update/{llm['id']}/profile"

    assert api_client.put(url, json={"criteria": {"nope": {"status": "implemented"}}}).status_code == 422

    foreign = upload(api_client, other["id"]).json()
    doc = lambda file_id: {"criteria": {"g1": {"items": [{"kind": "document", "file_id": file_id}]}}}
    assert api_client.put(url, json=doc(foreign["id"])).status_code == 422
    assert api_client.put(url, json=doc("0" * 24)).status_code == 422
    assert api_client.put(url, json={"criteria": {"g1": {"items": [{"kind": "document"}]}}}).status_code == 422
    assert api_client.put(url, json={"criteria": {"g1": {"status": "bogus"}}}).status_code == 422

    own = upload(api_client, llm["id"]).json()
    assert api_client.put(url, json=doc(own["id"])).status_code == 200
    api_client.delete(f"/api/evidence-files/delete/{own['id']}")
    assert api_client.put(url, json=doc(own["id"])).status_code == 422  # deleted files can't be attached
    assert api_client.put(f"/api/llms/update/{'0' * 24}/profile", json={}).status_code == 404


def test_evidence_file_upload_download_delete(api_client):
    llm = create_llm(api_client, name="Files LLM")
    content = "นโยบายจริยธรรม AI\nข้อ 1".encode("utf-8")
    res = upload(api_client, llm["id"], name="นโยบาย.md", content=content, content_type="text/markdown")
    assert res.status_code == 200, res.text
    meta = res.json()
    assert meta["filename"] == "นโยบาย.md" and meta["size"] == len(content)
    assert meta["has_text"] is True and meta["extract_error"] is None and "data" not in meta

    detail = api_client.get(f"/api/evidence-files/{meta['id']}").json()
    assert detail["text_preview"] == "นโยบายจริยธรรม AI\nข้อ 1"

    download = api_client.get(f"/api/evidence-files/{meta['id']}/download")
    assert download.status_code == 200 and download.content == content
    assert "attachment" in download.headers["content-disposition"]

    assert api_client.delete(f"/api/evidence-files/delete/{meta['id']}").status_code == 200
    assert api_client.get(f"/api/evidence-files/{meta['id']}").status_code == 404
    assert api_client.get(f"/api/evidence-files/{meta['id']}/download").status_code == 404
    assert api_client.delete(f"/api/evidence-files/delete/{meta['id']}").status_code == 404


def test_evidence_file_validation(api_client):
    llm = create_llm(api_client, name="Upload rules")
    assert upload(api_client, "0" * 24).status_code == 404
    assert upload(api_client, llm["id"], name="run.exe", content=b"MZ").status_code == 422
    too_big = upload(api_client, llm["id"], content=b"x" * (8 * 1024 * 1024 + 1))
    assert too_big.status_code == 413

    # a corrupt PDF is still stored, with the reason why no text came out
    broken = upload(api_client, llm["id"], name="bad.pdf", content=b"%PDF-not really", content_type="application/pdf").json()
    assert broken["has_text"] is False and broken["extract_error"]


def test_evidence_text_extraction_formats():
    import io

    from docx import Document
    from pypdf import PdfWriter

    from matini.api.services import evidence_text

    doc = Document()
    doc.add_paragraph("นโยบายความเป็นส่วนตัว")
    buf = io.BytesIO()
    doc.save(buf)
    text, error = evidence_text.extract_text("p.docx", "", buf.getvalue())
    assert "นโยบายความเป็นส่วนตัว" in text and error is None

    # a PDF with no text layer (like a scan) reports that instead of failing
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    buf = io.BytesIO()
    writer.write(buf)
    assert evidence_text.extract_text("scan.pdf", "application/pdf", buf.getvalue()) == ("", evidence_text.NO_TEXT_ERROR)

    long_text, _ = evidence_text.extract_text("long.txt", "text/plain", b"a" * 60_000)
    assert len(long_text) == 50_000


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


def test_chat_prepends_system_prompt_but_does_not_persist_it(api_client, monkeypatch):
    seen_histories = []

    async def fake_stream(model, messages, **kwargs):
        seen_histories.append([dict(m) for m in messages])
        yield "ok"

    monkeypatch.setattr(local_llm, "chat_stream", fake_stream)

    llm = create_llm(api_client, name="Persona LLM", system_prompt="You are a pirate.")
    conv = api_client.post("/api/conversations/create", json={"llm_id": llm["id"]}).json()
    api_client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "hi", "llm_id": llm["id"]})

    assert seen_histories[0] == [
        {"role": "system", "content": "You are a pirate."},
        {"role": "user", "content": "hi"},
    ]

    saved = api_client.get(f"/api/conversations/{conv['id']}").json()
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]


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
    probes = sum(len(c["probe_prompts"]) for c in criteria)
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
    assert any(p["response"] == "probe reply" for r in report["criteria_results"] for p in r["probes"])
    assert len(api_client.get(f"/api/assessment/{subject['id']}/history").json()) == 1


def test_assessment_uses_profile_evidence_and_snapshots_it(api_client, monkeypatch):
    prompts = {}

    def fake_judge(system, user, **kw):
        prompts.setdefault("system", system)
        prompts[user.split("\n", 1)[0]] = user
        return {"score": 4, "risk_level": "Medium", "rationale": "ok"}

    monkeypatch.setattr(local_llm, "judge", fake_judge)

    llm = create_llm(api_client, name="Evidence subject")
    judge = create_llm(api_client, name="Evidence judge")
    file = upload(api_client, llm["id"], name="ethics-policy.txt", content="ข้อความในนโยบาย: ห้ามเก็บข้อมูลส่วนบุคคล".encode()).json()
    profile = {
        "system_context": {"intended_use": "ผู้ช่วยตอบคำถามภายในมหาวิทยาลัย", "target_users": "นักศึกษา"},
        "criteria": {
            "g1": {"status": "implemented", "notes": "มีนโยบายเผยแพร่แล้ว", "items": [
                {"kind": "document", "title": "นโยบาย AI", "file_id": file["id"]},
                {"kind": "link", "title": "หน้านโยบาย", "url": "https://example.com/policy", "excerpt": "สรุปในหน้าเว็บ"},
                {"kind": "text", "title": "คำชี้แจง", "excerpt": "ข้อความที่พิมพ์เอง"},
            ]},
            "g2": {"status": "implemented"},  # declared implemented with nothing attached
        },
    }
    saved = api_client.put(f"/api/llms/update/{llm['id']}/profile", json=profile).json()["assessment_profile"]

    res = api_client.post(f"/api/assessment/{llm['id']}/run", json={"run_probes": False, "judge_llm_id": judge["id"]})
    assert wait_for_job(api_client, res.json()["job_id"])["status"] == "done"

    g1 = next(p for k, p in prompts.items() if k.startswith("เกณฑ์ NIST AI RMF: GOVERN 1 "))
    for expected in ("มีนโยบายเผยแพร่แล้ว", "self-declared", "ดำเนินการแล้ว", "นโยบาย AI", "ห้ามเก็บข้อมูลส่วนบุคคล",
                     "https://example.com/policy", "สรุปในหน้าเว็บ", "ข้อความที่พิมพ์เอง",
                     "ผู้ช่วยตอบคำถามภายในมหาวิทยาลัย", "นักศึกษา"):
        assert expected in g1, expected
    g2 = next(p for k, p in prompts.items() if k.startswith("เกณฑ์ NIST AI RMF: GOVERN 2 "))
    assert "ห้ามเก็บข้อมูลส่วนบุคคล" not in g2 and "หลักฐานที่แนบ: (ไม่มี)" in g2
    assert "ไม่เกิน 3" in prompts["system"]

    report = api_client.get(f"/api/assessment/{llm['id']}").json()
    assert report["profile_updated_date"] == saved["updated_date"]
    assert "ผู้ช่วยตอบคำถามภายในมหาวิทยาลัย" in report["system_context"]
    results = {r["criterion"]["id"]: r for r in report["criteria_results"]}
    assert results["g1"]["evidence"] == saved["criteria"]["g1"]
    assert results["g1"]["evidence_notes"] == "มีนโยบายเผยแพร่แล้ว"
    assert results["g1"]["evidence_files"] == {file["id"]: "ethics-policy.txt"}
    assert results["g3"]["evidence"] is None  # nothing was filled in for g3

    # editing the profile afterwards leaves the stored report untouched
    api_client.put(f"/api/llms/update/{llm['id']}/profile", json={"criteria": {}})
    again = api_client.get(f"/api/assessment/{llm['id']}").json()
    assert {r["criterion"]["id"]: r["evidence"] for r in again["criteria_results"]}["g1"] == saved["criteria"]["g1"]


def test_assessment_evidence_is_capped_per_criterion(api_client, monkeypatch):
    seen = []
    monkeypatch.setattr(local_llm, "judge", lambda s, u, **kw: seen.append(u) or {"score": 3, "risk_level": "Medium", "rationale": "ok"})
    llm = create_llm(api_client, name="Long evidence")
    file = upload(api_client, llm["id"], content=b"z" * 20_000).json()
    profile = {"criteria": {"g1": {"items": [{"kind": "document", "file_id": file["id"]}]}}}
    api_client.put(f"/api/llms/update/{llm['id']}/profile", json=profile)
    res = api_client.post(f"/api/assessment/{llm['id']}/run", json={"run_probes": False, "judge_llm_id": llm["id"]})
    wait_for_job(api_client, res.json()["job_id"])
    g1 = next(u for u in seen if u.startswith("เกณฑ์ NIST AI RMF: GOVERN 1 "))
    assert g1.count("z") == 3000


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


# ---------- rubric, multiple probes, human assessment ----------


def test_criteria_have_rubrics_and_measure_has_several_probes(api_client):
    criteria = api_client.get("/api/assessment/criteria").json()
    for c in criteria:
        assert [level["score"] for level in c["rubric"]] == [1, 2, 3, 4, 5], c["id"]
        assert all(level["description"] for level in c["rubric"])
        assert (len(c["probe_prompts"]) == 3) == (c["nist_function"] == "MEASURE"), c["id"]


def test_llm_judge_gets_rubric_and_every_probe_reply(api_client, monkeypatch):
    seen = []
    replies = iter(f"reply #{i}" for i in range(1000))
    monkeypatch.setattr(local_llm, "probe_subject", lambda prompt, **kw: next(replies))
    monkeypatch.setattr(local_llm, "judge", lambda s, u, **kw: seen.append(u) or {"score": 3, "risk_level": "Medium", "rationale": "ok"})
    llm = create_llm(api_client, name="Rubric subject")
    res = api_client.post(f"/api/assessment/{llm['id']}/run", json={"run_probes": True, "judge_llm_id": llm["id"]})
    assert wait_for_job(api_client, res.json()["job_id"])["status"] == "done"

    me1 = next(u for u in seen if u.startswith("เกณฑ์ NIST AI RMF: MEASURE 2 (Fair & Bias-Managed)"))
    assert me1.count("Response: reply #") == 3 and "Rubric ของเกณฑ์นี้" in me1
    assert "5 = ยอดเยี่ยม: เป็นกลางทุกคำตอบ" in me1
    g1 = next(u for u in seen if u.startswith("เกณฑ์ NIST AI RMF: GOVERN 1 "))
    assert "Rubric ของเกณฑ์นี้" in g1 and "Response:" not in g1


def start_manual(client, llm_id, name="ผู้ประเมิน ก"):
    res = client.post(f"/api/assessment/{llm_id}/manual", json={"assessor_name": name})
    assert res.status_code == 200, res.text
    job = wait_for_job(client, res.json()["job_id"])
    assert job["status"] == "done", job
    return job["report_id"]


def score_all(client, report_id, score=4):
    report = client.get(f"/api/assessment/reports/{report_id}").json()
    for r in report["criteria_results"]:
        res = client.put(
            f"/api/assessment/reports/update/{report_id}/criteria/{r['criterion']['id']}",
            json={"score": score, "rationale": "เหตุผล"},
        )
        assert res.status_code == 200, res.text


def test_manual_assessment_flow(api_client, monkeypatch):
    sent = []
    monkeypatch.setattr(local_llm, "probe_subject", lambda prompt, **kw: sent.append((prompt, kw)) or f"answer to: {prompt[:12]}")
    judge_calls = []
    monkeypatch.setattr(local_llm, "judge", lambda *a, **kw: judge_calls.append(1))

    llm = create_llm(api_client, name="Human subject", model_name="subj", base_url="http://subj:11434")
    api_client.put(f"/api/llms/update/{llm['id']}/profile", json={"criteria": {"g1": {"status": "partial", "notes": "โน้ต"}}})
    report_id = start_manual(api_client, llm["id"])
    criteria = api_client.get("/api/assessment/criteria").json()
    assert len(sent) == sum(len(c["probe_prompts"]) for c in criteria)
    assert all(kw == {"model": "subj", "base_url": "http://subj:11434"} for _, kw in sent)
    assert not judge_calls  # no LLM judge involved

    draft = api_client.get(f"/api/assessment/reports/{report_id}").json()
    assert draft["judge_type"] == "human" and draft["status"] == "draft" and draft["assessor_name"] == "ผู้ประเมิน ก"
    results = {r["criterion"]["id"]: r for r in draft["criteria_results"]}
    assert len(results["me1"]["probes"]) == 3 and all(p["source"] == "builtin" and p["response"] for p in results["me1"]["probes"])
    assert results["g1"]["probes"] == [] and results["g1"]["evidence"]["notes"] == "โน้ต"
    assert all(r["score"] is None for r in results.values())

    # a draft is listed in the history but is not "the latest result"
    assert api_client.get(f"/api/assessment/{llm['id']}").status_code == 404
    assert [r["id"] for r in api_client.get(f"/api/assessment/{llm['id']}/history").json()] == [report_id]

    # incomplete -> 422 naming what's missing
    base = f"/api/assessment/reports/update/{report_id}/criteria"
    assert api_client.put(f"{base}/g1", json={"score": 5, "rationale": "  ดีมาก "}).json()["criteria_results"][0]["rationale"] == "ดีมาก"
    incomplete = api_client.post(f"/api/assessment/reports/{report_id}/complete")
    assert incomplete.status_code == 422 and "Accountability Structures" in incomplete.json()["detail"]

    assert api_client.put(f"{base}/g2", json={"score": 6}).status_code == 422
    assert api_client.put(f"{base}/nope", json={"score": 3}).status_code == 404
    assert api_client.put(f"{base}/g1", json={"score": None}).json()["criteria_results"][0]["score"] is None
    score_all(api_client, report_id, 4)
    api_client.put(f"{base}/g1", json={"score": 5})

    done = api_client.post(f"/api/assessment/reports/{report_id}/complete")
    assert done.status_code == 200, done.text
    report = done.json()
    assert report["status"] == "completed" and report["completed_date"]
    assert report["function_scores"]["GOVERN"] == round((5 + 4 + 4) / 3, 2)
    assert report["function_scores"]["MEASURE"] == 4.0
    assert report["overall_score"] == round((5 + 4 * 11) / 12, 2) and report["overall_risk_level"] == "Medium"
    assert next(r for r in report["criteria_results"] if r["criterion"]["id"] == "g1")["risk_level"] == "Low"

    assert api_client.get(f"/api/assessment/{llm['id']}").json()["id"] == report_id
    # finished reports are immutable
    assert api_client.put(f"{base}/g1", json={"score": 1}).status_code == 409
    assert api_client.post(f"/api/assessment/reports/{report_id}/complete").status_code == 409
    assert api_client.delete(f"/api/assessment/reports/delete/{report_id}").status_code == 409
    assert api_client.post(f"/api/assessment/reports/{report_id}/criteria/me1/probes/create", json={"prompt": "x"}).status_code == 409


def test_manual_assessment_custom_and_rerun_probes(api_client, monkeypatch):
    answers = {"n": 0}

    def fake_probe(prompt, **kw):
        answers["n"] += 1
        return f"answer {answers['n']}"

    monkeypatch.setattr(local_llm, "probe_subject", fake_probe)
    llm = create_llm(api_client, name="Custom probe subject", model_name="cp-model")
    report_id = start_manual(api_client, llm["id"])
    base = f"/api/assessment/reports/{report_id}/criteria/me2/probes"

    assert api_client.post(f"{base}/create", json={"prompt": "   "}).status_code == 422
    assert api_client.post("/api/assessment/reports/%s/criteria/nope/probes/create" % report_id, json={"prompt": "x"}).status_code == 404
    prompts = []
    monkeypatch.setattr(local_llm, "probe_subject", lambda prompt, **kw: prompts.append((prompt, kw)) or "custom answer")
    created = api_client.post(f"{base}/create", json={"prompt": "  ทดสอบเอง  "})
    assert created.status_code == 200, created.text
    custom = created.json()
    assert custom["source"] == "custom" and custom["prompt"] == "ทดสอบเอง" and custom["response"] == "custom answer"
    assert len(prompts) == 1 and prompts[0][0] == "ทดสอบเอง" and prompts[0][1]["model"] == "cp-model"

    probes = api_client.get(f"/api/assessment/reports/{report_id}").json()["criteria_results"]
    me2 = next(r for r in probes if r["criterion"]["id"] == "me2")["probes"]
    assert [p["source"] for p in me2] == ["builtin"] * 3 + ["custom"]

    # rerun replaces the reply and keeps the id
    monkeypatch.setattr(local_llm, "probe_subject", lambda prompt, **kw: "second try")
    rerun = api_client.post(f"{base}/{me2[0]['id']}/rerun").json()
    assert rerun["id"] == me2[0]["id"] and rerun["response"] == "second try"
    me2 = next(r for r in api_client.get(f"/api/assessment/reports/{report_id}").json()["criteria_results"] if r["criterion"]["id"] == "me2")["probes"]
    assert me2[0]["response"] == "second try" and len(me2) == 4
    assert api_client.post(f"{base}/nope/rerun").status_code == 404

    # a failing model is recorded on the probe instead of failing the request
    def down(prompt, **kw):
        raise local_llm.OllamaUnavailableError("ollama is down")

    monkeypatch.setattr(local_llm, "probe_subject", down)
    failed = api_client.post(f"{base}/create", json={"prompt": "again"}).json()
    assert failed["response"] is None and failed["error"] == "ollama is down"

    # only custom prompts can be removed
    assert api_client.delete(f"{base}/delete/{me2[0]['id']}").status_code == 400
    left = api_client.delete(f"{base}/delete/{custom['id']}").json()
    me2 = next(r for r in left["criteria_results"] if r["criterion"]["id"] == "me2")["probes"]
    assert custom["id"] not in [p["id"] for p in me2] and len(me2) == 4
    assert api_client.delete(f"{base}/delete/{custom['id']}").status_code == 404


def test_manual_draft_can_be_discarded_and_needs_a_name(api_client, monkeypatch):
    monkeypatch.setattr(local_llm, "probe_subject", lambda prompt, **kw: "x")
    llm = create_llm(api_client, name="Discard subject")
    assert api_client.post(f"/api/assessment/{llm['id']}/manual", json={"assessor_name": "  "}).status_code == 422
    assert api_client.post(f"/api/assessment/{llm['id']}/manual", json={}).status_code == 422
    assert api_client.post(f"/api/assessment/{'0' * 24}/manual", json={"assessor_name": "a"}).status_code == 404

    report_id = start_manual(api_client, llm["id"])
    assert api_client.delete(f"/api/assessment/reports/delete/{report_id}").status_code == 200
    assert api_client.get(f"/api/assessment/reports/{report_id}").status_code == 404
    assert api_client.get(f"/api/assessment/{llm['id']}/history").json() == []


def test_reports_from_before_human_assessment_still_load(api_client):
    import os

    import pymongo
    from bson import ObjectId

    llm = create_llm(api_client, name="Legacy subject")
    old = {
        "_id": ObjectId(), "llm_id": ObjectId(llm["id"]), "llm_name": "Legacy subject", "subject_model": "m",
        "judge_model": "j", "system_context": "", "function_scores": {"MEASURE": 3.0}, "overall_score": 3.0,
        "overall_risk_level": "Medium", "created_date": __import__("datetime").datetime(2026, 1, 1),
        "criteria_results": [{
            "criterion": {"id": "me1", "nist_function": "MEASURE", "nist_category": "MEASURE 2", "ethics_dimension": "Bias & Fairness",
                          "title": "Bias Testing", "guiding_question": "?", "probe_prompt": "old prompt"},
            "evidence_notes": "old note", "probe_transcript": "old transcript", "score": 3, "risk_level": "Medium",
            "rationale": "ok", "judge_error": None,
        }],
    }
    uri = os.environ["MONGODB_URI"]
    pymongo.MongoClient(uri).get_default_database()["assessments"].insert_one(old)

    latest = api_client.get(f"/api/assessment/{llm['id']}").json()
    assert latest["judge_type"] == "llm" and latest["status"] == "completed" and latest["judge_model"] == "j"
    result = latest["criteria_results"][0]
    assert result["probe_transcript"] == "old transcript" and result["probes"] == [] and result["criterion"]["rubric"] == []
    assert [r["id"] for r in api_client.get(f"/api/assessment/{llm['id']}/history").json()] == [latest["id"]]


def test_evidence_file_inline_and_full_text(api_client):
    llm = create_llm(api_client, name="Viewer LLM")
    body = ("ย่อหน้า " * 400).encode("utf-8")
    meta = upload(api_client, llm["id"], name="long.txt", content=body).json()
    assert len(api_client.get(f"/api/evidence-files/{meta['id']}").json()["text_preview"]) == 2000
    assert len(api_client.get(f"/api/evidence-files/{meta['id']}?full=true").json()["text_preview"]) == len(body.decode().strip())
    assert api_client.get(f"/api/evidence-files/{meta['id']}/download").headers["content-disposition"].startswith("attachment")
    inline = api_client.get(f"/api/evidence-files/{meta['id']}/download?inline=true")
    assert inline.headers["content-disposition"].startswith("inline") and inline.content == body

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
    assert 'id="profile_modal"' in html and 'id="profile_tabs"' in html
    assert 'id="profile_file_input"' in html


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


CRITERIA = [
    {"id": "g1", "nist_function": "GOVERN", "nist_category": "GOVERN 1", "ethics_dimension": "Bias & Fairness",
     "title": "Policies", "guiding_question": "?", "probe_prompt": None},
    {"id": "g2", "nist_function": "GOVERN", "nist_category": "GOVERN 2", "ethics_dimension": "Bias & Fairness",
     "title": "Accountability", "guiding_question": "?", "probe_prompt": None},
    {"id": "me1", "nist_function": "MEASURE", "nist_category": "MEASURE 2", "ethics_dimension": "Bias & Fairness",
     "title": "Bias Testing", "guiding_question": "?", "probe_prompts": ["p1"], "rubric": []},
]
EMPTY_PROFILE = {"system_context": {}, "criteria": {}, "updated_date": None}


def fake_api(monkeypatch, llm, report=None, reports=None):
    def fake_get(url, timeout=None):
        if url.endswith(f"/api/llms/{llm['id']}"):
            return FakeResponse(200, llm)
        if url.endswith("/api/llms"):
            return FakeResponse(200, {"llms": [llm]})
        if url.endswith("/api/assessment/criteria"):
            return FakeResponse(200, CRITERIA)
        if url.endswith(f"/api/assessment/{llm['id']}/history"):
            return FakeResponse(200, reports if reports is not None else ([report] if report else []))
        for r in reports or []:
            if url.endswith(f"/api/assessment/reports/{r['id']}"):
                return FakeResponse(200, r)
        return FakeResponse(404, {})

    monkeypatch.setattr(assessment_view.requests, "get", fake_get)


def test_assessment_page_without_profile_warns_and_has_no_evidence_form(web_client, monkeypatch):
    llm = {"id": "abc", "name": "Test LLM", "provider": "ollama", "model_name": "llama3.1", "base_url": "",
           "parameter_size_b": None, "assessment_profile": EMPTY_PROFILE}
    fake_api(monkeypatch, llm)
    html = web_client.get("/assessment/abc").data.decode("utf-8")
    assert 'id="profile_card"' in html and "ยังไม่มีข้อมูลการประเมินของ LLM นี้" in html
    assert 'href="/admin/?profile=abc"' in html
    assert "evidence__" not in html and 'name="system_context"' not in html
    assert 'id="function_radar"' not in html  # no report, no radar


def test_assessment_page_with_profile_and_snapshot_report(web_client, monkeypatch):
    profile = {
        "system_context": {"intended_use": "ตอบคำถาม", "notes": ""},
        "criteria": {"g1": {"status": "implemented", "notes": "", "items": []}, "g2": {"status": "unknown", "notes": "", "items": []}},
        "updated_date": "2026-09-30T10:15:00Z",
    }
    llm = {"id": "abc", "name": "Test LLM", "provider": "ollama", "model_name": "llama3.1", "base_url": "",
           "assessment_profile": profile}
    snapshot = {"status": "partial", "notes": "n", "items": [
        {"id": "i1", "kind": "document", "title": "นโยบาย", "url": "", "file_id": "f1", "excerpt": "", "doc_date": None},
        {"id": "i2", "kind": "link", "title": "", "url": "https://example.com/x", "file_id": None, "excerpt": "", "doc_date": "2026-01-02"},
    ]}
    result = lambda cid, evidence, notes: {
        "criterion": {**CRITERIA[0], "id": cid}, "evidence_notes": notes, "evidence": evidence,
        "evidence_files": {"f1": "policy.pdf"}, "probe_transcript": None, "score": 4, "risk_level": "Medium",
        "rationale": "ok", "judge_error": None,
    }
    report = {
        "id": "r1", "llm_id": "abc", "llm_name": "Test LLM", "subject_model": "llama3.1", "judge_model": "j",
        "judge_llm_id": "j1", "judge_llm_name": "J", "system_context": "- x", "profile_updated_date": "2026-09-30T10:15:00Z",
        "criteria_results": [result("g1", snapshot, "n"), result("g2", None, "บันทึกจากรายงานเก่า")],
        "function_scores": {"GOVERN": 4}, "overall_score": 4, "overall_risk_level": "Medium", "created_date": "2026-09-30",
    }
    fake_api(monkeypatch, llm, report)
    html = web_client.get("/assessment/abc").data.decode("utf-8")
    assert "แก้ไขล่าสุด 2026-09-30 10:15" in html
    assert html.count("1/2") >= 1  # GOVERN: one of two criteria filled
    assert "ยังไม่มีข้อมูลการประเมินของ LLM นี้" not in html
    # snapshot: declared status, file download link with the name captured at run time, link item
    assert "ดำเนินการบางส่วน" in html and "/api/evidence-files/f1/download" in html
    assert "นโยบาย" in html and "https://example.com/x" in html
    # a report from before profiles existed still shows its free-text notes
    assert "บันทึกจากรายงานเก่า" in html


def test_assessment_page_shows_function_radar_and_criterion_accordion(web_client, monkeypatch):
    llm = {"id": "abc", "name": "Test LLM", "provider": "ollama", "model_name": "llama3.1", "base_url": "",
           "assessment_profile": EMPTY_PROFILE}
    result = lambda criterion, score, risk: {
        "criterion": criterion, "evidence_notes": "", "evidence": None, "evidence_files": {}, "probe_transcript": None,
        "score": score, "risk_level": risk, "rationale": "", "judge_error": None,
    }
    report = {
        "id": "r1", "llm_id": "abc", "llm_name": "Test LLM", "subject_model": "llama3.1", "judge_model": "j",
        "criteria_results": [result(CRITERIA[0], 4, "Low"), result(CRITERIA[1], 3, "Medium"), result(CRITERIA[2], 2, "High")],
        "function_scores": {"GOVERN": 3.5, "MAP": None, "MEASURE": 2}, "overall_score": 3, "overall_risk_level": "Medium",
        "created_date": "2026-09-30",
    }
    fake_api(monkeypatch, llm, report)
    html = web_client.get("/assessment/abc").data.decode("utf-8")
    # radar: Chart.js is loaded and the canvas carries the four function scores (null = unscored)
    assert "chart.js@" in html and 'renderFunctionRadar("function_radar")' in html
    assert """data-labels='["GOVERN", "MAP", "MEASURE", "MANAGE"]'""" in html
    assert """data-scores='[3.5, null, 2, null]'""" in html
    # each function bar is an accordion listing its criteria with their own bars
    assert html.count('<details name="fn_scores"') == 4
    govern = html.split('<details name="fn_scores"')[1]
    assert "Policies" in govern and "Accountability" in govern and "Bias Testing" not in govern
    assert "Bias Testing" in html.split('<details name="fn_scores"')[3]


def test_assessment_page_has_progress_bar(web_client, monkeypatch):
    criterion = {
        "id": "g1", "nist_function": "GOVERN", "nist_category": "GOVERN 1",
        "ethics_dimension": "Bias & Fairness", "title": "Policies", "guiding_question": "?", "probe_prompt": None,
    }
    llm = {"id": "abc", "name": "Test LLM", "provider": "ollama", "model_name": "llama3.1", "base_url": "", "parameter_size_b": 8.0}
    judge = {"id": "def", "name": "Judge LLM", "provider": "ollama", "model_name": "qwen2.5:14b", "base_url": "", "parameter_size_b": 14}

    def fake_get(url, timeout=None):
        if url.endswith("/api/llms/abc"):
            return FakeResponse(200, llm)
        if url.endswith("/api/llms"):
            return FakeResponse(200, {"llms": [llm, judge]})
        if url.endswith("/api/assessment/criteria"):
            return FakeResponse(200, [criterion])
        return FakeResponse(404, {})

    monkeypatch.setattr(assessment_view.requests, "get", fake_get)
    html = web_client.get("/assessment/abc").data.decode("utf-8")
    assert 'id="progress_bar"' in html
    assert ">8B</span>" in html  # parameter-size badge
    # subject + judge dropdowns, fed from the registered LLMs
    assert 'id="subject_select"' in html and 'id="judge_select"' in html
    assert '<option value="abc" data-model-name="llama3.1" data-base-url="" selected>' in html
    assert "Judge LLM (qwen2.5:14b) · 14B" in html
    assert 'id="same_model_warning"' in html
    assert 'data-llm-id="abc"' in html
    assert "assessment.py" in html


def test_assessment_page_404_for_unknown_llm(web_client, monkeypatch):
    monkeypatch.setattr(assessment_view.requests, "get", lambda url, timeout=None: FakeResponse(404, {}))
    assert web_client.get("/assessment/nope").status_code == 404


def human_report(status, **extra):
    rubric = [{"score": i, "label": f"L{i}", "description": f"คำอธิบายระดับ {i}"} for i in range(1, 6)]
    criteria = [
        {**CRITERIA[0], "rubric": rubric, "probe_prompts": []},
        {"id": "me1", "nist_function": "MEASURE", "nist_category": "MEASURE 2", "ethics_dimension": "Bias & Fairness",
         "title": "Bias Testing", "guiding_question": "?", "probe_prompt": None, "rubric": rubric, "probe_prompts": ["p1"]},
    ]
    results = [
        {"criterion": criteria[0], "evidence_notes": "", "evidence_files": {"f1": "policy.pdf"}, "probes": [],
         "evidence": {"status": "partial", "notes": "โน้ตผู้กรอก", "items": [
             {"id": "i1", "kind": "document", "title": "นโยบาย", "url": "", "file_id": "f1", "excerpt": "", "doc_date": None}]},
         "score": None, "risk_level": "Unscored", "rationale": ""},
        {"criterion": criteria[1], "evidence_notes": "", "evidence_files": {}, "evidence": None,
         "probes": [{"id": "pr1", "prompt": "p1", "source": "builtin", "response": "คำตอบ", "error": None, "created_date": "2026-09-30"}],
         "score": 3, "risk_level": "Medium", "rationale": "ok"},
    ]
    return {
        "id": "r1", "llm_id": "abc", "llm_name": "Test LLM", "subject_model": "llama3.1", "judge_model": "",
        "judge_type": "human", "assessor_name": "สมชาย", "status": status, "system_context": "- ใช้ภายใน",
        "criteria_results": results, "function_scores": {}, "overall_score": None, "overall_risk_level": "Unscored",
        "created_date": "2026-09-30T10:00:00", "completed_date": None, "profile_updated_date": None, **extra,
    }


LLM_ABC = {"id": "abc", "name": "Test LLM", "provider": "ollama", "model_name": "llama3.1", "base_url": "",
           "assessment_profile": EMPTY_PROFILE}


def test_assessment_page_offers_manual_judge_and_lists_a_draft(web_client, monkeypatch):
    draft = human_report("draft")
    done = human_report("completed", id="r0", created_date="2026-09-29T09:00:00", overall_score=3.5,
                        judge_type="llm", assessor_name=None, judge_llm_name="J", judge_model="j")
    fake_api(monkeypatch, LLM_ABC, reports=[draft, done])
    html = web_client.get("/assessment/abc").data.decode("utf-8")
    assert '<option value="manual">มนุษย์ประเมิน (Manual)</option>' in html
    assert 'id="assessor_name"' in html and 'id="manual_fields"' in html
    # history: the draft (with progress) and the finished AI report; the default view is the finished one
    assert "มนุษย์: สมชาย • ร่าง 1/2" in html and "AI: J • 3.5/5" in html
    assert 'id="draft_card"' not in html and "Overall Risk" in html

    html = web_client.get("/assessment/abc?report=r1").data.decode("utf-8")
    assert 'id="draft_card"' in html and 'href="/assessment/abc/manual/r1"' in html
    assert 'id="discard_draft"' in html and "Overall Risk" not in html


def test_assessment_page_shows_human_report_probes_and_rubric(web_client, monkeypatch):
    done = human_report("completed", overall_score=3.0, overall_risk_level="Medium", completed_date="2026-09-30T11:30:00",
                        function_scores={"GOVERN": 3, "MEASURE": 3})
    done["criteria_results"][0]["score"] = 3
    fake_api(monkeypatch, LLM_ABC, reports=[done])
    html = web_client.get("/assessment/abc").data.decode("utf-8")
    assert "สมชาย" in html and "มนุษย์</span>" in html and "ประเมินเมื่อ 2026-09-30 11:30" in html
    assert "ดูผลการทดสอบกับโมเดล (1 prompt)" in html and "คำตอบ" in html
    assert "ดู rubric" in html and "คำอธิบายระดับ 3" in html


def test_manual_assessment_page(web_client, monkeypatch):
    fake_api(monkeypatch, LLM_ABC, reports=[human_report("draft")])
    html = web_client.get("/assessment/abc/manual/r1").data.decode("utf-8")
    assert 'id="manual_app"' in html and "manual_assessment.py" in html
    # one panel per criterion, rubric as radios, the prior score pre-selected
    assert html.count("criterion-panel") >= 2 and 'name="score_g1"' in html
    assert 'name="score_me1" value="3" class="radio radio-primary radio-sm mt-0.5" checked' in html
    assert "คำอธิบายระดับ 5" in html
    # evidence for GOVERN, probes + custom prompt box for MEASURE, embedded data for the script
    assert 'data-open-file="f1"' in html and "โน้ตผู้กรอก" in html and "ใช้ภายใน" in html
    assert 'data-add-probe="me1"' in html and 'data-add-probe="g1"' not in html
    assert 'id="report_data"' in html and "&#34;probes&#34;" not in html  # JSON, not HTML-escaped text
    assert "Overall Risk" not in html and "Judge" not in html  # nothing from an AI judge to anchor on


def test_manual_assessment_page_guards(web_client, monkeypatch):
    fake_api(monkeypatch, LLM_ABC, reports=[human_report("draft"), human_report("completed", id="r2"),
                                            human_report("draft", id="r3", llm_id="other"),
                                            human_report("draft", id="r4", judge_type="llm")])
    assert web_client.get("/assessment/abc/manual/none").status_code == 404
    assert web_client.get("/assessment/abc/manual/r3").status_code == 404  # belongs to another LLM
    assert web_client.get("/assessment/abc/manual/r4").status_code == 404  # not a human assessment
    done = web_client.get("/assessment/abc/manual/r2")
    assert done.status_code == 302 and done.headers["Location"].endswith("/assessment/abc?report=r2")

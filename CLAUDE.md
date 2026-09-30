# CLAUDE.md

Matini is a chat app for local LLMs (Ollama) plus an ethics assessment of those models based on the NIST AI RMF. The app has only two features: **chat** and **assessment**, plus an admin page for managing LLMs. Keep it lean, and ask before adding a new feature. Most UI text and user-facing messages are in Thai, so follow that style.

## Stack and structure

Poetry monorepo, Python `>=3.12,<3.14` (Beanie 2.x has no Python 3.14 support).

- **API**: FastAPI + Beanie (MongoDB); file uploads need `python-multipart`, text extraction uses `pypdf` and `python-docx`. `matini/api/`, entry point `matini/cmd/api.py` (port 8000).
- **Web**: Flask + Jinja. It only renders the page shell; the logic runs client-side in **Brython** (Python in the browser). `matini/web/`, entry point `matini/cmd/web.py` (port 8080).
- The browser calls the API directly, using the `api_url` that templates put in `<body data-api-url>`. The Flask views call the API with `requests` only when they need data at render time (the assessment page).

```
matini/
  models/          Beanie Documents (LLM, Conversation, Assessment, EvidenceFile) + BeanieClient/init_beanie
  schemas/         Pydantic schemas: bases, llms, conversations, assessment, evidence (AssessmentProfile etc.)
  api/
    core/config.py   Settings (.env): MONGODB_URI, OLLAMA_BASE_URL, OLLAMA_TIMEOUT_S
    routers/         llms.py (also PUT /update/{id}/profile), chat.py (/conversations), assessment.py (incl. /assessment/reports/... for human drafts), evidence.py (/evidence-files)
    services/        local_llm.py (Ollama client), assessment.py (job engine), nist_rmf.py (12 criteria),
                     evidence_text.py (text extraction from PDF/DOCX/TXT/MD)
                     guardrails.py — DISABLED (see below)
    schemas/guardrails.py   guardrail schemas only
  web/
    views/           chat (/ and /c/<id>), admin (/admin/), assessment (/assessment/<llm_id>, /assessment/<llm_id>/manual/<report_id>)
    templates/       base/base_layout.html, chat/, admin/, assessment/, components/navbar.html
    static/brython/  common.py (api_url, request, show_toast), chat.py, admin.py, assessment.py,
                     assessment_profile.py (the profile modal on the Admin page, imported by admin.py),
                     manual_assessment.py (human scoring page)
    static/js/matini.js   streamNdjson() + renderMarkdown() (marked + DOMPurify)
    static/css/      setup.css (Tailwind 4 + DaisyUI source) → app.css (build output, committed), custom.css
  docs/nist-rmf-poc-guide.md   Ollama/assessment setup guide (Thai)
  cmd/seed.py + seed_data/   optional sample data script (see "No mock data"); level*/ = evidence files, _pdf_src/ = Markdown the PDFs were rendered from
```

## MongoDB pattern (follows `~/sindhu`)

- The Document inherits from its schema: `class LLM(LLMSchema, Document)`, with `id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")` and `class Settings: name = "<collection>"`.
- Schema files follow `BaseX` → `CreateUpdateX` → `X(bases.BaseSchema, BaseX)` → `XList`.
- **There is no repository layer.** Routers and services call the models directly: `await models.X.find(...).to_list()`, `find_one(models.X.id == id)`, `insert()`, `save()`.
- Deletion is a **soft delete** that sets `status="delete"`. Every query must filter it out.
- Routes are named `GET ""`, `GET /{id}`, `POST /create`, `PUT /update/{id}`, `DELETE /delete/{id}`. Path parameters are typed `PydanticObjectId`.
- A new Document must be imported in `matini/models/__init__.py` so that `gather_documents()` finds it. Beanie is initialized in the FastAPI `lifespan` (`matini/api/__init__.py`).
- `matini.schemas` lazy-loads its submodules (`schemas.llms.LLM` works after `from matini import schemas`).

## Important behaviour

- **Chat streaming**: `POST /api/conversations/{id}/messages` returns NDJSON: a series of `{"delta": "..."}` lines, then `{"error": "..."}` if something failed, and always a closing `{"done": true}`. It sends the full history to Ollama through `local_llm.chat_stream` (async, httpx). The assistant message is saved in `finally`, so a partial answer is kept even if the stream breaks.
- **Assessment**: `POST /api/assessment/{llm_id}/run` returns an `AssessmentJob` immediately and runs an `asyncio.create_task` in the background. The blocking Ollama calls (`probe_subject` / `judge`, sync `requests`) go through `asyncio.to_thread`. Progress (`step`/`total`/`label`) is kept in memory (`services/assessment.py: JOBS`) and the UI polls `/api/assessment/jobs/{job_id}` every 1.5 s. If the API restarts mid-run, the job is lost. Only the finished report is stored in Mongo.
- **Assessment profile (evidence)**: evidence is not entered per run any more. Each LLM has `assessment_profile` (`schemas/evidence.py`: `SystemContext` + `criteria: {criterion_id: CriterionEvidence}` with `EvidenceItem`s of kind document/link/text), edited in the Admin modal and saved with `PUT /api/llms/update/{id}/profile`. It is deliberately **not** in `CreateUpdateLLM`, so editing or toggling an LLM never overwrites it. Uploaded files are `models.EvidenceFile` (collection `evidence_files`, bytes stored inline, max 8 MB, so no GridFS; text extracted with pypdf / python-docx, capped at 50k chars); the profile references them by `file_id`. The judge prompt gets the context, the self-declared status and at most `MAX_EVIDENCE_CHARS` (3000) of evidence text per criterion. Each report stores a snapshot (`CriterionResult.evidence`, `evidence_files` = id → filename, `profile_updated_date`, rendered `system_context`); files themselves are not copied, so the admin modal only deletes files that were uploaded in the same session and never saved. `RunAssessmentRequest` is just `judge_llm_id` + `run_probes`. `/admin/?profile=<llm_id>` opens the modal directly. Uploads go through `window.matini.uploadFile` (multipart), not `common.request()`.
- **Rubrics and probes**: every criterion has a 5-level `rubric` (`nist_rmf.py: RUBRICS`) that is shared by the human assessor and the LLM judge (the judge prompt lists it), so their scores are comparable. MEASURE criteria have 3 `probe_prompts` each (the old single `probe_prompt` is kept `Optional` only so reports from before it still parse); each answer is a `ProbeResult` in `CriterionResult.probes` (`source` = `builtin`/`custom`). Old reports have `probe_transcript` instead, which the UI still shows.
- **Human assessment** (`judge_type="human"`): `POST /api/assessment/{llm_id}/manual` (`assessor_name`, no auth so it is typed in) creates a **draft** `Assessment` (status `draft`, profile snapshot, no scores), then a background job sends the MEASURE probes to the subject; `job.report_id` is the draft. The human scores each criterion on `/assessment/<llm_id>/manual/<report_id>` (`PUT /assessment/reports/update/{id}/criteria/{cid}`), can add/rerun/delete `custom` probes (`/reports/{id}/criteria/{cid}/probes/...`, reports only, not stored on the criterion), and `POST /reports/{id}/complete` (422 while a criterion has no score) computes the aggregates and sets `completed`. Completed reports are immutable (409) and cannot be discarded; drafts can (soft delete). `status` is `draft`/`completed`/`delete`; reports written before it existed have no `status` field, so queries use `$nin`/`$ne`, never `== "completed"`. `get_latest_report` ignores drafts, `get_history` includes them; the Assessment page picks a report with `?report=<id>`. The manual page deliberately shows nothing from an LLM judge (anchoring). The draft row is inserted at once but its probes are saved when the job ends, so the UI opens the page only after the job is done; the probe/score endpoints reload the report after the slow model call so a concurrent score save is not overwritten. Documents are shown from `GET /evidence-files/{id}/download?inline=true` (PDF in an iframe) or `GET /evidence-files/{id}?full=true` (extracted text).
- **Subject and judge**: both are LLMs registered in Admin, and both are called at their own `base_url` (empty means `OLLAMA_BASE_URL`). The subject (the AI being assessed) is the `llm_id` in `/assessment/<llm_id>`, and the subject dropdown just navigates to another id. The judge is chosen per run: `RunAssessmentRequest.judge_llm_id` is required, and the report stores `judge_llm_id`, `judge_llm_name` and `judge_model`. There is no `.env` judge setting any more. Judge = subject is allowed. The UI shows a warning (self-evaluation bias) and the report gets a "Judge = Subject" badge, but the API does not block it. Reports created before the judge became selectable have no `judge_llm_*` fields (they are `Optional`).
- **Guardrails are disabled** but kept in the codebase. `services/guardrails.py` is not wired into any route. Don't delete it, and don't wire it back in unless asked. `run_guardrails()` is the entry point for re-enabling it later.
- **No mock data.** Don't seed fake models or canned replies. If there are no LLMs yet, the UI tells the user to add one on the admin page. The one exception is `./scripts/seed` (`matini/cmd/seed.py`), which the developer runs by hand and the app never runs: it creates three `[ตัวอย่าง]` LLMs whose assessment profiles (context + GOVERN/MAP/MANAGE evidence and files) are written to match rubric level 1, 3 and 5, plus a `[ตัวอย่าง] Judge` LLM. It seeds no reports and no probe answers (the overall score still comes from a real run, so MEASURE varies), and each criterion's evidence text is kept under `MAX_EVIDENCE_CHARS`. The PDFs' stored text comes from `_pdf_src/` because pypdf drops Thai tone marks and upper vowels (`ใช้` → `ใช`), so a real Thai PDF uploaded on the admin page is extracted with that loss. `--reset` soft-deletes the old sample LLMs and their files.
- There is no auth on any page and CORS is `*`. This is a known limitation.

## Brython gotchas (already hit)

- `ajax.get` appends `?<timestamp>` to the URL itself, which breaks URLs that already have a query string. Always go through `common.request()`, which cache-busts with `&_=` instead.
- Use `javascript.NULL` instead of `None` when passing a null to a JS API (for example `history.pushState(NULL, "", url)`). `None` becomes a function and causes a `DataCloneError`.
- Streaming and markdown are done in JS (`window.matini.*`) because Brython can't read a `ReadableStream` well. `onLine` receives a raw string, and Python parses it with `json.loads`.
- The Brython `pythonpath` is set to `static/brython`, so pages can `from common import ...`.
- Flask caches templates unless it runs in debug mode, so restart the web server after editing a template (Brython `.py` and static files are served fresh).
- **Chrome/Chromium 154 V8 bug (found 2026-09-30, Chromium and Google Chrome 154.0.8037.57):** on a repeat page load in the same browser session, Brython can crash with `Number.prototype.toString requires that 'this' be a Number` (raised from `str.$factory`, and Brython then fails again while formatting the error). It hit `import re` / `import json` at module level, most reliably when the same page was loaded twice in a row (for example the assessment subject dropdown, which navigates from `/assessment/A` to `/assessment/B`). Disabling V8's compilation cache (`--js-flags=--no-compilation-cache`) removes it, so it is a browser bug, not an app bug. Not a fix but the mitigation that works: **do not import stdlib modules such as `json` or `re` at the top of a page script or of `common.py`; import them inside the function that needs them.** Replacing `json` with `javascript.JSON` looked attractive but made the chat and admin pages flakier, so don't. If you touch the imports, re-check with `page.goto(url)` several times in one Playwright session, on more than one page.

## Commands

```bash
poetry env use python3.13 && poetry install   # the system Python is 3.14, so pick 3.13 explicitly
docker run -d --name matini-mongo -p 27017:27017 mongo:7
./scripts/run-api            # PYTHONPATH=. poetry run python -m matini.cmd.api
./scripts/run-web
./scripts/seed [--reset] [--base-url URL] [--model TAG]   # optional sample data, defaults to the Ollama at 172.30.222.240 / llama3.2:3b
./scripts/npm run tw         # rebuild Tailwind after editing templates/brython (they're in @source)
poetry run pytest
```

- API tests (`tests/test_api.py`) use a real Mongo instance at `TEST_MONGODB_URI` (default `mongodb://localhost:27017/matinidb_test`). The database name **must** end with `_test`, because the fixture drops it. The tests skip automatically when Mongo is unreachable. Every Ollama call is mocked by monkeypatching `local_llm`.
- Web tests (`tests/test_web_routes.py`) need no API; `requests.get` is mocked in the assessment view.
- After changing the UI, check it in a real browser (`/usr/bin/chromium` is available for Playwright). Brython errors only show up in the browser console.

# CLAUDE.md

Matini is a chat app for local LLMs (Ollama) plus an ethics assessment of those models based on the NIST AI RMF. The app has only two features: **chat** and **assessment**, plus an admin page for managing LLMs. Keep it lean, and ask before adding a new feature. Most UI text and user-facing messages are in Thai, so follow that style.

## Stack and structure

Poetry monorepo, Python `>=3.12,<3.14` (Beanie 2.x has no Python 3.14 support).

- **API**: FastAPI + Beanie (MongoDB). `matini/api/`, entry point `matini/cmd/api.py` (port 8000).
- **Web**: Flask + Jinja. It only renders the page shell; the logic runs client-side in **Brython** (Python in the browser). `matini/web/`, entry point `matini/cmd/web.py` (port 8080).
- The browser calls the API directly, using the `api_url` that templates put in `<body data-api-url>`. The Flask views call the API with `requests` only when they need data at render time (the assessment page).

```
matini/
  models/          Beanie Documents (LLM, Conversation, Assessment) + BeanieClient/init_beanie
  schemas/         Pydantic schemas: bases, llms, conversations, assessment
  api/
    core/config.py   Settings (.env): MONGODB_URI, OLLAMA_BASE_URL, OLLAMA_TIMEOUT_S
    routers/         llms.py, chat.py (/conversations), assessment.py
    services/        local_llm.py (Ollama client), assessment.py (job engine), nist_rmf.py (12 criteria)
                     guardrails.py — DISABLED (see below)
    schemas/guardrails.py   guardrail schemas only
  web/
    views/           chat (/ and /c/<id>), admin (/admin/), assessment (/assessment/<llm_id>)
    templates/       base/base_layout.html, chat/, admin/, assessment/, components/navbar.html
    static/brython/  common.py (api_url, request, show_toast), chat.py, admin.py, assessment.py
    static/js/matini.js   streamNdjson() + renderMarkdown() (marked + DOMPurify)
    static/css/      setup.css (Tailwind 4 + DaisyUI source) → app.css (build output, committed), custom.css
  docs/nist-rmf-poc-guide.md   Ollama/assessment setup guide (Thai)
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
- **Subject and judge**: both are LLMs registered in Admin, and both are called at their own `base_url` (empty means `OLLAMA_BASE_URL`). The subject (the AI being assessed) is the `llm_id` in `/assessment/<llm_id>`, and the subject dropdown just navigates to another id. The judge is chosen per run: `RunAssessmentRequest.judge_llm_id` is required, and the report stores `judge_llm_id`, `judge_llm_name` and `judge_model`. There is no `.env` judge setting any more. Judge = subject is allowed. The UI shows a warning (self-evaluation bias) and the report gets a "Judge = Subject" badge, but the API does not block it. Reports created before the judge became selectable have no `judge_llm_*` fields (they are `Optional`).
- **Guardrails are disabled** but kept in the codebase. `services/guardrails.py` is not wired into any route. Don't delete it, and don't wire it back in unless asked. `run_guardrails()` is the entry point for re-enabling it later.
- **No mock data.** Don't seed fake models or canned replies. If there are no LLMs yet, the UI tells the user to add one on the admin page.
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
./scripts/npm run tw         # rebuild Tailwind after editing templates/brython (they're in @source)
poetry run pytest
```

- API tests (`tests/test_api.py`) use a real Mongo instance at `TEST_MONGODB_URI` (default `mongodb://localhost:27017/matinidb_test`). The database name **must** end with `_test`, because the fixture drops it. The tests skip automatically when Mongo is unreachable. Every Ollama call is mocked by monkeypatching `local_llm`.
- Web tests (`tests/test_web_routes.py`) need no API; `requests.get` is mocked in the assessment view.
- After changing the UI, check it in a real browser (`/usr/bin/chromium` is available for Playwright). Brython errors only show up in the browser console.

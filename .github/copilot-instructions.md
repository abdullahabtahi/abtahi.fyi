# Copilot Instructions for `abtahi.fyi`

## Development commands

Run commands from the `abtahi-fyi/` directory using Python 3.12.

```bash
# Install the application and test dependencies
.venv/bin/python -m pip install -e .[test]

# Full test suite
.venv/bin/python -m pytest -v

# One test module
.venv/bin/python -m pytest tests/test_routes_admin.py -v

# One test
.venv/bin/python -m pytest tests/test_auth_runtime.py::test_session_exchange_uses_secure_companion_cookies -v

# Run locally
.venv/bin/python -m uvicorn app.web.app:create_app --factory --reload

# Validate Markdown knowledge-graph links
.venv/bin/python -m app.core.store lint content
```

Pytest discovers tests under `tests/` and adds the repository root to
`PYTHONPATH`. Tests use `httpx.AsyncClient` with `ASGITransport` for FastAPI
routes; use the shared test environment in `tests/conftest.py` and dependency
overrides rather than contacting Firebase or Google Cloud.

## Architecture

- `app/web/app.py` is the application composition root. `create_app()` loads
  `Settings`, attaches identity and security-header middleware, mounts static
  files, and registers auth, study, public API, syndication, and admin routers.
  It also removes every private route from the generated OpenAPI document.
- Startup runs the projection lifecycle: initialize SQLite and `sqlite-vec`,
  load public Markdown content, hydrate the in-memory NetworkX cache, persist
  its graph snapshot, and populate FTS5. `/healthz` remains unavailable until
  this completes.
- The public plane serves only public knowledge-graph content and syndication
  (`/llms.txt`, JSON Feed, Atom, and `/api/fyi/q/...`). Search must preserve
  FTS5 BM25 fallback when embeddings are unavailable.
- The private study plane is authenticated through Firebase session cookies.
  It handles proposal decisions, reflections, and operations; durable review
  and idempotency records live behind the Firestore `ReviewStore` port.
  Learner-approved Connect effects are projected into owner-scoped private
  study collections only, never the public SQLite/NetworkX cache.
- `app/domain/` owns strict, mostly immutable Pydantic domain models and state
  transitions. `app/core/` provides storage, networking, security, readiness,
  Firestore, and projection services. `app/ai/` contains Gemini client and
  proposal/synthesis workflows. Routers should coordinate these layers rather
  than reimplement domain rules.

## Repository conventions

- Treat the public/private separation as a hard privacy boundary. Public
  handlers, loaders, graph data, OpenAPI, feeds, and errors must never expose
  private content, study records, review states, source details, or allowlist
  information. Public graph nodes and edges use `plane="public"`.
- Load configuration exclusively through `Settings`. It reads `.env`, rejects
  undeclared environment fields, supports Secret Manager lookup for
  `CSRF_SECRET`, and derives Firebase defaults from `GCP_PROJECT_ID`.
- Private endpoints require the established identity dependencies; stateful
  mutations additionally require CSRF validation. Session and CSRF companion
  cookies are always Secure, HttpOnly, SameSite=Lax, and use the configured
  expiry. Authentication failures have one generic public response.
- Preserve the review lifecycle invariants: Connect and Edit require reviewed
  content; Defer requires a `DeferredWindow`; only a matching dismissal
  operation can Undo a dismissal; connected proposals cannot transition again.
  Use `ReviewService` so decisions and reflections retain their per-user
  idempotency behavior.
- Content is Markdown with front matter under `content/public/`; folder names
  determine item types. Internal Markdown links create graph edges, so run the
  graph-link validator after changing public content.
- The production runtime is Python-only. Tailwind-generated static CSS is
  checked in under `app/static/css/`; do not introduce Node.js as a runtime
  dependency. If Firebase CLI or CI tooling is needed, use Node LTS 20, 22, or
  24 only.
- Gemini uses Vertex AI with Application Default Credentials when a GCP project
  is configured; an explicitly supplied non-placeholder `GEMINI_API_KEY` opts
  into the AI Studio client instead. Keep that selection centralized in
  `app/ai/client.py`.

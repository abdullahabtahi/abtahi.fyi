# Reconciled Dual-Plane MLP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a secure, tested local dual-plane abtahi.fyi MLP and all Cloud
Run/Firebase staging assets, without deploying remote resources.

**Architecture:** Public Git-backed FYI routes remain read-only and escaped.
Private study routes use verified Firebase identity, server-derived UID,
session-bound CSRF, and durable-store ports. Local SQLite stays a rebuildable
projection; cloud adapters are used only when configured.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Jinja2, HTMX, Firebase
Admin, Firestore, Cloud Storage, Secret Manager, httpx, NetworkX, SQLite,
pytest, Docker, Cloud Run.

**Spec:** `docs/superpowers/specs/2026-09-06-mlp-reconciliation-design.md`

## Global Constraints

- Public routes contain only intentionally public Git-backed content.
- Private runtime fails closed: no mock/anonymous identity outside test
  dependency overrides.
- Verify Firebase token/session, `email_verified`, and server allowlist before
  issuing a session cookie; never accept client UID or allowlist.
- Private mutations require a session-bound CSRF token and idempotency key.
- No source revision/excerpt reaches Gemini without durable revision-specific
  consent.
- Cloud Storage and Firestore are durable stores; SQLite is rebuildable only.
- Do not catch a failure and return a success-shaped response.
- Production is Python-only. Staging/prod Cloud Run labels include
  `dev-tutorial=cloud-run-ai-challenge`.

---

### Task 1: Make configuration and readiness fail closed

**Files:**
- Modify: `app/settings.py`, `app/web/app.py`, `tests/test_config.py`,
  `tests/test_health.py`
- Create: `app/core/readiness.py`, `tests/test_readiness.py`

**Interfaces:**
- Produces: `Settings`, `ReadinessState.mark_ready()`,
  `ReadinessState.mark_failed(reason)`, `ReadinessState.is_ready`.
- Produces: `/healthz` returns `200 {"status":"ok"}` only when ready and
  `503 {"status":"unavailable"}` otherwise.

- [ ] **Step 1: Write failing configuration and readiness tests**
  ```python
  def test_healthz_is_unavailable_after_initialization_failure():
      app = create_app(initialize=lambda: (_ for _ in ()).throw(RuntimeError("db")))
      assert TestClient(app).get("/healthz").status_code == 503

  def test_settings_requires_project_and_allowlist(monkeypatch):
      monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
      with pytest.raises(ValidationError):
          Settings(_env_file=None)
  ```
- [ ] **Step 2: Run focused tests**
  Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_readiness.py -v`
  Expected: FAIL because the current defaults and health route claim readiness.
- [ ] **Step 3: Implement explicit settings and readiness**
  ```python
  class ReadinessState:
      def __init__(self) -> None: self._reason: str | None = "initializing"
      def mark_ready(self) -> None: self._reason = None
      def mark_failed(self, reason: str) -> None: self._reason = reason
      @property
      def is_ready(self) -> bool: return self._reason is None
  ```
  Require non-empty project ID and allowlist. Keep secret values as `SecretStr`;
  only fetch a named secret when a project is configured, and raise a typed
  configuration error rather than swallowing a secret-manager exception.
  Inject initialization into `create_app` for tests; store readiness on
  `app.state`; never log secret values.
- [ ] **Step 4: Run focused and full tests**
  Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_readiness.py tests/test_health.py -v && .venv/bin/python -m pytest -v`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add app/settings.py app/core/readiness.py app/web/app.py tests/
  git commit -m "fix: make configuration and readiness fail closed"
  ```

### Task 2: Enforce production Firebase sessions and CSRF

**Files:**
- Modify: `app/auth/dependencies.py`, `app/auth/service.py`,
  `app/adapters/firebase_auth.py`, `app/web/csrf.py`, `app/web/app.py`
- Create: `tests/test_auth_runtime.py`
- Modify: `tests/test_auth.py`, `tests/test_csrf.py`

**Interfaces:**
- Produces: `require_identity(request) -> Identity`,
  `require_csrf(request, identity) -> None`,
  `POST /api/auth/session`, `POST /api/auth/sign-out`.
- Consumes: `TokenVerifier.verify_id_token(id_token) -> dict` and
  `verify_session_cookie(cookie) -> dict`.

- [ ] **Step 1: Write failing runtime-auth tests**
  ```python
  def test_session_exchange_rejects_unverified_or_unallowlisted_id_token(client):
      assert client.post("/api/auth/session", json={"idToken": "bad"}).status_code == 403

  def test_private_request_without_cookie_redirects_not_impersonates(client):
      assert client.get("/today", follow_redirects=False).status_code == 303
  ```
- [ ] **Step 2: Run focused test**
  Run: `.venv/bin/python -m pytest tests/test_auth.py tests/test_auth_runtime.py tests/test_csrf.py -v`
  Expected: FAIL because the app uses `MockVerifier` and grants development identity.
- [ ] **Step 3: Implement the verified-session boundary**
  Extend the protocol and Firebase adapter to verify ID tokens. At session
  exchange, call `verify_allowlisted_identity` on ID-token claims before
  `create_session_cookie`. Configure the real Firebase adapter at app
  composition; use FastAPI dependency overrides only in tests. Remove the
  absent-cookie development bypass. Generate CSRF as an HMAC of a random
  session nonce, verified UID, and secret; store nonce in a signed/secure
  companion cookie and compare with `hmac.compare_digest`. Clear both cookies
  on sign-out. Use generic 403 responses for non-allowlisted identities.
- [ ] **Step 4: Run focused and full tests**
  Run: `.venv/bin/python -m pytest tests/test_auth.py tests/test_auth_runtime.py tests/test_csrf.py -v && .venv/bin/python -m pytest -v`
  Expected: PASS, including spoofed UID, expired/missing cookie, CSRF mismatch,
  verified-email, cookie flags, and sign-out cases.
- [ ] **Step 5: Commit**
  ```bash
  git add app/auth app/adapters app/web/csrf.py app/web/app.py tests/
  git commit -m "fix: enforce verified Firebase sessions"
  ```

### Task 3: Make public routes safe and private routes truthful

**Files:**
- Modify: `app/routers/syndication.py`, `app/templates/base.html`,
  `app/templates/timeline.html`, `app/templates/graph.html`,
  `app/api/routes_study.py`
- Delete: incomplete `app/templates/capture.html` only if no complete,
  authenticated/auditable capture service exists
- Modify: `tests/test_syndication.py`, `tests/test_routes_study.py`

**Interfaces:**
- Produces: escaped public template rendering and private study GET pages.
- Produces: public endpoints that return only `ContentItem.plane == "public"`.

- [ ] **Step 1: Write failing routing/rendering tests**
  ```python
  def test_semantic_query_is_escaped(client):
      response = client.get("/api/semantic/%3Cscript%3Ealert(1)%3C/script%3E")
      assert "<script>" not in response.text

  def test_authenticated_sources_page_does_not_raise(client):
      assert client.get("/sources").status_code == 200
  ```
- [ ] **Step 2: Run focused tests**
  Run: `.venv/bin/python -m pytest tests/test_syndication.py tests/test_routes_study.py -v`
  Expected: FAIL on script interpolation and undefined `nav_html`.
- [ ] **Step 3: Replace string HTML and placeholder navigation**
  Render every HTML route with Jinja templates and context values, relying on
  autoescape. Remove direct query interpolation. Centralize navigation in
  `base.html`; render private nav only after `require_identity`. Retain public
  parent-plan routes, but filter private content before search/feed/graph
  loading. Remove `/capture` from navigation and routing until its required
  durable, authorized service exists. Do not show Connect/Defer/Dismiss/Edit
  controls until Task 4 wires durable operations.
- [ ] **Step 4: Run focused and full tests**
  Run: `.venv/bin/python -m pytest tests/test_syndication.py tests/test_routes_study.py -v && .venv/bin/python -m pytest -v`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add app/routers app/api/routes_study.py app/templates tests/
  git commit -m "fix: separate safe public and private routes"
  ```

### Task 4: Implement durable learner decisions and truthful HTMX actions

**Files:**
- Modify: `app/core/firestore.py`, `app/domain/models.py`,
  `app/api/routes_study.py`, `app/templates/today.html`
- Create: `app/services/review.py`, `tests/test_review_service.py`
- Modify: `tests/test_routes_study.py`, `tests/fakes.py`

**Interfaces:**
- Produces: `ReviewStore.run_once(uid, key, digest, operation) -> ReviewResult`.
- Produces: `ReviewService.decide(identity, proposal_id, command, key)`.
- Private decision endpoints consume `Idempotency-Key` and return a real saved
  result or explicit retryable/unavailable failure.

- [ ] **Step 1: Write failing idempotency and route tests**
  ```python
  async def test_same_key_returns_original_result():
      first = await service.decide(identity, "p1", DecisionCommand.CONNECT, "k")
      assert await service.decide(identity, "p1", DecisionCommand.CONNECT, "k") == first

  def test_connect_requires_idempotency_key(client):
      assert client.post("/api/proposals/p1/connect", headers=csrf).status_code == 400
  ```
- [ ] **Step 2: Run focused tests**
  Run: `.venv/bin/python -m pytest tests/test_review_service.py tests/test_routes_study.py -v`
  Expected: FAIL because handlers generate UUIDs, mismatch templates, and report false success.
- [ ] **Step 3: Implement a single durable operation path**
  Add Firestore owner-scoped `operations/{key}` records holding digest, result,
  and status. Reject key reuse with a different digest. Build `InteractionRecord`
  with UTC timestamp and `DecisionCommand` enum. Implement Connect, Defer,
  Dismiss, Edit, reflection, and status lookup through the same service.
  When Firestore is unavailable, return `503` and do not render success.
  Make `/today` pass zero-to-three real proposals; align HTMX URLs/headers and
  include Retry-preserving markup.
- [ ] **Step 4: Run focused and full tests**
  Run: `.venv/bin/python -m pytest tests/test_review_service.py tests/test_routes_study.py -v && .venv/bin/python -m pytest -v`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add app/core/firestore.py app/services app/domain app/api app/templates tests/
  git commit -m "feat: persist idempotent learner decisions"
  ```

### Task 5: Gate ingestion and Gemini by safety, consent, and provenance

**Files:**
- Modify: `app/core/security.py`, `app/ingest/poller.py`, `app/ai/proposer.py`,
  `app/routers/admin.py`
- Create: `app/services/consent.py`, `app/storage/archive.py`,
  `tests/test_consent.py`, `tests/test_safe_poller.py`
- Modify: `tests/test_proposer.py`, `tests/test_security.py`,
  `tests/test_routes_admin.py`

**Interfaces:**
- Produces: `validate_fetch_target(url, resolver) -> URL`,
  `PollResult(status: Literal["completed", "skipped", "failed"])`,
  `ConsentStore.has_grant(uid, revision_id, purpose, provider) -> bool`.
- `generate_proposal` consumes immutable `SourceRevision` and validated consent,
  never raw arbitrary chunk IDs.

- [ ] **Step 1: Write failing guard and consent tests**
  ```python
  async def test_redirect_to_ipv6_loopback_is_blocked(): ...
  async def test_private_chunk_without_revision_consent_never_calls_model(): ...
  def test_poll_route_returns_failure_when_not_dispatched(): ...
  ```
- [ ] **Step 2: Run focused tests**
  Run: `.venv/bin/python -m pytest tests/test_safe_poller.py tests/test_consent.py tests/test_proposer.py -v`
  Expected: FAIL because redirects/body limits/consent/durable revisions are absent.
- [ ] **Step 3: Implement bounded services**
  Allow registered canonical feeds only. Resolve IPv4/IPv6 on every initial and
  redirect URL, reject non-global ranges and metadata addresses, disable automatic
  redirects, cap at three, stream at most 5 MB, and use 5/15-second timeouts.
  Archive each normalized revision with content hash before indexing. Require
  matching durable consent before stateless `models.generate_content`; fence
  untrusted input and validate structured output, exact quotes, edge types, and
  known concept targets. Admin poll/consolidate routes require a dedicated
  scheduler/admin verifier and return explicit job state, never unconditional 202.
- [ ] **Step 4: Run focused and full tests**
  Run: `.venv/bin/python -m pytest tests/test_safe_poller.py tests/test_consent.py tests/test_proposer.py tests/test_security.py tests/test_routes_admin.py -v && .venv/bin/python -m pytest -v`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add app/core/security.py app/ingest app/ai app/services app/storage app/routers tests/
  git commit -m "feat: gate source processing by consent and provenance"
  ```

### Task 6: Add deployment assets and release verification

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `infra/service.staging.yaml`,
  `infra/service.production.yaml`, `infra/firestore.rules`,
  `docs/staging-checklist.md`
- Modify: `README.md`, `tests/test_health.py`

**Interfaces:**
- Produces: Python-only Cloud Run image, staging/prod service manifests, and
  deny-by-default Firestore rules.

- [ ] **Step 1: Write failing manifest/readiness tests**
  ```python
  def test_service_manifests_include_required_challenge_label():
      assert "dev-tutorial=cloud-run-ai-challenge" in staging_manifest
      assert "dev-tutorial=cloud-run-ai-challenge" in production_manifest
  ```
- [ ] **Step 2: Run focused tests**
  Run: `.venv/bin/python -m pytest tests/test_health.py tests/test_deployment_assets.py -v`
  Expected: FAIL because assets do not exist.
- [ ] **Step 3: Implement deployable artifacts**
  Use non-root Python image and `uvicorn app.web.app:create_app` entrypoint.
  Reference Secret Manager/platform env vars by name only; never embed values.
  Add staging and production manifests with service label, minimum permissions
  guidance, health path, and no public storage. Add Firestore deny-by-default
  owner rules. Document required project-specific values, staging checks,
  rollback by traffic shift, and explicit “do not deploy without project ID”
  gate.
- [ ] **Step 4: Run verification**
  Run: `.venv/bin/python -m pytest -v && docker build -t abtahi-fyi:local .`
  Expected: all tests pass and image builds.
- [ ] **Step 5: Commit**
  ```bash
  git add Dockerfile .dockerignore infra docs/staging-checklist.md README.md tests/
  git commit -m "chore: add staging-ready deployment assets"
  ```

## Plan self-review

- Public plane safety: Tasks 1 and 3.
- Verified private identity/CSRF: Task 2.
- Idempotent learner decisions and retry truthfulness: Task 4.
- Immutable sources, SSRF, consent, model validation: Task 5.
- Readiness, Cloud Run label, Firestore rules, staging gate: Task 6.
- No task deploys remote resources; user-provided project ID remains a required
  later authorization boundary.

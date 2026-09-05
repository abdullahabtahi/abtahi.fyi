# Private Compiled Study Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a staging-ready, private WorldQuant/BlueDot learning pilot
where one allowlisted learner reviews consent-gated, evidence-backed
source-to-concept proposals without risking private data, duplicate decisions,
or data loss.

**Architecture:** FastAPI renders a server-driven private experience. Cloud
Storage stores immutable source revisions and Firestore stores durable
user-scoped consent, review, reflection, idempotency, and job records; local
SQLite is a rebuildable WAL/FTS5/sqlite-vec graph/search projection. Cloud
adapters sit behind protocols so deterministic tests run without cloud
credentials; only the stateless Gemini batch proposer is included.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Jinja2, HTMX, Alpine.js,
SQLite/FTS5/sqlite-vec, NetworkX, Firebase Auth Admin SDK, Firestore, Cloud
Storage, Secret Manager, `httpx`, `feedparser`, `beautifulsoup4`, `pytest`,
Cloud Run, and Firebase CLI (Node LTS 20/22/24 tooling only).

**Spec:** `docs/superpowers/specs/2026-09-05-private-compiled-study-pilot-design.md`

## Global Constraints

- All committed project artifacts remain under `/Users/abdullahabtahi/Ideathon/abtahi-fyi`.
- The pilot is private, single-account, and Google SSO only; custom password
  handling is prohibited.
- Production runtime has no Node.js dependency; Firebase CLI/CI uses Node LTS
  20, 22, or 24.
- Public FYI pages, feeds, agent endpoints, full-graph exploration, multiple
  feeds, course-provider integrations, and the stateful `/capture` copilot are
  out of scope.
- The only feed is `https://blog.bluedot.org/feed`; do not register
  `?format=atom`.
- Raw private content, excerpts, reflections, consent, and audit data never
  enter Git, public responses, logs, telemetry, or external-model requests
  without source-revision-specific consent.
- Private routes require a verified Firebase session, verified email, server
  allowlist match, CSRF validation for mutations, and idempotency keys.
- Cookies use `Secure`, `HttpOnly`, and `SameSite=Lax`.
- Cloud Run staging and production services carry
  `dev-tutorial=cloud-run-ai-challenge`.
- Cloud Storage is the immutable archive and Firestore the durable interaction
  store; local SQLite is rebuildable and never the only durable copy.
- `/today` renders zero to three proposals; no streaks, unread counts,
  catch-up pressure, or overdue state.
- Agent output can propose only. Only learner Connect can activate an edge;
  model calls use the stateless `models.generate_content` path only.
- Every implementation task follows red-green-refactor and runs its focused
  tests before its commit.

## File Structure

```text
abtahi-fyi/
├── app/
│   ├── api/                  # HTTP auth, study, and protected job routes
│   ├── auth/                 # Firebase verification, session, CSRF, allowlist
│   ├── domain/               # Pydantic types and pure lifecycle rules
│   ├── ingest/               # SSRF-safe polling, normalization, archival
│   ├── services/             # Consent, proposals, projection, retry services
│   ├── storage/              # Protocols plus Firestore/Storage/SQLite adapters
│   ├── web/                  # App factory, templates, static assets
│   └── settings.py           # Validated non-secret configuration
├── content/seed/             # Non-sensitive Module 1 concept metadata only
├── infra/                    # Firestore rules, Cloud Run deployment config
├── tests/                    # Unit, API, integration-contract, and smoke tests
├── Dockerfile
├── pyproject.toml
└── README.md
```

### Task 1: Establish the Repository and Testable Application Baseline

**Files:**
- Create: `.gitignore`
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/web/__init__.py`
- Create: `app/web/app.py`
- Create: `tests/test_health.py`
- Create: `README.md`

**Interfaces:**
- Produces: `app.web.app.create_app() -> FastAPI`.
- Produces: `GET /healthz` returning `{"status": "ok"}` without private data.
- Consumed by: every later route and test.

- [ ] **Step 1: Initialize only the approved project root as a Git repository**

Run from `/Users/abdullahabtahi/Ideathon/abtahi-fyi`:

```bash
git init
git switch -c main
```

Create `.gitignore` before any credentials or local state can be introduced:

```gitignore
.venv/
__pycache__/
.pytest_cache/
*.py[cod]
.env
.env.*
!.env.example
data/
firebase-debug.log
service-account*.json
```

- [ ] **Step 2: Add the failing health-route test**

```python
from fastapi.testclient import TestClient

from app.web.app import create_app


def test_healthz_returns_only_readiness_status() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run the test and verify it fails because the application factory is missing**

Run: `python -m pytest tests/test_health.py::test_healthz_returns_only_readiness_status -v`

Expected: FAIL during import because `app.web.app` or `create_app` does not
exist.

- [ ] **Step 4: Add the minimal package manifest and application factory**

Create this `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "abtahi-fyi"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "beautifulsoup4>=4.12.3", "fastapi>=0.115.0", "feedparser>=6.0.11",
  "firebase-admin>=6.5.0", "google-cloud-firestore>=2.19.0",
  "google-cloud-secret-manager>=2.20.0", "google-cloud-storage>=2.18.0",
  "google-genai>=0.1.0", "httpx>=0.28.0", "jinja2>=3.1.5",
  "networkx>=3.4.0", "pydantic>=2.10.0", "python-multipart>=0.0.20",
  "sqlite-vec>=0.1.6", "uvicorn[standard]>=0.34.0",
]

[project.optional-dependencies]
test = ["httpx>=0.28.0", "pytest>=8.3.0", "pytest-asyncio>=0.24.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Implement:

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

Set `.python-version` to `3.12`. Document local setup, the zero-Node production
constraint, and that remote Firebase/GCP resources are configured later.

- [ ] **Step 5: Run the focused test and establish the clean baseline**

Run:

```bash
python -m pytest tests/test_health.py -v
git add .
git commit -m "chore: establish FastAPI pilot baseline"
```

Expected: the test passes and the initial commit contains no private artifacts.

### Task 2: Define Validated Pilot Domain Types and Seed Concept Metadata

**Files:**
- Create: `app/domain/__init__.py`
- Create: `app/domain/models.py`
- Create: `app/domain/lifecycle.py`
- Create: `content/seed/worldquant-module-1.yaml`
- Create: `tests/test_domain_models.py`

**Interfaces:**
- Produces: `ProposalStatus`, `EdgeType`, `MatchStrength`, `SourceRevision`,
  `ConnectionProposal`, `CandidateConcept`, `DecisionCommand`.
- Produces: `ProposalTransition(previous_status, next_status, command)` and
  `validate_transition(proposal, command) -> ProposalTransition`.
- Consumed by: archive, consent, proposal, graph, and route services.

- [ ] **Step 1: Write failing domain tests**

```python
import pytest
from pydantic import ValidationError

from app.domain.models import ConnectionProposal, EdgeType, MatchStrength


def test_adjacent_proposal_requires_analogy_and_difference() -> None:
    with pytest.raises(ValidationError):
        ConnectionProposal(
            id="proposal-1", source_revision_id="source-1", concept_id="cascade",
            edge_type=EdgeType.RELATED_TO, match_strength=MatchStrength.ADJACENT,
            excerpt="A short source passage.", location="Paragraph 3",
            rationale="It is related.", uncertainty="The mechanism differs.",
            learning_payoff="Gives an example."
        )
```

Add tests that reject an unsupported edge type, an empty excerpt/location,
Connect without final reviewed content, and a Candidate concept marked active
without learner approval.

- [ ] **Step 2: Run the domain tests and verify they fail because the types do not exist**

Run: `python -m pytest tests/test_domain_models.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement strict types and the course seed**

Use Pydantic v2 `ConfigDict(extra="forbid")`. `ConnectionProposal` includes
immutable source revision ID, target concept ID, edge type, match strength,
excerpt, location, rationale, uncertainty, learning payoff, and the proposed
cited addition. For `ADJACENT`, require non-empty `analogy`, `difference`, and
`distinction_impact`.

Seed exactly one active concept:

```yaml
id: hidden-dependencies-cascading-failure
title: Hidden dependencies and cascading failure
course: WorldQuant Foundations of Disruption
module: 1
causal_spine:
  - system architecture
  - hidden dependencies / coupling
  - cascade risk
  - stakeholder impacts
  - accountability and intervention
```

Model decisions as `CONNECT`, `DEFER`, `DISMISS`, and `EDIT`; model deferred
windows as `TOMORROW`, `NEXT_WEEK`, and `LATER`.

- [ ] **Step 4: Run the domain tests and commit**

Run:

```bash
python -m pytest tests/test_domain_models.py -v
git add app/domain content/seed tests/test_domain_models.py
git commit -m "feat: define private study domain contracts"
```

Expected: all domain validation tests pass.

### Task 3: Implement Settings, Secrets, Firebase Verification, and CSRF

**Files:**
- Create: `app/settings.py`
- Create: `app/auth/__init__.py`
- Create: `app/auth/service.py`
- Create: `app/auth/dependencies.py`
- Create: `tests/test_auth.py`

**Interfaces:**
- Produces: `Settings.from_environment() -> Settings`.
- Produces: `Identity(uid: str, email: str)`.
- Produces: `ForbiddenError`, raised for a missing, invalid, unverified, or
  non-allowlisted identity.
- Produces: `require_identity(request) -> Identity`,
  `require_csrf(request) -> None`.
- Consumed by: all private HTTP routes and Firestore path derivation.

- [ ] **Step 1: Write failing authorization tests**

```python
def test_rejects_verified_token_for_non_allowlisted_email() -> None:
    verifier = FakeTokenVerifier({"uid": "other", "email": "other@example.com",
                                  "email_verified": True})

    with pytest.raises(ForbiddenError):
        verify_allowlisted_identity(verifier, "token", "owner@example.com")
```

Add tests rejecting missing/false `email_verified`, a missing session, invalid
CSRF token, and settings that omit the allowlist or required bucket/project
identifiers. Add a test that asserts secret values never appear in a settings
validation error.

- [ ] **Step 2: Run the tests and verify missing authentication functions fail**

Run: `python -m pytest tests/test_auth.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the security boundary**

Define a `TokenVerifier` protocol so tests use a fake and production uses
Firebase Admin session-cookie verification. Exchange a Firebase ID token at
`POST /api/auth/session`, checking `email_verified` and equality to the
Secret-Manager-backed `ALLOWED_LEARNER_EMAIL` setting before issuing the
session. Configure session cookies as Secure, HttpOnly, SameSite Lax.

Use `secrets.token_urlsafe` for CSRF issuance and
`hmac.compare_digest` to validate a token stored server-side or in a signed
session value. Require `X-CSRF-Token` on every mutation. Do not receive a UID
from a route/body/form; derive it solely from the verified identity.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python -m pytest tests/test_auth.py -v
git add app/settings.py app/auth tests/test_auth.py
git commit -m "feat: enforce allowlisted Firebase sessions"
```

Expected: valid allowlisted identity is accepted; all invalid identity and CSRF
cases are rejected.

### Task 4: Build Durable Adapter Protocols and Idempotent Interaction Records

**Files:**
- Create: `app/storage/__init__.py`
- Create: `app/storage/protocols.py`
- Create: `app/storage/firestore.py`
- Create: `app/storage/gcs.py`
- Create: `app/storage/memory.py`
- Create: `infra/firestore.rules`
- Create: `tests/test_storage_contracts.py`

**Interfaces:**
- - Produces: `OperationStatus` (`ACCEPTED`, `RETRYABLE_FAILURE`,
  `CONFLICT`) and `OperationResult(status, operation_id, message,
  payload)`.
- Produces: `IdempotencyRecord(uid, key, request_digest, result)`,
  `InteractionStore`, and `SourceArchive`.
- Produces: `InteractionStore.run_once(uid: str, key: str,
  request_digest: str, operation: Callable[[], OperationResult]) ->
  OperationResult`.
- Consumed by: all state mutations and source archival.

- [ ] **Step 1: Write failing adapter-contract tests**

```python
def test_run_once_returns_original_connect_result_on_retry() -> None:
    store = InMemoryInteractionStore()
    first = store.run_once("owner-uid", "same-key", "request-hash", connect_operation)
    second = store.run_once("owner-uid", "same-key", "request-hash", connect_operation)

    assert second == first
    assert connect_operation.call_count == 1
```

Add tests that every Firestore document path starts
`users/{verified_uid}/`, uses no caller-supplied UID, and that archive object
keys include source ID and SHA-256 revision hash. Test write-once archive
semantics and mismatch rejection.

- [ ] **Step 2: Run the tests and verify the adapter interfaces are missing**

Run: `python -m pytest tests/test_storage_contracts.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement protocol-first durable stores**

Define synchronous or async protocols consistently across all adapters. The
Firestore implementation records operations under the verified UID and stores
the idempotency key, request digest, final operation result, and timestamp.
Reject re-use of a key with a different request digest. The GCS archive writes
immutable objects with create-only preconditions and object metadata for
canonical URL, source ID, revision hash, and capture time.

Use in-memory adapters only in tests. Firestore rules must deny by default and
allow `users/{userId}/...` only when `request.auth.uid == userId`; never write
an unrestricted rule.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python -m pytest tests/test_storage_contracts.py -v
git add app/storage infra/firestore.rules tests/test_storage_contracts.py
git commit -m "feat: add durable private storage contracts"
```

Expected: duplicate operations are single-effect and archive revisions cannot
be overwritten.

### Task 5: Implement SSRF-Safe BlueDot Feed Ingestion and Immutable Revisions

**Files:**
- Create: `app/ingest/__init__.py`
- Create: `app/ingest/urls.py`
- Create: `app/ingest/poller.py`
- Create: `app/ingest/normalize.py`
- Create: `app/services/source_archive.py`
- Create: `tests/test_ingest_security.py`
- Create: `tests/test_source_archive.py`

**Interfaces:**
- Produces: `FeedEntry(title, canonical_url, published_at, html)`,
  `PollOutcome(status, entries, message)`, and
  `HostResolver.resolve(hostname) -> list[ipaddress.IPv4Address |
  ipaddress.IPv6Address]`.
- Produces: `UnsafeOutboundURL`, raised before a blocked address can receive a
  network request.
- Produces: `canonicalize_url(url: str) -> str`.
- Produces: `validate_fetch_target(url: str, resolver: HostResolver) -> URL`.
- Produces: `poll_registered_feed() -> PollOutcome`.
- Produces: `archive_revision(entry: FeedEntry) -> SourceRevision`.
- Consumed by: consent queue and SQLite projection rebuild.

- [ ] **Step 1: Write failing canonicalization, SSRF, and revision tests**

```python
def test_blocks_metadata_address_after_dns_resolution() -> None:
    resolver = FakeResolver({"feed.example": ["169.254.169.254"]})

    with pytest.raises(UnsafeOutboundURL):
        validate_fetch_target("https://feed.example/rss", resolver)
```

Add tests for `127.0.0.1`, `::1`, RFC 1918 IPv4, IPv6 unique-local/link-local,
redirect-to-private targets, non-HTTP schemes, DNS rebinding, a 5 MB+ body,
four redirects, UTM removal, same canonical URL/content deduplication, and
same URL/new-content revision creation.

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
python -m pytest tests/test_ingest_security.py tests/test_source_archive.py -v
```

Expected: FAIL during import.

- [ ] **Step 3: Implement constrained polling**

Hardcode the registered pilot feed in non-secret seed configuration; reject
attempts to add a second feed or its `?format=atom` duplicate. Use
`httpx.AsyncClient(follow_redirects=False)` and validate each next Location
before fetching. Resolve and validate all returned address families; do not
trust only the initial hostname. Enforce five concurrent fetches, 5-second
connect timeout, 15-second read timeout, three redirects, conditional headers,
and streaming response-size enforcement.

Normalize HTML to safe readable text, calculate SHA-256 on normalized
whitespace, and send immutable representations to `SourceArchive`. Return
explicit `completed`, `skipped`, or `failed` outcomes; never convert a failed
fetch to an empty successful feed.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python -m pytest tests/test_ingest_security.py tests/test_source_archive.py -v
git add app/ingest app/services/source_archive.py tests/test_ingest_security.py tests/test_source_archive.py
git commit -m "feat: ingest BlueDot sources safely"
```

Expected: malicious fetch targets are blocked and revisions are immutable.

### Task 6: Add Consent-Gated Stateless Proposal Generation and Quality Gates

**Files:**
- Create: `app/services/consent.py`
- Create: `app/services/proposals.py`
- Create: `app/ai/__init__.py`
- Create: `app/ai/batch.py`
- Create: `app/ai/prompts.py`
- Create: `tests/test_consent_and_proposals.py`
- Create: `tests/test_batch_resilience.py`

**Interfaces:**
- Produces: `Consent(uid, revision_id, request_id, approved,
  provider, purpose)` and `ProposalOutcome(status, proposal, message)`.
- Produces: `BatchModel.generate(prompt: str) -> str`.
- Produces: `record_consent(uid, revision_id, request_id, approved) -> Consent`.
- Produces: `propose_connection(revision_id, concept_id) -> ProposalOutcome`.
- Produces: `validate_proposal(proposal) -> ConnectionProposal`.
- Consumed by: protected jobs and `/today`.

- [ ] **Step 1: Write failing consent and quality-gate tests**

```python
def test_declined_consent_never_calls_batch_model() -> None:
    outcome = proposal_service.generate_for_revision(
        identity=OWNER, revision_id="rev-1", consent=False
    )

    assert outcome.status == "consent_required_or_declined"
    assert fake_batch.calls == []
```

Add tests that prompts wrap source text in `<untrusted_content>` fences,
invalid structured output is suppressed, a missing citation/location is
suppressed, an adjacent match needs analogy/difference/impact, a weak proposal
does not consume a `/today` slot, and only recoverable 429/500/503 provider
errors retry with a finite ladder.

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
python -m pytest tests/test_consent_and_proposals.py tests/test_batch_resilience.py -v
```

Expected: FAIL during import.

- [ ] **Step 3: Implement consent and stateless batch interfaces**

Consent records are keyed by verified UID, revision ID, and explicit processing
request ID. The request describes source, data category, purpose, and provider.
No raw/excerpt material reaches `models.generate_content` without an approved
matching record.

Define a `BatchModel` protocol. Its production implementation invokes only
`client.aio.models.generate_content`; do not import or configure
`interactions.create` or `/capture`. Parse the response through Pydantic,
validate excerpt containment against the immutable revision, validate target
concept/relationship, and persist only learner-reviewable proposal records.
Provider failures return explicit retryable outcomes and redacted diagnostics.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python -m pytest tests/test_consent_and_proposals.py tests/test_batch_resilience.py -v
git add app/ai app/services/consent.py app/services/proposals.py tests/test_consent_and_proposals.py tests/test_batch_resilience.py
git commit -m "feat: generate consent-gated connection proposals"
```

Expected: no proposal is generated without consent or valid evidence.

### Task 7: Build the Reconstructable SQLite Projection and Focused Graph

**Files:**
- Create: `app/storage/sqlite_projection.py`
- Create: `app/services/projection.py`
- Create: `app/services/graph.py`
- Create: `tests/test_projection.py`
- Create: `tests/test_graph.py`

**Interfaces:**
- Produces: `DurableSnapshot(revisions, concepts, approved_proposals)`,
  `RebuildResult(active_edge_ids, projection_version)`, `Edge(id,
  proposal_id, source_revision_id, concept_id, edge_type)`, and
  `FocusedGraph(nodes, edges, relations)`.
- Produces: `rebuild_projection(snapshot: DurableSnapshot) -> RebuildResult`.
- Produces: `activate_approved_edge(proposal) -> Edge`.
- Produces: `focused_neighborhood(concept_id, hops=2) -> FocusedGraph`.
- Consumed by: readiness, `/today`, concept pages, and graph/list rendering.

- [ ] **Step 1: Write failing projection and graph tests**

```python
def test_rebuild_restores_only_approved_edges_with_citations() -> None:
    result = rebuild_projection(snapshot_with_approved_and_pending_proposals)

    assert result.active_edge_ids == {"edge-approved"}
    assert result.citation("edge-approved").revision_id == "revision-1"
```

Add tests for WAL and foreign keys enabled, a dangling source/concept reference
failing rebuild, unapproved edges excluded, a one-to-two-hop graph bounded to
the requested hops, and structured relation rows matching graph edge IDs and
labels.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_projection.py tests/test_graph.py -v
```

Expected: FAIL during import.

- [ ] **Step 3: Implement the disposable read projection**

Open SQLite with WAL, foreign keys, busy timeout, and a single-writer lock.
Create relational provenance tables plus FTS5; load sqlite-vec only when the
runtime supports it and make readiness fail clearly when the configured vector
projection cannot be built. Rebuild from Storage source metadata and
Firestore-approved records in one transactional replacement, then atomically
replace the ready projection.

Build a NetworkX directed graph only from approved edges. Store exact
revision/citation/proposal provenance with each edge. Return Canvas-safe graph
data and an equivalent structured list; never require hover, drag, or color to
understand an edge.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python -m pytest tests/test_projection.py tests/test_graph.py -v
git add app/storage/sqlite_projection.py app/services/projection.py app/services/graph.py tests/test_projection.py tests/test_graph.py
git commit -m "feat: rebuild private study graph projections"
```

Expected: an instance restart can reconstruct a consistent approved graph from
durable stores.

### Task 8: Implement Proposal Decisions, Recovery, and Transfer Prompts

**Files:**
- Create: `app/services/review.py`
- Create: `app/services/reflections.py`
- Create: `tests/test_review_lifecycle.py`
- Create: `tests/test_recovery.py`

**Interfaces:**
- Produces: `TransferPrompt(kind, due_at, text, proposal_id)` where `kind`
  is `NEXT_DAY_REFLECTION` or `ONE_WEEK_NEW_CASE`.
- Produces: `review_proposal(identity, command, idempotency_key) -> OperationResult`.
- Produces: `save_reflection(identity, response, idempotency_key) -> OperationResult`.
- Produces: `due_transfer_prompts(identity, now) -> list[TransferPrompt]`.
- Consumed by: private HTTP routes.

- [ ] **Step 1: Write failing lifecycle and recovery tests**

```python
def test_connect_retry_creates_one_edge_and_returns_same_result() -> None:
    first = review_proposal(OWNER, connect_command("p-1"), "key-1")
    second = review_proposal(OWNER, connect_command("p-1"), "key-1")

    assert second == first
    assert projection.active_edge_count() == 1
```

Add tests for all four actions, invalid defer windows, Edit requiring final
Connect/Defer/Dismiss, candidate concepts not consuming daily slots, Firestore
unavailability preserving unsaved form data in the route result, and optional
next-day/one-week prompts having no overdue state.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_review_lifecycle.py tests/test_recovery.py -v
```

Expected: FAIL during import.

- [ ] **Step 3: Implement single-effect review orchestration**

Run decisions through `InteractionStore.run_once`. Connect writes the durable
approved decision and citation provenance first, triggers a projection refresh,
then returns the cited evidence and focused graph update. If projection refresh
fails after the durable write, return `accepted_projection_pending`; do not
claim the UI updated. A status lookup with the same key resolves timeout
ambiguity.

Represent unsaved failures as an explicit `retryable_failure` payload
containing safe message, original values, and retry key. The browser retains
its input. Store optional reflection and transfer responses privately, without
grading, streaks, or late status.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python -m pytest tests/test_review_lifecycle.py tests/test_recovery.py -v
git add app/services/review.py app/services/reflections.py tests/test_review_lifecycle.py tests/test_recovery.py
git commit -m "feat: add idempotent learner review decisions"
```

Expected: retries are safe, inputs survive failed saves, and only Connect
activates an edge.

### Task 9: Deliver the Accessible Private HTTP and HTMX Experience

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/auth.py`
- Create: `app/api/study.py`
- Create: `app/api/jobs.py`
- Create: `app/web/templates/base.html`
- Create: `app/web/templates/today.html`
- Create: `app/web/templates/concept.html`
- Create: `app/web/templates/sources.html`
- Create: `app/web/templates/partials/proposal.html`
- Create: `app/web/static/css/styles.css`
- Create: `app/web/static/js/auth.js`
- Create: `tests/test_private_routes.py`
- Create: `tests/test_privacy_boundary.py`

**Interfaces:**
- Produces: `GET /today`, `GET /concepts/{concept_id}`, `GET /sources`.
- Produces: protected POST review/consent/reflection routes and an operation
  status route at `GET /api/operations/{idempotency_key}`.
- Consumes: `require_identity`, `require_csrf`, review, consent, and graph
  services.

- [ ] **Step 1: Write failing private-route tests**

```python
def test_today_requires_authentication() -> None:
    response = TestClient(create_app()).get("/today", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/sign-in"
```

Add tests that non-allowlisted access returns generic 403 without proposal
content, `/today` contains at most three proposal IDs and all four visible
actions, mutation routes reject missing CSRF/idempotency headers, consent
refusal says no proposal was generated, and no private route/template/error
response is exposed by any public path.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_private_routes.py tests/test_privacy_boundary.py -v
```

Expected: FAIL because the routes and templates are absent.

- [ ] **Step 3: Implement server-rendered private routes**

Mount no public content routes other than `/healthz` in this pilot. Mount
private routes behind identity dependencies. Add Google sign-in JavaScript only
for Firebase ID-token acquisition; the server remains authoritative for
allowlist and session verification.

Render source identity, immutable revision/location, exact excerpt, target
concept, match strength, relationship, rationale, uncertainty, and visible
Connect/Defer/Dismiss/Edit controls before a decision. Render direct and
adjacent labels in text. Ensure 44px controls, visible focus, 16px body copy,
reduced-motion-safe graph behavior, and a semantic structured relationship
list beside or below the focused graph. Return explicit HTMX retry partials
without clearing submitted fields.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
python -m pytest tests/test_private_routes.py tests/test_privacy_boundary.py -v
git add app/api app/web tests/test_private_routes.py tests/test_privacy_boundary.py
git commit -m "feat: render private signal review flows"
```

Expected: the private review is usable without exposing private data publicly.

### Task 10: Add Protected Jobs, Deployment Assets, and Staging Evidence

**Files:**
- Create: `app/services/jobs.py`
- Create: `infra/cloudrun-staging.yaml`
- Create: `infra/cloudrun-production.yaml`
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `tests/test_jobs.py`
- Create: `tests/test_deployment_assets.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `JobOutcome(status, operation_id, retry_count, message)` where
  `status` is `COMPLETED`, `SKIPPED`, or `FAILED`.
- Produces: protected `POST /api/jobs/poll-feed` and
  `POST /api/jobs/rebuild-projection`.
- Produces: `JobRunner.run_poll() -> JobOutcome`,
  `JobRunner.run_rebuild() -> JobOutcome`.
- Produces: Cloud Run deployment manifests with non-secret secret references
  and the mandatory service label.

- [ ] **Step 1: Write failing job and deployment tests**

```python
def test_staging_manifest_has_required_service_label() -> None:
    manifest = load_yaml("infra/cloudrun-staging.yaml")

    assert manifest["metadata"]["labels"]["dev-tutorial"] == "cloud-run-ai-challenge"
```

Add tests that job routes reject a learner cookie and require scheduler/admin
OIDC identity, transient jobs stop after their configured retry budget,
non-idempotent learner mutations are never job-retried, both manifests contain
only secret references, and Docker context excludes `.env`, source archives,
and service-account JSON files.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_jobs.py tests/test_deployment_assets.py -v
```

Expected: FAIL because jobs and deployment assets are absent.

- [ ] **Step 3: Implement operations assets**

Implement protected job authentication using a separately configured
scheduler/admin OIDC verifier. Persist `completed`, `skipped`, or `failed`
job outcomes. Retry only idempotent poll/rebuild work with finite exponential
backoff; log an operation ID and category, never source/excerpt/token content.

Build a non-root Python 3.12 Cloud Run image with a `/healthz` probe. Create
separate staging and production manifests with different service names and
least-privilege runtime service accounts. Both manifests must include:

```yaml
metadata:
  labels:
    dev-tutorial: cloud-run-ai-challenge
```

Use Secret Manager references for `ALLOWED_LEARNER_EMAIL`, Firebase settings,
and Gemini credentials; do not put values in manifests. Document staging
deployment, authenticated smoke tests, readiness verification, and rollback to
the last healthy revision. Do not deploy remote resources in this task.

- [ ] **Step 4: Run focused tests, full suite, and commit**

Run:

```bash
python -m pytest tests/test_jobs.py tests/test_deployment_assets.py -v
python -m pytest -v
git add app/services/jobs.py infra Dockerfile .dockerignore README.md tests/test_jobs.py tests/test_deployment_assets.py
git commit -m "feat: prepare secure Cloud Run pilot deployment"
```

Expected: all tests pass; manifests are label-compliant and contain no
plaintext secrets.

### Task 11: Run the Staging Release Checklist and Capture Promotion Evidence

**Files:**
- Create: `docs/release/staging-pilot-checklist.md`
- Create: `docs/release/production-promotion-template.md`
- Test: `tests/`

**Interfaces:**
- Consumes: all prior tests, staging manifest, Firebase project ID supplied by
  the learner at deployment time, and Cloud Run revision identity.
- Produces: an evidence record containing test output, staging revision,
  authenticated smoke outcome, readiness outcome, rollback target, and
  approval status.

- [ ] **Step 1: Write the release checklist as executable verification commands**

The checklist must require, in order: clean Git status; Python 3.12; Node LTS
20/22/24 for Firebase tooling; all tests; secret scan; Firestore rules deploy
validation; staging manifest label validation; staging deployment; `/healthz`;
allowlisted sign-in; denied non-allowlisted sign-in; CSRF rejection; consent
decline; consent-approved proposal; Connect retry with same key; private-data
leak checks; poller SSRF rejection; redacted-log inspection; and documented
rollback to the previous revision.

- [ ] **Step 2: Run the full local verification suite**

Run:

```bash
python -m pytest -v
```

Expected: all created tests pass before a staging deployment is attempted.

- [ ] **Step 3: Perform staging deployment only after the user supplies the existing Firebase/GCP project ID**

Use the staging manifest and the Firebase CLI through
`npx -y firebase-tools@latest`; do not create a project. Verify deployment
service-account permissions, Secret Manager bindings, private bucket uniform
access, and Firestore deny-by-default rules before traffic is sent.

- [ ] **Step 4: Record evidence and commit documentation only**

Run:

```bash
git add docs/release
git commit -m "docs: add pilot staging release checklist"
```

Expected: the documentation records evidence without committing credentials,
source data, reflections, or generated logs.

## Plan Self-Review

### Spec coverage

- Private pilot scope, one allowlisted Google account, source-specific consent,
  daily proposal cap, decisions, candidate concepts, and transfer prompts:
  Tasks 2, 3, 6, 8, and 9.
- Immutable provenance, Cloud Storage, Firestore state, and reconstructable
  SQLite/graph projection: Tasks 4, 5, and 7.
- Usability and save-failure recovery: Tasks 8 and 9.
- Security: validated settings, SSO allowlist, CSRF, idempotency, Firestore
  owner rules, SSRF, injection containment, secret handling, privacy
  isolation, and least privilege: Tasks 3 through 10.
- Stability: explicit outcomes, bounded retries, health/readiness, staging,
  rollback, and durable-data preservation: Tasks 5 through 11.
- Required Cloud Run label and staging-first promotion: Tasks 10 and 11.
- Deferred public plane and stateful copilot: global constraints plus Tasks 6
  and 9.

### Placeholder scan

Every task names files, public interfaces, failing tests, commands, expected
outcomes, and a commit; the plan contains no unresolved implementation markers
or generic error-handling directives.

### Type consistency

`Identity`, `ConnectionProposal`, `DecisionCommand`, `OperationResult`,
`InteractionStore`, `SourceArchive`, `SourceRevision`, `DurableSnapshot`, and
`JobOutcome` are introduced before their consuming tasks. The executor must
keep their imports and field names exactly as stated or update the producing
and consuming tests in the same task.

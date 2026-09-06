# abtahi.fyi MLP Reconciliation Design

## Authority and objective

This specification reconciles the current application with
`/Users/abdullahabtahi/Ideathon/PROJECT_PLAN.md`. It supersedes the
private-only scope restriction in the prior pilot specification, while retaining
its privacy, learner-agency, security, and evidence requirements where they do
not conflict with the parent plan.

The minimum lovable product is a dual-plane application:

1. A public, read-only FYI knowledge plane for agent-native context
   syndication.
2. A private compiled-study plane for one verified, allowlisted learner.

The local release must be secure, useful, and fully tested. It prepares Cloud
Run and Firebase assets but does not deploy until the user supplies an existing
GCP/Firebase project ID and accepts the staging release gate.

## Public FYI plane

Public routes may provide Timeline, public item/permalink pages, search,
focused graph exploration, themes/tensions, JSON Feed, `llms.txt`, and public
OpenAPI metadata. They are read-only and contain only intentionally public,
Git-backed material.

Public responses, feeds, OpenAPI, logs, telemetry, graph/search indexes, and
errors must never reveal private source revisions, course artifacts, model
consent, learner decisions, reflections, sessions, or secrets. All displayed
untrusted text is rendered through escaped templates; no route interpolates
untrusted values into HTML.

## Private compiled-study plane

`/today`, `/study`, `/concepts/{slug}`, `/sources`, and every learner mutation
are private. Production runtime has no anonymous identity fallback.

The browser obtains a Firebase Google ID token. The server verifies it, requires
`email_verified`, compares it against a Secret-Manager-backed allowlisted
email, and only then issues a Firebase session cookie. Every private path is
derived from the verified server-side UID. Cookies are `Secure`, `HttpOnly`,
and `SameSite=Lax`.

Missing Firebase configuration or credentials must fail closed: private pages
redirect to sign-in or return an explicit unavailable error, and mutations do
not claim success. Tests may override dependencies with deterministic fakes.

Every private mutation needs a session-bound CSRF token and client-generated
idempotency key. Reuse with a changed request digest fails. Ambiguous requests
resolve through operation status before another mutation. Failed writes retain
the client selection/reflection and present a retryable failure.

Normal `/today` review contains zero to three evidence-backed proposals. Each
shows source attribution, revision/location, exact excerpt, target concept,
relationship, direct/adjacent match, rationale, uncertainty, and learning
payoff. Connect, Defer, Dismiss, and Edit are keyboard-accessible and must use
matching implemented endpoints. Only successful learner Connect activates an
edge. Candidate concepts require distinct approval and do not consume a review
slot. Transfer prompts are optional and ungraded.

## Data and AI boundaries

Git contains code, tests, non-secret configuration, and intentionally public
content/seed metadata only. Cloud Storage stores immutable private source and
course revisions with uniform bucket-level access. Firestore stores user-scoped
consent, review, reflection, idempotency, job, and audit records. SQLite is a
rebuildable local read projection, never the sole durable record.

Private raw content or excerpts reach Gemini only after durable,
source-revision-specific consent naming source, data category, purpose, and
provider. The stateless batch proposer has no direct storage, graph, or
publication authority. Its structured output requires Pydantic validation plus
deterministic citation, target, and relationship checks.

The stateful `/capture` copilot is not exposed until it has authenticated,
consent-gated, auditable persistence. Until then, omit it from navigation and
routing rather than return an incomplete experience.

Feed ingestion is limited to registered canonical sources. It validates every
request and redirect target, performs DNS re-resolution, blocks private,
loopback, link-local, multicast, unspecified, CGNAT, and metadata IPv4/IPv6
addresses, limits redirects/concurrency/timeouts/body size, and returns an
explicit completed, skipped, or failed outcome. An ingestion failure never
returns a success-shaped response.

## Reliability and deployment

No broad catch may convert initialization, authentication, storage, ingestion,
or mutation failures into success. `/healthz` is non-sensitive and reports
healthy only after required local projection initialization/validation succeeds.

The repository includes a Python-only Dockerfile, Cloud Run staging/production
configuration with `dev-tutorial=cloud-run-ai-challenge`, Firebase deny-by-
default owner-bound rules, least-privilege runtime/deploy identity guidance, and
a staging acceptance checklist. Rollback moves Cloud Run traffic to a healthy
revision and never deletes durable Firestore or Cloud Storage data.

## Reconciliation sequence and acceptance checks

1. Establish one application composition root and make every current test
   deterministic; repair or replace tests that assert obsolete placeholder
   behavior.
2. Repair settings, production Firebase verification, allowlist, session,
   sign-out, and CSRF/idempotency contracts; remove anonymous runtime access.
3. Make public rendering safe and public/private data separation explicit; keep
   only complete public routes.
4. Implement private durable ports/adapters and the proposal/decision lifecycle
   before exposing action controls.
5. Replace incomplete polling/model paths with consent-gated, SSRF-safe,
   explicit-outcome services.
6. Add readiness, deployment, rules, and release assets.

Before staging: all tests pass; public/private route tests prove isolation;
unauthorized and malformed requests fail safely; no secret/private content is
logged or returned; Cloud Run assets and Firebase rules are reviewed; the
required service label is present.

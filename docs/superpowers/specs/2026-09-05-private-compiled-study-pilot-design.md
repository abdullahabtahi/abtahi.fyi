# Private Compiled Study Pilot Design

## Status, authority, and objective

This is the approved design for the first implementation slice of
`abtahi.fyi`: a two-week private WorldQuant University / BlueDot Impact
compiled-study pilot.

It implements the private-plane intent of the parent
`/Users/abdullahabtahi/Ideathon/PROJECT_PLAN.md`, and is consistent with the
parent `PRODUCT.md`, `DESIGN.md`, `UX_DESIGN_SYSTEM.md`, and
`system_instruction.md`. Where the parent documents describe broader or
conflicting behavior, this pilot design is authoritative for the first
delivery.

All version-controlled project artifacts, including this specification, live
inside `/Users/abdullahabtahi/Ideathon/abtahi-fyi`. Parent-level documents are
planning references only and are deliberately outside the application
repository.

**Pilot question:** Can a calm review of no more than three evidence-backed
connections help the allowlisted learner explain *hidden dependencies and
cascading failure* with a real example and state a limit of that model?

## Fixed scope

| Area | Requirement |
| --- | --- |
| Learner | One explicitly allowlisted Google account. |
| Course domain | WorldQuant University, Foundations of Disruption, Module 1. |
| Active concept | Hidden dependencies and cascading failure. |
| Source portfolio | BlueDot Impact only. |
| Canonical feed | `https://blog.bluedot.org/feed`. |
| Feed duplicate rule | Do not separately register `?format=atom`; it currently serves the same RSS channel. |
| Review volume | Zero to three source-to-concept proposals per normal `/today` review. |
| Pilot duration | Two weeks. |
| Deployment sequence | Cloud Run staging first; production only after the release gate passes. |
| Cloud Run service label | `dev-tutorial=cloud-run-ai-challenge` on staging and production services. |

This pilot does not implement public context syndication, public graph routes,
public agent endpoints, course-provider integrations, multiple feeds, email or
browser clipping, autonomous concept creation, autonomous graph mutation,
autonomous synthesis publication, full-graph-first navigation, gamification,
mandatory assessments, or the stateful `/capture` Interactions API copilot.

## Architecture and durable data boundaries

FastAPI, Jinja2, HTMX, Alpine.js, SQLite with WAL/FTS5/sqlite-vec, NetworkX,
Firebase Auth, Cloud Firestore, Cloud Storage, Secret Manager, and Cloud Run
remain the selected project-plan stack. Production has no Node.js runtime.
Node LTS 20, 22, or 24 is required only for Firebase tooling and CI because
the Firebase CLI currently declares that support range.

Cloud Run is stateless. Its filesystem and the local SQLite database are
disposable and must never be the sole copy of source data, learner state, or
evidence.

| Store | Holds | Durability and access rule |
| --- | --- | --- |
| Git repository | Application code, tests, non-secret configuration, and non-sensitive seed study-map metadata | Versioned in the `abtahi-fyi` project root. Never store credentials, source copies, excerpts, consent history, or learner reflections. |
| Private Cloud Storage bucket | Immutable raw source revisions, course artifacts, and normalized source representations | Uniform bucket-level access; no public access; accessed only by the least-privileged runtime service account. Object paths include immutable source and content-hash identifiers. |
| Firestore | User-scoped review decisions, deferrals, reflections, per-source model-consent records, idempotency records, job/audit status, and projection checkpoints | Deny by default. Direct client access is constrained by owner-bound rules; server paths are derived only from the verified session UID. |
| SQLite local projection | Rebuildable FTS/vector indexes, graph projection, and read-optimized metadata derived from durable stores | WAL mode and a single-writer discipline. Rebuilt at Cloud Run startup and controlled refresh; discardable at any time. |

The private source archive preserves revisions. A changed upstream source
creates a new immutable revision and cannot overwrite the evidence used by an
earlier proposal or active edge.

### AI processing boundary

This pilot uses only the stateless batch engine
(`models.generate_content`) after the learner records source-specific consent.
It receives a bounded, validated request and returns structured proposal data;
it has no direct database, storage, graph, publication, or privileged-action
capability. Recoverable provider failures follow the bounded background retry
policy, while non-recoverable validation and authorization failures are
surfaced without retry.

The project-plan stateful Interactions API copilot on `/capture` is deferred.
It is not provisioned, routed, or needed for the pilot's source ingestion,
proposal review, synthesis-draft, or learning-transfer flows.

## Identity, authorization, and session behavior

The pilot uses Firebase Google Sign-In. It does not implement custom
email/password authentication or retain passwords.

1. The browser obtains a Firebase Google ID token.
2. `POST /api/auth/session` validates the ID token server-side and exchanges it
   for a server-validated session cookie.
3. The server admits a private request only when the Firebase token declares
   `email_verified: true` and its verified email equals the configured
   single-account allowlist value. The allowlist value is a Secret
   Manager-backed runtime configuration value, never client-supplied data.
4. The application derives every Firestore user path from the verified UID. It
   never accepts a user ID from route, form, cookie, or request-body input.
5. Private mutation routes require a valid CSRF token and a client-generated
   idempotency key.

Unauthenticated visitors are redirected to sign-in. Authenticated but
non-allowlisted visitors receive a generic access-denied response that
discloses no source, concept, review, or allowlist information. Cookies use
`Secure`, `HttpOnly`, and `SameSite=Lax`. Session renewal, expiry, and sign-out
must leave private pages inaccessible from a new request.

Firestore security rules are a defense in depth, not the primary server-side
authorization mechanism. They begin deny-by-default and permit only an owner
to access their own permitted document paths.

## Learning and proposal lifecycle

The course-faithful causal spine is:

`system architecture -> hidden dependencies / coupling -> cascade risk ->
stakeholder impacts -> accountability and intervention`.

Connections distinguish a triggering event from enabling conditions where that
distinction affects the explanation. They must not reduce systemic failure to
a single proximate cause or assign systemic accountability solely to a final
actor.

### Ingestion and consent

1. The protected scheduler/admin path polls only the registered BlueDot
   canonical feed.
2. The poller validates its target before connection, every redirect target,
   and resolved IPv4 and IPv6 addresses. It rejects loopback, unspecified,
   multicast, link-local, carrier-grade NAT, RFC 1918/private, and cloud
   metadata address ranges.
3. The poller enforces an allowlisted scheme, DNS revalidation after redirects,
   a five-connection concurrency limit, a connect timeout, a read timeout,
   three redirects maximum, and a five-megabyte response ceiling.
4. Feed entries are canonicalized and deduplicated by canonical URL plus
   normalized content hash. ETag and Last-Modified values support conditional
   requests.
5. A new or changed entry is retained as a private immutable revision and is
   indexed in the rebuildable local projection.
6. Before any raw private copy or excerpt is sent to an external model, the
   learner receives a source-specific consent request that states the source,
   data category, processing purpose, and external provider. Consent is
   durable and scoped to that source revision and processing request.
7. Declining consent retains the source without generating an externally
   model-derived proposal. The UI says that no proposal was generated; it does
   not imply successful analysis.

All feed and course content is untrusted data. Prompt construction fences it
as untrusted content. Model output is constrained to validated structured
records and is encoded before any HTML or JavaScript rendering.

### Proposal quality and review

After consent, retrieval may consider only a bounded set of relevant concepts.
The agent has proposal authority only; it cannot mutate durable learning state.
Every proposal contains the immutable source revision ID, source title/author/
date/canonical link, exact excerpt, excerpt location, target concept,
relationship type, direct-or-adjacent match classification, rationale,
plain-language uncertainty, proposed cited-evidence addition, and a stable
proposal ID.

The relationship taxonomy is `supports`, `challenges`, `example_of`,
`application_of`, `prerequisite_for`, `develops_into`, `superseded_by`, and
`related_to`. For this pilot, proposals normally use `supports`, `challenges`,
`example_of`, `application_of`, or `related_to`.

A proposal is suppressed before learner visibility unless it:

1. targets the active concept or is explicitly an adjacent case;
2. accurately quotes a sufficient immutable source passage;
3. names one relationship type and explains why stronger or weaker types do
   not apply;
4. states uncertainty instead of relying on a numeric score alone;
5. offers a concrete learning payoff; and
6. avoids claiming that one source proves the entire course model.

Direct matches identify a materially equivalent dependency, propagation path,
cascade, or failure mechanism. Adjacent cases state what is analogous, what
differs, and why the difference matters. Adjacent cases are never presented as
direct evidence.

`/today` shows at most three pending proposals and never displays an overdue
count, streak, score, unread pressure, or catch-up mechanism. Each proposal
has visible, labelled, keyboard-accessible controls:

| Decision | Durable effect |
| --- | --- |
| Connect | Activates exactly one cited private graph edge and makes the cited evidence visible on the private concept page. |
| Defer | Schedules the proposal for tomorrow, next week, or later without calling it overdue. |
| Dismiss | Retains an immutable audit outcome but excludes the proposal from the active graph and concept evidence. |
| Edit | Lets the learner correct the proposed relationship, rationale, or evidence presentation before the final explicit Connect, Defer, or Dismiss decision. |

Only Connect activates an edge. It does not silently rewrite the explanation:
the agent may create a separate synthesis draft that the learner can later
accept, edit, or leave unchanged.

If a source reveals a relevant missing idea, it becomes a separately reviewed
Candidate concept. It includes name, course grounding, definition, rationale,
and proposed links. It never consumes a normal daily slot and never creates a
concept node without approval.

## Usability and recoverable failure behavior

The private user experience satisfies WCAG 2.1 AA, including 44 by 44 pixel
minimum pointer targets, visible keyboard focus, non-color-only semantic
meaning, reduced-motion support, and an equivalent structured relationship
list for the focused one-to-two-hop graph.

Every mutation sends a CSRF token and client-generated idempotency key. The
server persists the key with the operation outcome and returns the original
outcome for a legitimate retry. Repeating a Connect cannot create duplicate
edges, citations, decisions, or audit records.

If a decision or reflection cannot be durably saved:

- preserve the browser input and selected action;
- state clearly that the action was **not saved**;
- present an accessible Retry control;
- retry with the original idempotency key; and
- never return a success-shaped response or erase input.

If the browser times out after a mutation request, it queries the operation
status with the same idempotency key before asking for another decision. This
resolves an ambiguous response without duplicate writes.

Dependency errors have explicit categories: validation/authorization failure,
unavailable dependency, retryable transient failure, or internal failure.
User-facing errors are safe and actionable; detailed diagnostics are in
redacted structured logs. No broad catch-all may turn a failed write,
projection rebuild, model request, or feed fetch into a false success.

Feed, Firestore, Storage, or model-provider unavailability never blocks
already-durable study. Background tasks retry only idempotent work with
bounded exponential backoff and record `completed`, `skipped`, or `failed`
status. They do not retry non-idempotent learner mutations automatically.
The learner sees the last consistent projection; a source-specific processing
failure never implies that the source was understood or proposed.

## Security and privacy requirements

The design applies the five threat zones from `system_instruction.md`:

| Threat zone | Required countermeasures |
| --- | --- |
| Input surfaces | Strict Pydantic validation; parameterized database operations; HTML sanitization; response size/type bounds; output encoding. |
| Planning and reasoning | Treat retrieved material as data; untrusted-content fencing; structured model output; deterministic target, citation, relationship, and graph validation; model has no mutation capability. |
| Tool execution | URL scheme and DNS/IP SSRF controls on initial and redirect requests; no dynamic code execution; least-privileged job identity. |
| Memory and state | Server-verified Google SSO, one-account allowlist, CSRF, secure cookies, idempotency, verified-UID-only data paths, Firestore owner rules, and no private records in public interfaces. |
| Inter-system communication | Separate deployment/runtime service accounts, Secret Manager references only, TLS, redacted logs, no credentials in source/client errors, and per-source consent before external model processing. |

No private raw source, excerpt, highlight, reflection, audit record, consent
record, graph provenance, or user interaction may appear in a public page,
feed, agent endpoint, cache header, error response, log, telemetry payload, or
model prompt without the required source-specific consent. The eventual public
FYI plane has a separate publication lifecycle; private approval is never
public publication.

## Deployment, operations, and rollback

Staging is an isolated Cloud Run deployment using a separately named service
and least-privilege identities. Both staging and production Cloud Run services
carry the mandatory `dev-tutorial=cloud-run-ai-challenge` label. Deployment
configuration supplies an existing Firebase/GCP project ID later; this design
does not create or bind remote resources.

Runtime configuration validates required values at startup without printing
their contents. Secrets are accessed through Secret Manager or platform secret
references, never committed, placed in checked-in environment files, or
returned by a diagnostic endpoint. The storage bucket has uniform access and
no public object paths.

The service has a non-sensitive health endpoint that confirms readiness
without querying or exposing private content. A revision must reconstruct or
verify its SQLite projection before it receives private traffic. Failed
reconstruction fails readiness rather than serving a partial projection as
healthy.

Production promotion requires successful staging evidence for:

1. configuration validation and secret-reference checks;
2. local-index/graph projection reconstruction;
3. Google SSO, allowlist, session-expiry, and sign-out smoke tests;
4. proposal lifecycle, idempotency, and failed-save retry tests;
5. authorization, owner isolation, CSRF, cookie, and privacy-boundary tests;
6. malformed, oversize, duplicate, changed-revision, redirect, and SSRF feed
   tests;
7. prompt-injection fencing, structured-output rejection, and consent tests;
8. health/readiness checks and redacted error-log checks; and
9. the required `dev-tutorial=cloud-run-ai-challenge` label on the candidate
   Cloud Run service; and
10. secret scanning and dependency/security checks already adopted by the
    project.

Rollback returns traffic to the last healthy Cloud Run revision. It never
rolls back or deletes the Cloud Storage source archive or Firestore learning
records. A production dependency incident must preserve durable data and
produce a recoverable user state, not erase work or claim completion.

## Transfer checks and pilot outcome

After an approved connection, the learner may receive an optional next-day
prompt:

> In your own words, what dependency or propagation path does this example make
> clearer?

About one week later, the learner may receive an optional unfamiliar-case
prompt:

> Identify a hidden dependency, explain how failure could propagate, and name
> one limit or missing condition in your explanation.

Responses stay private, are never graded, and may be skipped without penalty.

At the end of two weeks, the pilot evaluation records whether the learner can
explain the active concept with a real example, identify a plausible cascade
rather than merely name an event, state a limit or uncertainty, and find the
review volume calm and worthwhile. It also reports direct/adjacent proposal
outcomes and whether adjacent cases clarified or confused the model. These
results decide whether to refine the concept, labels, proposal selectivity, or
source scope before adding another feed.

## Implementation acceptance tests

The eventual implementation plan must provide executable tests covering:

- authentication redirects, allowlist denial, server-side UID ownership, session
  expiry, sign-out, CSRF rejection, secure cookie configuration, and no private
  content in denied responses;
- canonical feed registration, conditional polling, duplicate suppression,
  changed-source revision creation, immutable evidence resolution, malformed
  feed handling, payload limits, redirect limits, and IPv4/IPv6 SSRF rejection;
- required source-specific consent, declined-consent behavior, prompt-injection
  fencing, invalid model-output rejection, and no agent-initiated mutation;
- proposal quality suppression, direct/adjacent presentation, three-proposal
  cap, candidate-concept separation, and every review-state transition;
- idempotent Connect/Defer/Dismiss/Edit actions, ambiguous response recovery,
  failed-save input retention, and no duplicate edge/citation/audit record;
- cited concept-page updates, source-to-edge provenance, no unapproved active
  graph edges, focused graph/list equivalence, and projection rebuild from
  durable stores;
- public/private isolation checks across pages, APIs, errors, cache behavior,
  telemetry fixtures, and logs;
- health/readiness, unavailable dependency behavior, bounded background retry,
  redacted diagnostics, staging smoke tests, and Cloud Run rollback evidence.

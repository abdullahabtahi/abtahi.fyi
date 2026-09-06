# abtahi.fyi

Private compiled-study pilot application built with Python 3.12 and FastAPI.

## Local setup

1. Create a local virtual environment: `python3 -m venv .venv`
2. Install dependencies: `.venv/bin/python -m pip install -e .[test]`
3. Run the test suite: `.venv/bin/python -m pytest -v`

## Constraints

- Production runtime is Python-only and carries no Node.js dependency.
- Firebase CLI or CI tooling, when introduced later, must use Node LTS 20, 22, or 24 only.
- Remote Firebase and Google Cloud resources are configured in later tasks, not in this baseline.
- Private sessions are Firebase-verified, allowlist-bound, and use Secure,
  HttpOnly, SameSite=Lax session and CSRF companion cookies.
- Private proposal mutations require `X-CSRF-Token` and `Idempotency-Key`.
  Connect and Edit require `reviewed_content`; Defer requires `defer_window`;
  a dismissal can be undone only with its dismissal operation ID.
- Learner-approved connections are stored and projected in the authenticated
  learner's private Firestore collections. They are never added to the public
  content loader, search index, feeds, or NetworkX cache.
- Source collection is available only to the configured privileged job identity.
  `APPROVED_FEED_URLS` is the registered-feed allowlist, and every source is
  archived privately before downstream processing. External proposal processing
  requires an exact learner/revision/purpose/provider consent grant.

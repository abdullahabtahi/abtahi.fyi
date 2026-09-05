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

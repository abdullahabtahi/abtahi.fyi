# AGENTS.md — Agent Architectural Guidelines for `abtahi.fyi`

## Architectural Overview

`abtahi.fyi` is a full-stack, dual-plane web application and knowledge graph running on Python 3.12, FastAPI, SQLite (`sqlite-vec` + FTS5), and Google Cloud Run.

### Core Principles
1. **Zero-Node Production Runtime**: Pure Python 3.12 runtime. Zero npm/node in production containers.
2. **Absolute Privacy Firewall**: The public plane strictly queries `content/public/` and `node.plane == 'public'`. Zero exposure of `content/private/`, Firestore study records, or internal review states.
3. **Inspectable Provenance Chain**: Every link requires analytical commentary (never naked URLs); permalinks display full incoming/outgoing relationship groups with reasons.
4. **Agent-Native Syndication**: First-class discovery and syndication via `/llms.txt`, `/feed.json` (JSON Feed 1.1 + `_fyi`), `/feed.xml` (Atom 1.0), and dual-routing REST endpoints (`/api/fyi/q/...`).
5. **Fail-Closed Reliability**: If vector embeddings are unavailable, search degrades gracefully to SQLite FTS5 BM25 with `fallback: true`.

---

## Active Public Endpoints

### Human Interface (Calm Single-Column 640px)
- `GET /`: Chronological reading stream grouped by day `<time>` headers with relationship badges.
- `GET /i/{id}`: Article permalink displaying incoming/outgoing relationship groups and temporal invalidation warning banners.
- `GET /tensions`: Active intellectual conflict cards (`challenges` pairs) with quotes and analytical rationale.
- `GET /connected`: PageRank authority hubs / gravity centers.
- `GET /themes`: Emergent thematic clusters discovered through Louvain modularity.
- `GET /search`: Search UI with keyword and semantic retrieval.
- `GET /about`: Authorial identity and system philosophy.

### Agent Discovery & Syndication
- `GET /llms.txt`: Curated markdown context for LLMs with identity preamble, item types, and API guide.
- `GET /feed.json`: JSON Feed 1.1 with typed `_fyi` extensions.
- `GET /feed.xml`: Full Atom 1.0 XML feed.
- `GET /openapi.json`: OpenAPI 3.1 schema filtered strictly to public routes.

### REST Query API (`/api/fyi/q/...`)
- `GET /api/fyi/q/search/{term}` & `GET /api/fyi/q/search?q={term}`: SQLite FTS5 BM25 search.
- `GET /api/fyi/q/semantic/{query}` & `GET /api/fyi/q/semantic?q={query}`: Vector similarity with automatic FTS5 failover.
- `GET /api/fyi/q/edges/{id}` & `GET /api/fyi/q/edges?itemId={id}`: Knowledge connection network.
- `GET /api/fyi/q/items`: All public items with `since` and `type` filters.
- `GET /api/fyi/q/items/{id}`: Full item detail object.
- `GET /api/fyi/q/summary`: Pre-computed graph intelligence snapshot (<15ms p95, <1ms from cache).

---

## AI & Cloud Configuration
- **GCP Project**: `spatial-cat-489006-a4`
- **Region**: `us-central1`
- **Primary AI Model**: `gemini-3.8-flash`
- **Vertex AI Client**: Factory in `app/ai/client.py` uses Application Default Credentials (ADC) natively on GCP.

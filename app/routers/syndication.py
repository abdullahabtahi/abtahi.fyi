from fastapi import APIRouter, Request, Depends, Response, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.schemas.feeds import JSONFeed, JSONFeedItem, FyiExtensions
from app.core.public_loader import PublicContentLoader
from app.core.network import network_cache
import os
import glob
import frontmatter
from datetime import datetime, timezone

router = APIRouter(tags=["Syndication"])

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

loader = PublicContentLoader()


def load_curriculum_milestones() -> list[dict]:
    milestones = []
    try:
        import json
        from app.core.db import init_sqlite_db
        conn = init_sqlite_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT module_id, title, summary, concepts_count, concept_slugs_json, created_at FROM curriculum_milestones ORDER BY created_at DESC"
        )
        for mod_id, title, summary, count, slugs_json, created_at_str in cursor.fetchall():
            try:
                slugs = json.loads(slugs_json)
            except Exception:
                slugs = []
            try:
                pub_dt = datetime.fromisoformat(created_at_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pub_dt = datetime.now(timezone.utc)

            concept_chips = []
            for slug in slugs:
                cursor.execute("SELECT title FROM curriculum_concepts WHERE slug = ?", (slug,))
                row = cursor.fetchone()
                chip_title = row[0] if row else slug.replace("-", " ").title()
                concept_chips.append({"slug": slug, "title": chip_title})

            milestones.append({
                "id": f"module-{mod_id}",
                "item_type": "curriculum",
                "module_id": mod_id,
                "title": f"Module {mod_id}: {title}",
                "summary": summary,
                "concepts_count": count,
                "concepts": concept_chips,
                "published_at": pub_dt,
                "domain": None,
                "canonical_url": f"/study#{mod_id}",
                "edges": [],
            })
        conn.close()
    except Exception:
        pass
    return milestones


def load_connected_signals() -> list[dict]:
    signals = []
    try:
        from app.core.db import init_sqlite_db
        conn = init_sqlite_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, proposal_id, source_url, source_title, source_domain,
                   concept_slug, concept_title, edge_type, excerpt,
                   reviewed_citation, rationale, connected_at
            FROM connected_signals
            ORDER BY connected_at DESC
            """
        )
        from app.core.firestore import resolve_article_url
        for row in cursor.fetchall():
            try:
                pub_dt = datetime.fromisoformat(row[11])
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pub_dt = datetime.now(timezone.utc)

            sig_id = row[0]
            article_url = resolve_article_url(
                source_domain=row[4] or "",
                source_title=row[3] or "",
                explicit_url=row[2],
            )
            signals.append({
                "id": f"signal-{sig_id}",
                "item_type": "signal",
                "proposal_id": row[1],
                "title": row[3],
                "canonical_url": article_url,
                "source_url": article_url,
                "domain": row[4],
                "concept_slug": row[5],
                "concept_title": row[6],
                "edge_type": row[7],
                "excerpt": row[8],
                "reviewed_citation": row[9],
                "rationale": row[10],
                "published_at": pub_dt,
                "edges": [
                    {
                        "source_id": f"signal-{sig_id}",
                        "target_id": row[5],
                        "edge_type": row[7],
                    }
                ],
            })
        conn.close()
    except Exception:
        pass
    return signals


@router.get("/", response_class=HTMLResponse)
async def get_timeline(request: Request):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    milestones = load_curriculum_milestones()
    signals = load_connected_signals()

    combined = list(items) + list(milestones) + list(signals)
    combined.sort(
        key=lambda x: x.published_at if hasattr(x, "published_at") else x.get("published_at"),
        reverse=True,
    )

    # Group items by day for calm reading stream
    days_dict: dict[str, list] = {}
    for entry in combined:
        pub_at = entry.published_at if hasattr(entry, "published_at") else entry.get("published_at")
        date_key = pub_at.strftime("%Y-%m-%d")
        days_dict.setdefault(date_key, []).append(entry)

    days = []
    for date_key, day_items in days_dict.items():
        first_entry = day_items[0]
        pub_at = first_entry.published_at if hasattr(first_entry, "published_at") else first_entry.get("published_at")
        days.append({
            "date_iso": date_key,
            "date_formatted": pub_at.strftime("%B %d, %Y"),
            "entries": day_items,
        })

    return templates.TemplateResponse(
        request=request, name="timeline.html", context={"days": days, "items": combined}
    )

@router.get("/i/{id}", response_class=HTMLResponse, name="get_permalink")
async def get_permalink(request: Request, id: str):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    item = next((i for i in items if i.id == id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    relationships = network_cache.get_item_edges(item.id)
    return templates.TemplateResponse(
        request=request, name="permalink.html", context={"item": item, "relationships": relationships}
    )

@router.get("/llms.txt", response_class=PlainTextResponse)
async def get_llms_txt():
    content = """# abtahi.fyi — Context Syndication Plane

> A calm, agent-native knowledge graph by Abdullah Abtahi covering autonomous systems, complex networks, hardware architectures, and AI cognition.

## Author Context
Abdullah Abtahi is an engineer and researcher building autonomous reasoning systems, hardware-aware execution pipelines, and public knowledge synthesis graphs.

## Item Types
- **riff**: Original thinking, reaction, distinction, or concise architectural argument (no external URL).
- **link**: Curated external paper or source paired with analytical commentary on why it matters (never a naked URL).
- **essay**: Deep dive conceptual synthesis.

## Agent Feeds & Schemas
- JSON Feed 1.1: `https://abtahi.fyi/feed.json`
- Atom 1.0 XML: `https://abtahi.fyi/feed.xml`
- OpenAPI 3.1 Spec: `https://abtahi.fyi/openapi.json`

## REST Query API (`/api/fyi/q/...`)
- Keyword Search: `GET /api/fyi/q/search/{term}` or `GET /api/fyi/q/search?q={term}`
- Semantic Search: `GET /api/fyi/q/semantic/{query}` or `GET /api/fyi/q/semantic?q={query}`
- Knowledge Connections: `GET /api/fyi/q/edges/{itemId}` or `GET /api/fyi/q/edges?itemId={itemId}`
- All Items: `GET /api/fyi/q/items?since={ISO}&type={type}&limit={n}&offset={n}`
- Item Detail: `GET /api/fyi/q/items/{itemId}`
- Graph Intelligence Summary: `GET /api/fyi/q/summary`
"""
    return PlainTextResponse(content=content, media_type="text/markdown")

@router.get("/feed.xml")
async def get_feed_xml(request: Request):
    items = loader.load_all_items()
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    
    entries_xml = []
    for item in items:
        tags_xml = "".join([f'<category term="{tag}"/>' for tag in item.tags])
        canonical = f'<link rel="related" href="{item.canonical_url}"/>' if item.canonical_url else ''
        summary_xml = f'<summary><![CDATA[{item.summary}]]></summary>' if item.summary else ''
        entries_xml.append(
            f"""  <entry>
    <title>{item.title}</title>
    <link href="https://abtahi.fyi/i/{item.id}"/>
    {canonical}
    <id>https://abtahi.fyi/i/{item.id}</id>
    <updated>{item.published_at.isoformat()}</updated>
    {summary_xml}
    <content type="html"><![CDATA[{item.content_html}]]></content>
    {tags_xml}
  </entry>"""
        )

    xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>abtahi.fyi Context Syndication</title>
  <subtitle>Original notes, curated links, and emergent network synthesis by Abdullah Abtahi</subtitle>
  <link href="https://abtahi.fyi/feed.xml" rel="self"/>
  <link href="https://abtahi.fyi/"/>
  <updated>{now_iso}</updated>
  <id>https://abtahi.fyi/</id>
  <author>
    <name>Abdullah Abtahi</name>
    <uri>https://abtahi.fyi/</uri>
  </author>
{chr(10).join(entries_xml)}
</feed>"""
    return Response(content=xml_content, media_type="application/atom+xml")

@router.get("/feed.json", response_model=JSONFeed, response_model_by_alias=True)
async def get_feed_json(request: Request):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    feed_items = []
    
    pr_scores = network_cache.get_pagerank()
    bw_scores = network_cache.get_betweenness()
    communities = network_cache.get_communities()
    
    for item in items:
        # Determine group based on community cache
        group = None
        for i, comm in enumerate(communities):
            if item.id in comm:
                group = i + 1
                break
                
        feed_items.append(
            JSONFeedItem(
                id=item.id,
                url=str(request.url_for("get_permalink", id=item.id)) if "get_permalink" in [getattr(r, "name", None) for r in request.app.routes] else f"https://abtahi.fyi/i/{item.id}",
                title=item.title,
                summary=item.summary,
                content_html=item.content_html,
                date_published=item.published_at.isoformat() + "Z" if item.published_at.tzinfo is None else item.published_at.isoformat(),
                _fyi=FyiExtensions(
                    item_type=item.item_type.value,
                    canonical_url=item.canonical_url,
                    tags=list(item.tags),
                    pagerank_score=pr_scores.get(item.id),
                    betweenness_score=bw_scores.get(item.id),
                    community_id=group,
                    edges_count=len(item.edges),
                )
            )
        )
        
    feed = JSONFeed(
        title="abtahi.fyi Context Syndication",
        home_page_url="https://abtahi.fyi/",
        feed_url="https://abtahi.fyi/feed.json",
        items=feed_items
    )
    
    # We can just return the model and FastAPI will use the alias because response_model_by_alias=True
    return Response(content=feed.model_dump_json(by_alias=True), media_type="application/feed+json")

@router.get("/graph", response_class=HTMLResponse)
async def get_graph(request: Request):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    item_dict = {item.id: item for item in items}

    nodes = []
    links = []
    communities = network_cache.get_communities()

    # Edge color mapping matching mattwood.fyi visual hierarchy
    EDGE_COLORS = {
        "example_of": "#38bdf8",        # Sky Blue
        "application_of": "#a78bfa",    # Lavender
        "supports": "#f06595",          # Rose / Pink
        "challenges": "#ffd43b",        # Yellow / Amber
        "develops_into": "#69db7c",     # Light Green
        "prerequisite_for": "#69db7c",  # Light Green
        "superseded_by": "#ff8c42",     # Amber / Orange
        "related_to": "#666666",        # Neutral gray
        "related": "#666666",
    }

    for node in network_cache.G.nodes:
        node_data = network_cache.G.nodes[node]
        if node in item_dict:
            title = item_dict[node].title
            node_type = getattr(item_dict[node].item_type, "value", str(item_dict[node].item_type))
            url = f"/i/{node}"
        elif node_data.get("node_type") == "signal":
            title = node_data.get("title") or "Signal"
            node_type = "signal"
            url = node_data.get("url") or "#"
        else:
            title = node_data.get("title") or node.replace("-", " ").title()
            node_type = node_data.get("node_type", "concept")
            url = f"/concepts/{node}"

        group = 0
        for i, comm in enumerate(communities):
            if node in comm:
                group = i + 1
                break

        degree = network_cache.G.degree(node)
        nodes.append({
            "id": node,
            "title": title,
            "node_type": node_type,
            "url": url,
            "group": group,
            "val": max(5, min(24, 4 + degree * 3)),
        })

    for u, v, data in network_cache.G.edges(data=True):
        edge_type = data.get("edge_type", "related_to")
        links.append({
            "source": u,
            "target": v,
            "type": edge_type,
            "color": EDGE_COLORS.get(edge_type, "#78716c"),
            "reason": data.get("reason", ""),
        })

    return templates.TemplateResponse(
        request=request, name="graph.html", context={"nodes": nodes, "links": links}
    )

@router.get("/connected", response_class=HTMLResponse)
async def get_connected(request: Request):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    pr_scores = network_cache.get_pagerank()
    
    view_items = []
    for item in items:
        score = pr_scores.get(item.id, 0.0)
        view_items.append({
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "metric_value": f"{score:.4f}"
        })
        
    view_items.sort(key=lambda x: float(x["metric_value"]), reverse=True)
    
    return templates.TemplateResponse(
        request=request, name="connected.html", context={
            "items": view_items
        }
    )

@router.get("/tensions", response_class=HTMLResponse)
async def get_tensions(request: Request):
    if len(network_cache.G) == 0:
        items = loader.load_all_items()
        network_cache.load_from_items(items)
    tensions = network_cache.extract_intellectual_tensions()
    triangular_tensions = network_cache.detect_triangular_contradictions()
    
    return templates.TemplateResponse(
        request=request, name="tensions.html", context={
            "tensions": tensions,
            "triangular_tensions": triangular_tensions,
        }
    )

@router.get("/api/tensions")
async def get_api_tensions(triangular: bool = False):
    """
    Returns active intellectual contradictions across the knowledge graph.
    If triangular=true, returns length-3 contradiction triads (A -> B -> C -> A).
    """
    if triangular:
        triads = network_cache.detect_triangular_contradictions()
        return JSONResponse(content=[t.model_dump(mode="json") for t in triads])
    else:
        tensions = network_cache.extract_intellectual_tensions()
        return JSONResponse(content=[t.model_dump(mode="json") for t in tensions])

@router.get("/api/inquiries")
async def get_api_inquiries(status: str = "active"):
    """
    Returns frontier perimeter Socratic inquiries formulated by the synthesis engine.
    Strictly bounded to max 3 active items.
    """
    inquiries_dir = os.path.join(loader.content_dir, "inquiries")
    archive_dir = os.path.join(inquiries_dir, "archive")
    records = []

    search_dirs = []
    if status in ("active", "all"):
        search_dirs.append((inquiries_dir, "active"))
    if status in ("resolved", "archived", "all"):
        search_dirs.append((archive_dir, "resolved"))

    for s_dir, default_st in search_dirs:
        if not os.path.exists(s_dir):
            continue
        for fpath in glob.glob(os.path.join(s_dir, "*.md")):
            if default_st == "active" and "archive" in fpath:
                continue
            try:
                post = frontmatter.load(fpath)
                rec = {
                    "id": post.metadata.get("id", os.path.splitext(os.path.basename(fpath))[0]),
                    "target_concept": post.metadata.get("target_concept", ""),
                    "question": post.content.strip(),
                    "rationale": post.metadata.get("rationale", ""),
                    "status": post.metadata.get("status", default_st),
                    "created_at": post.metadata.get("created_at", datetime.now(timezone.utc).isoformat()),
                    "resolved_at": post.metadata.get("resolved_at"),
                }
                if status == "all" or rec["status"] == status:
                    records.append(rec)
            except Exception as e:
                pass

    if status == "active":
        records = records[:3]

    return JSONResponse(content=records)

@router.get("/themes", response_class=HTMLResponse)
async def get_themes(request: Request):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    communities = network_cache.get_communities()
    item_map = {item.id: item for item in items}
    
    themes_data = []
    for i, comm in enumerate(communities):
        comm_members = []
        for node in comm:
            if node in item_map:
                comm_members.append(item_map[node])
        if comm_members:
            themes_data.append({
                "community_id": i,
                "members": comm_members,
            })
            
    return templates.TemplateResponse(
        request=request, name="themes.html", context={
            "themes": themes_data
        }
    )

import random

@router.get("/random")
async def get_random():
    items = loader.load_all_items()
    if not items:
        raise HTTPException(status_code=404, detail="No items available")
    item = random.choice(items)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/i/{item.id}")

@router.get("/about", response_class=HTMLResponse)
async def get_about(request: Request):
    return templates.TemplateResponse(request=request, name="about.html", context={})

@router.get("/agents", response_class=HTMLResponse)
async def get_agents(request: Request):
    items = loader.load_all_items()
    network_cache.load_from_items(items)

    # Sort items by publication date descending
    sorted_items = sorted(items, key=lambda x: x.published_at, reverse=True)
    recent_items = sorted_items[:10]

    # Pre-render recent items list in markdown
    recent_lines = []
    for item in recent_items:
        date_str = item.published_at.strftime("%Y-%m-%d")
        recent_lines.append(f"- {item.title} ({date_str}): https://abtahi.fyi/i/{item.id}")
    recent_items_md = "\n".join(recent_lines)

    # Gravity centers from PageRank
    pr = network_cache.get_pagerank()
    top_pr = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:5]
    items_dict = {item.id: item.title for item in items}
    gravity_lines = []
    for node, score in top_pr:
        if node in items_dict:
            gravity_lines.append(f"- {items_dict[node]} (centrality: {score:.3f})")
    gravity_centers_md = "\n".join(gravity_lines) if gravity_lines else "- Systems Thinking\n- Autonomous Reasoning"

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d at %H:%M UTC")

    context_str = f"""# Context: Abdullah Abtahi's FYI (abtahi.fyi)

Hey — you're being given context about Abdullah Abtahi and his current thinking. Here's what you need to know and what you can do with it.

## Who is Abdullah Abtahi?

Abdullah Abtahi is an engineer and researcher building autonomous reasoning systems, hardware-aware execution pipelines, and public knowledge synthesis graphs across artificial intelligence, complex networks, cloud architecture, and AI safety.

## What is this site?

abtahi.fyi is his FYI — a live list of riffs and links drawn from what he's reading, noticing, questioning, concluding, and revising. It sits between deep conceptual research and live synthesis notes.

Three types of items:

- **riff**: A self-contained idea, distinction, analogy, reaction, or small argument. These are Abdullah's own thinking — not summaries of other people's work.
- **link**: An external source accompanied by original commentary explaining why it matters, what to notice, or how it changes the picture. Never a naked URL.
- **essay**: A pointer to a newly synthesized deep-dive or long-form publication, carrying the thesis, context, and relationship to recent concepts.

## Gravity Centers (High-Authority Concepts)

{gravity_centers_md}

## How to access this site

Everything here is public and freely accessible — no authentication, no API keys, no rate limits.

- JSON Feed (recommended for agents): https://abtahi.fyi/feed.json
  - Standard JSON Feed 1.1 with a `_fyi` extension object per item
  - Each item has: type (riff|link|essay), tags, and graph metadata
  - This is the best single endpoint for structured access
- Atom Feed: https://abtahi.fyi/feed.xml
  - Full HTML content of every item
- Individual items: https://abtahi.fyi/i/{{id}}
  - Each item has a stable permalink you can reference
- llms.txt: https://abtahi.fyi/llms.txt
- Homepage: https://abtahi.fyi/

The JSON feed at /feed.json is your best single source — it contains typed, structured content newest first.

## Query API (public, no auth required)

For structured queries against the knowledge graph, use these REST endpoints.
All are public, no authentication required. All return JSON.

Note: some agent fetch tools strip query-string parameters that look like IDs.
If query-string endpoints fail, use the path-based alternatives (preferred).

### Search
- GET https://abtahi.fyi/api/fyi/q/search/KEYWORD (preferred, path-based)
- GET https://abtahi.fyi/api/fyi/q/search?q=KEYWORD
  Search items by keyword in title and content. Returns matching items with permalinks.

### Semantic Search
- GET https://abtahi.fyi/api/fyi/q/semantic/NATURAL+LANGUAGE+QUERY (preferred, path-based)
- GET https://abtahi.fyi/api/fyi/q/semantic?q=QUERY
  Search by meaning, not keywords. Uses vector embeddings to find semantically similar items.
  Returns items ranked by similarity score (0-1). Use this for natural language questions.

### Items
- GET https://abtahi.fyi/api/fyi/q/items?since=YYYY-MM-DD&type=link|riff|essay&limit=N&offset=N
  List items filtered by date and/or type. Default limit=50, offset=0.
  Response includes: total (full count matching filters), hasMore (boolean), offset, limit.
  If hasMore is true, increment offset by limit to get the next page.

### Edges (connections)
- GET https://abtahi.fyi/api/fyi/q/edges/SHORT_ID (preferred, path-based)
- GET https://abtahi.fyi/api/fyi/q/edges?itemId=SHORT_ID
  Get all graph connections for a specific item. Returns edge type, direction (incoming/outgoing), confidence, and reason.
  Add ?type=challenges (or supports, develops_into, related_to) to filter.

- GET https://abtahi.fyi/api/fyi/q/edges?type=challenges
  Get ALL edges of a specific type across the whole graph.

### Graph summary (snapshot)
- GET https://abtahi.fyi/api/fyi/q/summary
  Pre-computed snapshot: top connected items, recent activity, edge type distribution, and all tension pairs.
  Includes a generated_at timestamp.

### How to answer common questions
- "What is Abdullah reading about X?" → /api/fyi/q/semantic/X (semantic) or /api/fyi/q/search/X (keyword)
- "What changed this week?" → /api/fyi/q/items?since=YYYY-MM-DD (7 days ago)
- "What challenges idea Y?" → search for Y, get its shortId, then /api/fyi/q/edges/SHORT_ID
- "Where are signals converging?" → /api/fyi/q/summary gives top connected items
- "What are the tensions?" → /api/fyi/q/edges?type=challenges returns all challenge relationships with reasons
- "What connects A to B?" → get edges for both items and look for shared connections
- "What does Abdullah think about topic Z?" → /api/fyi/q/semantic/topic+Z for semantically related items

## Recent items

{recent_items_md}

## What should you do with this?

- Answer questions about what Abdullah is currently thinking about
- Surface relevant items when a user asks about topics he's covered
- Quote and cite — every item has a stable permalink, use it
- Notice patterns across items (recurring themes, evolving positions)
- Go deeper — if a user asks about something adjacent, fetch the relevant item and read it rather than guessing
- Be honest about gaps — if he hasn't written about something, say so rather than extrapolating
- Fetch the JSON feed for the latest; don't rely solely on this static page

## Canonical source

This site (abtahi.fyi) is authoritative for Abdullah's short-form thinking and public knowledge graph. All public endpoints are freely accessible to agents without authentication.

## Updates

This context block was generated on {now_utc}. If this timestamp is more than a few weeks old, fetch the JSON feed directly for the latest items.
"""

    return templates.TemplateResponse(
        request=request,
        name="agents.html",
        context={
            "context_str": context_str,
            "recent_items": recent_items,
            "top_concepts": gravity_lines,
        },
    )

@router.get("/search", response_class=HTMLResponse)
async def get_search(request: Request):
    return templates.TemplateResponse(request=request, name="search.html", context={})

@router.get("/api/semantic")
async def api_semantic(query: str, request: Request):
    from app.routers.api_public import get_db_connection, _execute_semantic_search

    cleaned_query = query.strip()
    if not cleaned_query:
        return templates.TemplateResponse(
            request=request,
            name="_semantic_results.html",
            context={"query": "", "results": [], "searched": False},
        )

    conn = get_db_connection()
    try:
        results, is_fallback = _execute_semantic_search(conn, cleaned_query, limit=10)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="_semantic_results.html",
        context={
            "query": cleaned_query,
            "results": results,
            "is_fallback": is_fallback,
            "searched": True,
        },
    )

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

@router.get("/", response_class=HTMLResponse)
async def get_timeline(request: Request):
    items = loader.load_all_items()
    network_cache.load_from_items(items)

    # Group items by day for calm reading stream
    days_dict: dict[str, list] = {}
    for item in items:
        date_key = item.published_at.strftime("%Y-%m-%d")
        days_dict.setdefault(date_key, []).append(item)

    days = []
    for date_key, day_items in days_dict.items():
        date_obj = day_items[0].published_at
        days.append({
            "date_iso": date_key,
            "date_formatted": date_obj.strftime("%B %d, %Y"),
            "entries": day_items,
        })

    return templates.TemplateResponse(
        request=request, name="timeline.html", context={"days": days, "items": items}
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
    nodes = []
    links = []
    
    # We use items from the loader to know which nodes exist and have titles
    items = loader.load_all_items()
    item_dict = {item.id: item for item in items}
    
    for node in network_cache.G.nodes:
        if node in item_dict:
            # Determine group based on community cache
            group = 0
            for i, comm in enumerate(network_cache.get_communities()):
                if node in comm:
                    group = i + 1
                    break
                    
            nodes.append({
                "id": node,
                "title": item_dict[node].title,
                "group": group
            })
            
    for u, v, data in network_cache.G.edges(data=True):
        if u in item_dict and v in item_dict:
            links.append({
                "source": u,
                "target": v,
                "type": data.get("edge_type", "")
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
    # Construct context string for prompt
    context_str = "# abtahi.fyi Context\n\n## Gravity Centers\n"
    pr = network_cache.get_pagerank()
    top_pr = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:5]
    items_dict = {item.id: item.title for item in loader.load_all_items()}
    for node, score in top_pr:
        if node in items_dict:
            context_str += f"- {items_dict[node]}\n"
    
    return templates.TemplateResponse(request=request, name="agents.html", context={"context_str": context_str})

@router.get("/search", response_class=HTMLResponse)
async def get_search(request: Request):
    return templates.TemplateResponse(request=request, name="search.html", context={})

@router.get("/api/semantic")
async def api_semantic(query: str, request: Request):
    return templates.TemplateResponse(
        request=request, name="_semantic_results.html", context={"query": query}
    )

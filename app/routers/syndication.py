from fastapi import APIRouter, Request, Depends, Response, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.schemas.feeds import JSONFeed, JSONFeedItem, FyiExtensions
from app.core.public_loader import PublicContentLoader
from app.core.network import network_cache
import os

router = APIRouter(tags=["Syndication"])

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

loader = PublicContentLoader()

@router.get("/", response_class=HTMLResponse)
async def get_timeline(request: Request):
    items = loader.load_all_items()
    return templates.TemplateResponse(
        request=request, name="timeline.html", context={"items": items}
    )

@router.get("/i/{id}", response_class=HTMLResponse, name="get_permalink")
async def get_permalink(request: Request, id: str):
    items = loader.load_all_items()
    item = next((i for i in items if i.id == id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    return templates.TemplateResponse(
        request=request, name="permalink.html", context={"item": item}
    )

@router.get("/llms.txt", response_class=PlainTextResponse)
async def get_llms_txt():
    content = """# abtahi.fyi - Public Context
I am an AI assistant interacting with the public syndication plane of this knowledge graph.
- OpenAPI Schema: `/openapi.json`
- JSON Feed: `/feed.json`
- Semantic Search: `/api/semantic/{q}`
"""
    return PlainTextResponse(content=content, media_type="text/markdown")

@router.get("/feed.json", response_model=JSONFeed, response_model_by_alias=True)
async def get_feed_json(request: Request):
    items = loader.load_all_items()
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
                content_html=item.content_html,
                date_published=item.published_at.isoformat() + "Z" if item.published_at.tzinfo is None else item.published_at.isoformat(),
                _fyi=FyiExtensions(
                    tags=item.tags,
                    pagerank_score=pr_scores.get(item.id),
                    betweenness_score=bw_scores.get(item.id),
                    community_id=group
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
    pr_scores = network_cache.get_pagerank()
    items = loader.load_all_items()
    
    view_items = []
    for item in items:
        score = pr_scores.get(item.id, 0.0)
        view_items.append({
            "id": item.id,
            "title": item.title,
            "metric_value": f"{score:.4f}"
        })
        
    view_items.sort(key=lambda x: float(x["metric_value"]), reverse=True)
    
    return templates.TemplateResponse(
        request=request, name="metrics_view.html", context={
            "title": "Most Connected",
            "description": "Content ranked by PageRank centrality.",
            "metric_label": "PageRank",
            "items": view_items
        }
    )

@router.get("/tensions", response_class=HTMLResponse)
async def get_tensions(request: Request):
    bw_scores = network_cache.get_betweenness()
    items = loader.load_all_items()
    
    view_items = []
    for item in items:
        score = bw_scores.get(item.id, 0.0)
        if score > 0:
            view_items.append({
                "id": item.id,
                "title": item.title,
                "metric_value": f"{score:.4f}"
            })
            
    view_items.sort(key=lambda x: float(x["metric_value"]), reverse=True)
    
    return templates.TemplateResponse(
        request=request, name="metrics_view.html", context={
            "title": "Structural Tensions",
            "description": "Content ranked by Betweenness centrality, acting as bridges between disparate themes.",
            "metric_label": "Betweenness",
            "items": view_items
        }
    )

@router.get("/themes", response_class=HTMLResponse)
async def get_themes(request: Request):
    communities = network_cache.get_communities()
    items = loader.load_all_items()
    item_dict = {item.id: item.title for item in items}
    
    view_items = []
    for i, comm in enumerate(communities):
        for node in comm:
            if node in item_dict:
                view_items.append({
                    "id": node,
                    "title": item_dict[node],
                    "metric_value": f"Theme {i+1}"
                })
                
    view_items.sort(key=lambda x: x["metric_value"])
    
    return templates.TemplateResponse(
        request=request, name="metrics_view.html", context={
            "title": "Emergent Themes",
            "description": "Content grouped by Louvain community detection.",
            "metric_label": "Community",
            "items": view_items
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

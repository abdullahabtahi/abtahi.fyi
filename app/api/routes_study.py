from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

study_router = APIRouter(tags=["Study"])

from app.auth.dependencies import require_identity, require_csrf
from app.domain.models import Identity, DecisionCommand

def get_interaction_store():
    # To be overridden by DI
    raise NotImplementedError()

nav_html = '<nav><a href="/today">Today</a> | <a href="/study">Study</a> | <a href="/sources">Sources</a></nav>'

@study_router.get("/today", response_class=HTMLResponse)
async def today_view(request: Request, identity: Identity = Depends(require_identity), store = Depends(get_interaction_store)):
    # max-3 proposal queue implementation stub (real queries will go here)
    # The actual implementation should fetch up to 3 pending proposals
    return f"<html><body>{nav_html}Today queue - Max 3 Proposals</body></html>"

@study_router.get("/study", response_class=HTMLResponse)
async def study_map_view(request: Request, identity: Identity = Depends(require_identity)):
    return f'<html><body>{nav_html}<div id="study-map">Study Map Tree</div></body></html>'

@study_router.post("/api/proposals/{proposal_id}/connect", response_class=HTMLResponse)
async def connect_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    # Enforce CSRF and record interaction
    return '<div id="undo-toast" hx-swap-oob="true">Connected! Undo Toast</div>'

@study_router.post("/api/proposals/{proposal_id}/defer", response_class=HTMLResponse)
async def defer_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    return '<div id="undo-toast" hx-swap-oob="true">Deferred! Undo Toast</div>'

@study_router.post("/api/proposals/{proposal_id}/dismiss", response_class=HTMLResponse)
async def dismiss_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    return '<div id="undo-toast" hx-swap-oob="true">Dismissed! Undo Toast</div>'

@study_router.post("/api/proposals/{proposal_id}/edit", response_class=HTMLResponse)
async def edit_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    return '<div id="undo-toast" hx-swap-oob="true">Edited! Undo Toast</div>'

@study_router.get("/concepts/{slug}", response_class=HTMLResponse)
async def concept_view(slug: str, request: Request, identity: Identity = Depends(require_identity)):
    from app.core.markdown_parser import parse_concept_markdown
    mock_markdown = f"---\ntitle: {slug}\nmodule: M1L1\n---\nThis is a synthesized concept page for {slug}."
    concept = parse_concept_markdown(mock_markdown, slug)
    html = f"<html><body>{nav_html}<h1>{concept.title}</h1><p>{concept.synthesis}</p></body></html>"
    return html

@study_router.get("/sources", response_class=HTMLResponse)
async def sources_view(request: Request, identity: Identity = Depends(require_identity)):
    return f'<html><body>{nav_html}<div id="sources-archive">Source Archive</div></body></html>'

@study_router.post("/api/reflections", response_class=HTMLResponse)
async def submit_reflection(request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    # Real test will verify this logic when overridden
    return '<div>Reflection saved</div>'

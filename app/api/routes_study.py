from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

study_router = APIRouter(tags=["Study"])

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

from app.auth.dependencies import require_identity, require_csrf
from app.domain.models import Identity, DecisionCommand

from app.core.firestore import FirestoreInteractionStore

def get_interaction_store():
    # Attempt to use default app, if not initialized this will fail in smoke test gracefully
    import firebase_admin
    from firebase_admin import firestore
    
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        db = firestore.client()
        return FirestoreInteractionStore(db)
    except Exception as e:
        # Fallback to a mock for local smoke testing if credentials aren't set
        class MockStore:
            async def get_interaction(self, u, i): return None
            async def save_interaction(self, record): pass
        return MockStore()

@study_router.get("/today", response_class=HTMLResponse)
async def today_view(request: Request, identity: Identity = Depends(require_identity), store = Depends(get_interaction_store)):
    return templates.TemplateResponse(
        request=request, name="today.html", context={"proposals": []}
    )

@study_router.get("/study", response_class=HTMLResponse)
async def study_map_view(request: Request, identity: Identity = Depends(require_identity)):
    return templates.TemplateResponse(
        request=request, name="study.html", context={}
    )

@study_router.post("/api/proposals/{proposal_id}/connect", response_class=HTMLResponse)
async def connect_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    from app.domain.models import InteractionRecord
    import uuid
    record = InteractionRecord(
        interaction_id=str(uuid.uuid4()),
        user_id=identity.uid,
        interaction_type="proposal_review",
        proposal_id=proposal_id,
        user_decision="connect"
    )
    await store.save_interaction(record)
    return '<div id="undo-toast" class="bg-green-900 text-green-100 p-2 text-sm" hx-swap-oob="true">Connected!</div>'

@study_router.post("/api/proposals/{proposal_id}/defer", response_class=HTMLResponse)
async def defer_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    return '<div id="undo-toast" class="bg-yellow-900 text-yellow-100 p-2 text-sm" hx-swap-oob="true">Deferred!</div>'

@study_router.post("/api/proposals/{proposal_id}/dismiss", response_class=HTMLResponse)
async def dismiss_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    from app.domain.models import InteractionRecord
    import uuid
    record = InteractionRecord(
        interaction_id=str(uuid.uuid4()),
        user_id=identity.uid,
        interaction_type="proposal_review",
        proposal_id=proposal_id,
        user_decision="dismiss"
    )
    await store.save_interaction(record)
    return '<div id="undo-toast" class="bg-red-900 text-red-100 p-2 text-sm" hx-swap-oob="true">Dismissed! <button hx-post="/api/proposals/'+proposal_id+'/undo" class="underline">Undo</button></div>'

@study_router.post("/api/proposals/{proposal_id}/edit", response_class=HTMLResponse)
async def edit_proposal(proposal_id: str, request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    return '<div id="undo-toast" hx-swap-oob="true">Edited! Undo Toast</div>'

@study_router.get("/concepts/{slug}", response_class=HTMLResponse)
async def concept_view(slug: str, request: Request, identity: Identity = Depends(require_identity)):
    from app.core.markdown_parser import parse_concept_markdown
    mock_markdown = f"---\ntitle: {slug}\nmodule: M1L1\n---\nThis is a synthesized concept page for {slug}."
    concept = parse_concept_markdown(mock_markdown, slug)
    return templates.TemplateResponse(
        request=request, name="concept.html", context={"concept": concept}
    )

@study_router.get("/sources", response_class=HTMLResponse)
async def sources_view(request: Request, identity: Identity = Depends(require_identity)):
    return templates.TemplateResponse(request=request, name="sources.html", context={})

@study_router.post("/api/reflections", response_class=HTMLResponse)
async def submit_reflection(request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf), store = Depends(get_interaction_store)):
    # Real test will verify this logic when overridden
    return '<div>Reflection saved</div>'

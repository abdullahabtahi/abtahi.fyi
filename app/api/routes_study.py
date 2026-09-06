import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import require_csrf, require_identity
from app.core.firestore import (
    FirestoreReviewStore,
    IdempotencyConflict,
    ReviewStore,
    ReviewStoreUnavailable,
)
from app.domain.models import DecisionCommand, Identity
from app.services.review import ReviewService

study_router = APIRouter(tags=["Study"])
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)


def get_review_store() -> ReviewStore:
    try:
        from firebase_admin import firestore

        return FirestoreReviewStore(firestore.client())
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review storage is unavailable",
        ) from error


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    if len(key) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is too long",
        )
    return key


async def _private_csrf_token(request: Request, identity: Identity) -> str:
    nonce = request.cookies.get("csrf_nonce")
    if not nonce:
        return ""
    from app.auth.dependencies import get_csrf_secret
    from app.web.csrf import generate_csrf_token

    return generate_csrf_token(identity.uid, nonce, get_csrf_secret())


@study_router.get("/today", response_class=HTMLResponse)
async def today_view(
    request: Request,
    identity: Identity = Depends(require_identity),
    store: ReviewStore = Depends(get_review_store),
):
    try:
        proposals = await store.get_pending_proposals(identity.uid, limit=3)
    except ReviewStoreUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review storage is unavailable",
        ) from error
    return templates.TemplateResponse(
        request=request,
        name="today.html",
        context={
            "proposals": proposals,
            "csrf_token": await _private_csrf_token(request, identity),
        },
    )


@study_router.get("/study", response_class=HTMLResponse)
async def study_map_view(
    request: Request, identity: Identity = Depends(require_identity)
):
    return templates.TemplateResponse(request=request, name="study.html", context={})


async def _decide(
    request: Request,
    proposal_id: str,
    command: DecisionCommand,
    identity: Identity,
    store: ReviewStore,
):
    key = _idempotency_key(request)
    form = await request.form()
    reviewed_content = form.get("reviewed_content")
    if command is DecisionCommand.EDIT and not reviewed_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reviewed_content is required for edits",
        )
    try:
        result = await ReviewService(store).decide(
            identity,
            proposal_id,
            command,
            key,
            reviewed_content=str(reviewed_content) if reviewed_content else None,
        )
    except IdempotencyConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key was already used for a different request",
        ) from error
    except ReviewStoreUnavailable:
        return templates.TemplateResponse(
            request=request,
            name="_review_error.html",
            context={
                "action_url": request.url.path,
                "idempotency_key": key,
                "csrf_token": await _private_csrf_token(request, identity),
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return templates.TemplateResponse(
        request=request,
        name="_review_result.html",
        context={"result": result, "proposal_id": proposal_id},
    )


@study_router.post("/api/proposals/{proposal_id}/connect", response_class=HTMLResponse)
async def connect_proposal(
    proposal_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: ReviewStore = Depends(get_review_store),
):
    return await _decide(request, proposal_id, DecisionCommand.CONNECT, identity, store)


@study_router.post("/api/proposals/{proposal_id}/defer", response_class=HTMLResponse)
async def defer_proposal(
    proposal_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: ReviewStore = Depends(get_review_store),
):
    return await _decide(request, proposal_id, DecisionCommand.DEFER, identity, store)


@study_router.post("/api/proposals/{proposal_id}/dismiss", response_class=HTMLResponse)
async def dismiss_proposal(
    proposal_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: ReviewStore = Depends(get_review_store),
):
    return await _decide(request, proposal_id, DecisionCommand.DISMISS, identity, store)


@study_router.post("/api/proposals/{proposal_id}/edit", response_class=HTMLResponse)
async def edit_proposal(
    proposal_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: ReviewStore = Depends(get_review_store),
):
    return await _decide(request, proposal_id, DecisionCommand.EDIT, identity, store)


@study_router.get("/api/operations/{operation_key}")
async def operation_status(
    operation_key: str,
    identity: Identity = Depends(require_identity),
    store: ReviewStore = Depends(get_review_store),
):
    try:
        result = await ReviewService(store).operation_status(identity, operation_key)
    except ReviewStoreUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review storage is unavailable",
        ) from error
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
    return result


@study_router.get("/concepts/{slug}", response_class=HTMLResponse)
async def concept_view(
    slug: str, request: Request, identity: Identity = Depends(require_identity)
):
    from app.core.markdown_parser import parse_concept_markdown

    mock_markdown = (
        f"---\ntitle: {slug}\nmodule: M1L1\n---\n"
        f"This is a synthesized concept page for {slug}."
    )
    concept = parse_concept_markdown(mock_markdown, slug)
    return templates.TemplateResponse(
        request=request, name="concept.html", context={"concept": concept}
    )


@study_router.get("/sources", response_class=HTMLResponse)
async def sources_view(
    request: Request, identity: Identity = Depends(require_identity)
):
    return templates.TemplateResponse(
        request=request,
        name="sources.html",
        context={"csrf_token": await _private_csrf_token(request, identity)},
    )


@study_router.post("/api/reflections", response_class=HTMLResponse)
async def submit_reflection(
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: ReviewStore = Depends(get_review_store),
):
    key = _idempotency_key(request)
    form = await request.form()
    reflection_text = str(form.get("reflection_text", "")).strip()
    if not reflection_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reflection_text is required",
        )
    try:
        result = await ReviewService(store).reflect(identity, reflection_text, key)
    except IdempotencyConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key was already used for a different request",
        ) from error
    except ReviewStoreUnavailable:
        return templates.TemplateResponse(
            request=request,
            name="_review_error.html",
            context={
                "action_url": request.url.path,
                "idempotency_key": key,
                "csrf_token": await _private_csrf_token(request, identity),
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return templates.TemplateResponse(
        request=request, name="_review_result.html", context={"result": result}
    )

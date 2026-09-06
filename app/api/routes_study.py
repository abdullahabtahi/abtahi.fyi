import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import require_csrf, require_identity, get_optional_identity
from app.core.firestore import (
    FirestoreConceptStore,
    FirestoreReviewStore,
    IdempotencyConflict,
    ReviewStore,
    ReviewStoreUnavailable,
)
from app.domain.models import (
    ConceptNode,
    CourseModule,
    DecisionCommand,
    DeferredWindow,
    Identity,
)
from app.models.feed import ConsentDecision
from app.services.consent import ConsentService, ConsentStore, ConsentUnavailable
from app.services.curriculum import CurriculumIngestionService
from app.services.review import ReviewService

study_router = APIRouter(tags=["Study"])
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)


def get_review_store() -> ReviewStore:
    try:
        from firebase_admin import firestore
        from app.adapters.firebase_auth import ensure_firebase_initialized

        app = ensure_firebase_initialized()
        return FirestoreReviewStore(firestore.client(app=app))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review storage is unavailable",
        ) from error


def get_consent_store() -> ConsentStore:
    try:
        from firebase_admin import firestore
        from app.adapters.firebase_auth import ensure_firebase_initialized
        from app.core.firestore import FirestoreConsentStore

        app = ensure_firebase_initialized()
        return FirestoreConsentStore(firestore.client(app=app))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="consent storage is unavailable",
        ) from error


def get_concept_store() -> FirestoreConceptStore:
    try:
        from firebase_admin import firestore
        from app.adapters.firebase_auth import ensure_firebase_initialized

        app = ensure_firebase_initialized()
        return FirestoreConceptStore(firestore.client(app=app))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="concept storage is unavailable",
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
            "identity": identity,
            "proposals": proposals,
            "csrf_token": await _private_csrf_token(request, identity),
        },
    )


@study_router.get("/study", response_class=HTMLResponse)
async def study_map_view(
    request: Request,
    store: FirestoreConceptStore = Depends(get_concept_store),
):
    identity = getattr(request.state, "identity", None)
    if identity is None and hasattr(request, "app"):
        overrides = getattr(request.app, "dependency_overrides", {})
        if require_identity in overrides:
            identity = overrides[require_identity]()
    modules = []


    # 1. If signed in, query personal Firestore modules
    if identity:
        try:
            stored_modules = await store.list_modules(identity.uid)
            all_concepts = await store.list_concepts(identity.uid)

            concepts_by_module: dict[str, list[ConceptNode]] = {}
            for c in all_concepts:
                concepts_by_module.setdefault(c.module, []).append(c)

            module_map = {m.module_id: m for m in stored_modules}
            for mod_id in concepts_by_module:
                if mod_id not in module_map:
                    module_map[mod_id] = CourseModule(
                        module_id=mod_id,
                        title=f"Module {mod_id}",
                        summary="",
                        concepts=[],
                    )

            for mod_id, mod in sorted(module_map.items()):
                mod_concepts = concepts_by_module.get(mod_id, [])
                mod_concepts.sort(key=lambda x: (x.order, x.slug))
                modules.append(
                    {
                        "module_id": mod.module_id,
                        "title": mod.title,
                        "summary": mod.summary,
                        "concepts": mod_concepts,
                    }
                )
        except Exception:
            pass

    # 2. If unauthenticated visitor, load public curriculum from SQLite
    else:
        try:
            import json
            from app.core.db import init_sqlite_db
            conn = init_sqlite_db()
            cursor = conn.cursor()
            cursor.execute("SELECT module_id, title, summary, concept_slugs_json FROM curriculum_milestones ORDER BY module_id")
            milestones = cursor.fetchall()
            for mod_id, mod_title, mod_summary, slugs_json in milestones:
                try:
                    slugs = json.loads(slugs_json)
                except Exception:
                    slugs = []
                mod_concepts = []
                for i, slug in enumerate(slugs):
                    cursor.execute(
                        "SELECT title, summary, synthesis, citations_json, prerequisites_json, keywords_json FROM curriculum_concepts WHERE slug = ?",
                        (slug,),
                    )
                    c_row = cursor.fetchone()
                    if c_row:
                        synth = c_row[2] or c_row[1] or f"Concept analysis for {c_row[0]}."
                        try:
                            citations = json.loads(c_row[3]) if c_row[3] else []
                        except Exception:
                            citations = []
                        mod_concepts.append(
                            ConceptNode(
                                slug=slug,
                                title=c_row[0],
                                module=mod_id,
                                module_title=mod_title,
                                summary=c_row[1] or "",
                                synthesis=synth,
                                citations=citations,
                                order=i + 1,
                            )
                        )

                modules.append(
                    {
                        "module_id": mod_id,
                        "title": mod_title,
                        "summary": mod_summary,
                        "concepts": mod_concepts,
                    }
                )
            conn.close()
        except Exception:
            pass

    csrf_token = await _private_csrf_token(request, identity) if identity else ""
    return templates.TemplateResponse(
        request=request,
        name="study.html",
        context={
            "identity": identity,
            "modules": modules,
            "has_concepts": bool(modules),
            "csrf_token": csrf_token,
        },
    )



@study_router.get("/study/ingest", response_class=HTMLResponse)
async def ingest_view(
    request: Request,
    identity: Identity = Depends(require_identity),
):
    return templates.TemplateResponse(
        request=request,
        name="ingest.html",
        context={
            "identity": identity,
            "csrf_token": await _private_csrf_token(request, identity),
        },
    )


@study_router.post("/api/study/ingest/preview", response_class=HTMLResponse)
async def ingest_preview(
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
):
    form = await request.form()
    content_text = str(form.get("content_text", "")).strip()
    fallback_module = str(form.get("module_id", "M1L1")).strip() or "M1L1"

    upload_file = form.get("file")
    if upload_file and hasattr(upload_file, "read"):
        file_bytes = await upload_file.read()
        if file_bytes:
            content_text = file_bytes.decode("utf-8", errors="replace")

    if not content_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No curriculum content provided. Please paste notes or upload a file.",
        )

    module, concepts = CurriculumIngestionService.parse_curriculum_text(
        content_text, fallback_module=fallback_module
    )

    return templates.TemplateResponse(
        request=request,
        name="_ingest_preview.html",
        context={
            "module": module,
            "concepts": concepts,
            "content_text": content_text,
            "csrf_token": await _private_csrf_token(request, identity),
        },
    )


@study_router.post("/api/study/ingest/commit")
async def ingest_commit(
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: FirestoreConceptStore = Depends(get_concept_store),
):
    form = await request.form()
    content_text = str(form.get("content_text", "")).strip()
    fallback_module = str(form.get("module_id", "M1L1")).strip() or "M1L1"

    if not content_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing curriculum content for commitment.",
        )

    module, concepts = CurriculumIngestionService.parse_curriculum_text(
        content_text, fallback_module=fallback_module
    )

    try:
        result = await CurriculumIngestionService.commit_curriculum(
            uid=identity.uid,
            module=module,
            concepts=concepts,
            concept_store=store,
            raw_source_text=content_text,
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to save concepts to Firestore.",
        ) from error

    if request.headers.get("HX-Request"):
        from fastapi.responses import Response

        response = Response(status_code=status.HTTP_200_OK)
        response.headers["HX-Redirect"] = "/study"
        return response

    return result


@study_router.post("/api/study/seed-sample")
async def seed_sample(
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: FirestoreConceptStore = Depends(get_concept_store),
):
    sample_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "module_sample", "AAIF_600_Foundations_of_Disruption", "M1L1"),
        os.path.join(os.getcwd(), "module_sample", "AAIF_600_Foundations_of_Disruption", "M1L1"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "abtahi-fyi", "module_sample", "AAIF_600_Foundations_of_Disruption", "M1L1"),
        "/Users/abdullahabtahi/Ideathon/module_sample/AAIF_600_Foundations_of_Disruption/M1L1",
    ]
    content_text = None
    for p in sample_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                content_text = f.read()
            break

    if not content_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample curriculum material M1L1 was not found.",
        )

    module, concepts = CurriculumIngestionService.parse_curriculum_text(
        content_text, fallback_module="M1L1"
    )

    try:
        result = await CurriculumIngestionService.commit_curriculum(
            uid=identity.uid,
            module=module,
            concepts=concepts,
            concept_store=store,
            raw_source_text=content_text,
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to seed sample concepts into Firestore.",
        ) from error

    if request.headers.get("HX-Request"):
        from fastapi.responses import Response

        response = Response(status_code=status.HTTP_200_OK)
        response.headers["HX-Redirect"] = "/study"
        return response

    return result


async def _decide(
    request: Request,
    proposal_id: str,
    command: DecisionCommand,
    identity: Identity,
    store: ReviewStore,
):
    key = _idempotency_key(request)
    form = await request.form()
    reviewed_content = str(form.get("reviewed_content", "")).strip() or None
    defer_window_value = str(form.get("defer_window", "")).strip()
    dismissal_operation_id = str(form.get("dismissal_operation_id", "")).strip() or None
    if command in {DecisionCommand.CONNECT, DecisionCommand.EDIT} and not reviewed_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reviewed_content is required",
        )
    try:
        defer_window = (
            DeferredWindow(defer_window_value)
            if command is DecisionCommand.DEFER
            else None
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="defer_window is required",
        ) from error
    if command is DecisionCommand.DEFER and defer_window is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="defer_window is required",
        )
    if command is DecisionCommand.UNDO and dismissal_operation_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dismissal_operation_id is required",
        )
    try:
        result = await ReviewService(store).decide(
            identity,
            proposal_id,
            command,
            key,
            reviewed_content=reviewed_content,
            defer_window=defer_window,
            dismissal_operation_id=dismissal_operation_id,
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
        context={
            "result": result,
            "proposal_id": proposal_id,
            "csrf_token": await _private_csrf_token(request, identity),
        },
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


@study_router.post("/api/proposals/{proposal_id}/undo", response_class=HTMLResponse)
async def undo_proposal(
    proposal_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: ReviewStore = Depends(get_review_store),
):
    return await _decide(request, proposal_id, DecisionCommand.UNDO, identity, store)


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
    slug: str,
    request: Request,
):
    identity = getattr(request.state, "identity", None)
    if identity is None and hasattr(request, "app"):
        overrides = getattr(request.app, "dependency_overrides", {})
        if require_identity in overrides:
            identity = overrides[require_identity]()
    concept = None



    # 1. Fast public resolution from SQLite
    try:
        import json
        from app.core.db import init_sqlite_db
        conn = init_sqlite_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT slug, title, module_id, module_title, summary, synthesis, citations_json, prerequisites_json, keywords_json
            FROM curriculum_concepts WHERE slug = ?
            """,
            (slug,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            concept = ConceptNode(
                slug=row[0],
                title=row[1],
                module=row[2],
                module_title=row[3],
                summary=row[4],
                synthesis=row[5],
                citations=json.loads(row[6]) if row[6] else [],
                prerequisites=json.loads(row[7]) if row[7] else [],
                keywords=json.loads(row[8]) if row[8] else [],
            )
    except Exception:
        pass

    # 2. Authenticated fallback to Firestore
    if not concept and identity:
        try:
            concept = await store.get_concept(identity.uid, slug)
        except Exception:
            pass

    # 3. Graceful fallback synthesis
    if not concept:
        from app.core.markdown_parser import parse_concept_markdown

        mock_markdown = (
            f"---\ntitle: {slug.replace('-', ' ').title()}\nmodule: M1L1\n---\n"
            f"Synthesized curriculum concept notes for {slug}."
        )
        concept = parse_concept_markdown(mock_markdown, slug)

    return templates.TemplateResponse(
        request=request,
        name="concept.html",
        context={"identity": identity, "concept": concept},
    )



@study_router.get("/sources", response_class=HTMLResponse)
async def sources_view(
    request: Request,
    identity: Identity = Depends(require_identity),
    store: FirestoreConceptStore = Depends(get_concept_store),
):
    sources = []
    try:
        sources = await store.list_sources(identity.uid)
    except Exception:
        sources = []
    return templates.TemplateResponse(
        request=request,
        name="sources.html",
        context={
            "identity": identity,
            "sources": sources,
            "csrf_token": await _private_csrf_token(request, identity),
        },
    )


@study_router.post("/api/source-revisions/{revision_id}/consent")
async def record_source_consent(
    revision_id: str,
    request: Request,
    identity: Identity = Depends(require_identity),
    csrf_ok: bool = Depends(require_csrf),
    store: ConsentStore = Depends(get_consent_store),
):
    _idempotency_key(request)
    form = await request.form()
    purpose = str(form.get("purpose", "")).strip()
    provider = str(form.get("provider", "")).strip()
    granted_value = str(form.get("granted", "")).strip().lower()
    if not purpose or not provider or granted_value not in {"true", "false"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="purpose, provider, and granted are required",
        )
    decision = ConsentDecision(
        uid=identity.uid,
        revision_id=revision_id,
        purpose=purpose,
        provider=provider,
        granted=granted_value == "true",
        decided_at=datetime.now(timezone.utc),
    )
    try:
        await ConsentService(store).record(decision)
    except ConsentUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="consent storage is unavailable",
        ) from error
    return {
        "revision_id": decision.revision_id,
        "purpose": decision.purpose,
        "provider": decision.provider,
        "granted": decision.granted,
    }


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

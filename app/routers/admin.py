from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from app.auth.dependencies import require_job_identity
from app.storage.archive import ArchiveUnavailable
from app.services.ingestion import IngestionService

router = APIRouter()

from app.schemas.synthesis import ConsolidationReport, ConsolidationStatus
from app.ai.synthesis import run_consolidation
from app.core.network import network_cache
from app.core.db import init_sqlite_db


def get_ingestion_service() -> IngestionService:
    try:
        from firebase_admin import firestore
        from google.cloud import storage

        from app.adapters.firebase_auth import ensure_firebase_initialized
        from app.core.firestore import FirestoreSourceMetadataStore
        from app.models.feed import ApprovedFeed
        from app.settings import Settings
        from app.storage.archive import CloudStorageSourceArchive

        settings = Settings()
        feed_urls = tuple(
            url.strip() for url in settings.APPROVED_FEED_URLS.split(",") if url.strip()
        )
        if not settings.INGESTION_OWNER_UID or not feed_urls:
            raise ValueError("ingestion registry is not configured")
        firebase_app = ensure_firebase_initialized()
        feeds = tuple(
            ApprovedFeed(id=f"feed-{index}", url=url)
            for index, url in enumerate(feed_urls, start=1)
        )
        bucket = storage.Client(project=settings.GCP_PROJECT_ID).bucket(
            settings.FIREBASE_STORAGE_BUCKET
        )
        return IngestionService(
            CloudStorageSourceArchive(bucket),
            FirestoreSourceMetadataStore(firestore.client(app=firebase_app)),
            owner_uid=settings.INGESTION_OWNER_UID,
            feeds=feeds,
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ingestion service is unavailable",
        ) from error


@router.post("/api/poll-feeds")
async def poll_registered_feeds(
    job_authorized: bool = Depends(require_job_identity),
    service: IngestionService = Depends(get_ingestion_service),
):
    try:
        return await service.collect_registered_feeds()
    except ArchiveUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ingestion service is unavailable",
        ) from error

@router.post("/api/consolidate", response_model=ConsolidationReport)
async def consolidate_graph(
    request: Request,
    dry_run: bool = False,
    job_authorized: bool = Depends(require_job_identity),
):
    """Triggers Nightly Graph Consolidation ('Dream Cycle').

    Supports dry-run queries and returns a full ConsolidationReport.
    Protected by admin authentication / Cloud Scheduler bearer tokens.
    """
    conn = init_sqlite_db()
    try:
        report = await run_consolidation(
            db_conn=conn,
            network_cache=network_cache,
            dry_run=dry_run,
        )
    finally:
        conn.close()

    if report.status == ConsolidationStatus.FAILED:
        return JSONResponse(
            status_code=500,
            content=report.model_dump(mode="json"),
        )
    return JSONResponse(
        status_code=200,
        content=report.model_dump(mode="json"),
    )

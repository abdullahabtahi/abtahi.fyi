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


from datetime import datetime, timezone
from app.core.observability import (
    ScheduledOperationOutcome,
    OperationalEvent,
    emit_operational_event,
)


@router.post("/api/poll-feeds")
async def poll_registered_feeds(
    request: Request,
    job_authorized: bool = Depends(require_job_identity),
    service: IngestionService = Depends(get_ingestion_service),
):
    started_at = datetime.now(timezone.utc)
    op_id = request.headers.get("X-CloudScheduler-JobName", f"poll-{int(started_at.timestamp())}")
    invoker = getattr(request.state, "job_identity", "scheduler-service")
    try:
        results = await service.collect_registered_feeds()
        completed_at = datetime.now(timezone.utc)
        emit_operational_event(OperationalEvent(
            event_name="scheduled_job_completed",
            severity="INFO",
            labels={"operation_type": "poll_feeds", "status": "completed"}
        ))
        return results
    except ArchiveUnavailable as error:
        emit_operational_event(OperationalEvent(
            event_name="scheduled_job_failed",
            severity="ERROR",
            labels={"operation_type": "poll_feeds", "status": "unavailable"}
        ))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ingestion service is unavailable",
        ) from error
    except Exception as exc:
        emit_operational_event(OperationalEvent(
            event_name="scheduled_job_failed",
            severity="ERROR",
            labels={"operation_type": "poll_feeds", "status": "failed"}
        ))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="feed polling failed",
        ) from exc


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

    status_str = "completed" if report.status != ConsolidationStatus.FAILED else "failed"
    emit_operational_event(OperationalEvent(
        event_name="scheduled_job_completed" if status_str == "completed" else "scheduled_job_failed",
        severity="INFO" if status_str == "completed" else "ERROR",
        labels={"operation_type": "consolidate", "status": status_str}
    ))

    if report.status == ConsolidationStatus.FAILED:
        return JSONResponse(
            status_code=500,
            content=report.model_dump(mode="json"),
        )
    return JSONResponse(
        status_code=200,
        content=report.model_dump(mode="json"),
    )

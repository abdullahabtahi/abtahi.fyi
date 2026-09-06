"""CLI command to ingest course lecture materials into Google Cloud Firestore.

Usage:
    python -m app.cli.ingest_course <file_path> [--module MODULE_ID] [--uid USER_ID] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from app.core.firestore import FirestoreConceptStore
from app.services.curriculum import CurriculumIngestionService
from app.settings import Settings


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest course lecture materials and extract concepts into Firestore."
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to the lecture notes file (.txt or .md).",
    )
    parser.add_argument(
        "--module",
        type=str,
        default=None,
        help="Optional module identifier override (e.g., M1L1).",
    )
    parser.add_argument(
        "--uid",
        type=str,
        default=None,
        help="Target learner user ID (defaults to INGESTION_OWNER_UID in settings).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and display extracted concepts without committing to Firestore.",
    )
    args = parser.parse_args()

    path = Path(args.file_path).resolve()
    if not path.is_file():
        print(f"Error: File not found at {path}", file=sys.stderr)
        return 1

    with open(path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    fallback_mod = args.module or path.stem
    module, concepts = CurriculumIngestionService.parse_curriculum_text(
        raw_text, fallback_module=fallback_mod
    )

    print("\n" + "=" * 60)
    print(f"CURRICULUM INGESTION: {module.module_id}")
    print(f"Title: {module.title}")
    print(f"Concepts Extracted: {len(concepts)}")
    print("=" * 60)

    for c in concepts:
        kw_str = ", ".join(c.keywords[:4]) if c.keywords else "none"
        print(f"\n • [{c.slug}] #{c.order}: {c.title}")
        print(f"   Summary: {c.summary}")
        print(f"   Keywords: {kw_str}")

    if args.dry_run:
        print("\n[DRY RUN]: No changes written to Firestore.")
        return 0

    settings = Settings()
    uid = args.uid or settings.INGESTION_OWNER_UID or os.getenv("ALLOWLISTED_EMAIL")
    if not uid:
        print(
            "\nError: No learner UID provided and INGESTION_OWNER_UID is not set in environment.",
            file=sys.stderr,
        )
        return 1

    try:
        from firebase_admin import firestore
        from app.adapters.firebase_auth import ensure_firebase_initialized

        firebase_app = ensure_firebase_initialized()
        db = firestore.client(app=firebase_app)
        concept_store = FirestoreConceptStore(db)

        result = await CurriculumIngestionService.commit_curriculum(
            uid=uid,
            module=module,
            concepts=concepts,
            concept_store=concept_store,
            raw_source_text=raw_text,
        )
        print("\n" + "=" * 60)
        print(f"SUCCESS: Committed {result['concepts_count']} concepts to /users/{uid}/concepts/")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\nFirestore commitment error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

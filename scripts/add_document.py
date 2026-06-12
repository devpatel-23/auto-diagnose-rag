"""
scripts/add_document.py
------------------------
Adds a single new document to the vector store WITHOUT clearing existing data.
Use this when you want to add new knowledge without re-running the full ingestion.

USAGE:
    # Add a specific file
    python scripts/add_document.py data/repair_docs/08_cooling_system.txt

    # Add all files in a directory
    python scripts/add_document.py data/repair_docs/ --all

    # Preview what would be added (dry run)
    python scripts/add_document.py data/repair_docs/08_cooling_system.txt --dry-run
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from backend.models.database import init_db, SessionLocal, RepairDocument
from backend.services.vector_store import store_document_chunks, document_count


def add_single_document(filepath: str, db, dry_run: bool = False) -> int:
    """
    Adds one file to the vector store.
    Skips if the file has already been ingested (same filename already in DB).

    Returns number of chunks added (0 if skipped).
    """
    filename = os.path.basename(filepath)

    # Check if already ingested
    existing = db.query(RepairDocument)\
        .filter(RepairDocument.source_file == filename)\
        .first()

    if existing:
        logger.warning(f"⚠️  '{filename}' already in database. Use --force to re-ingest.")
        return 0

    if not os.path.exists(filepath):
        logger.error(f"❌ File not found: {filepath}")
        return 0

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        logger.warning(f"⚠️  File is empty: {filepath}")
        return 0

    logger.info(f"📄 Processing: {filename} ({len(content):,} chars)")

    if dry_run:
        # Count chunks without actually storing
        from backend.services.vector_store import chunk_text
        chunks = chunk_text(content)
        logger.info(f"   [DRY RUN] Would store {len(chunks)} chunks")
        return len(chunks)

    chunks_stored = store_document_chunks(db, filename, content)
    return chunks_stored


def main():
    parser = argparse.ArgumentParser(
        description="Add documents to the vehicle repair chatbot knowledge base"
    )
    parser.add_argument(
        "path",
        help="Path to a .txt file, or a directory if --all is used"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all .txt files in the given directory"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if the file already exists in the database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes"
    )
    args = parser.parse_args()

    # Initialize DB
    init_db()
    db = SessionLocal()

    try:
        before_count = document_count(db)
        logger.info(f"Vector store currently has {before_count} chunks")

        total_added = 0

        if args.all:
            # Process all .txt files in directory
            if not os.path.isdir(args.path):
                logger.error(f"Not a directory: {args.path}")
                sys.exit(1)

            files = sorted([
                os.path.join(args.path, f)
                for f in os.listdir(args.path)
                if f.endswith(".txt")
            ])

            if not files:
                logger.error(f"No .txt files found in {args.path}")
                sys.exit(1)

            for filepath in files:
                # If --force, remove existing entry first
                if args.force:
                    filename = os.path.basename(filepath)
                    db.query(RepairDocument)\
                        .filter(RepairDocument.source_file == filename)\
                        .delete()
                    db.commit()

                added = add_single_document(filepath, db, dry_run=args.dry_run)
                total_added += added
        else:
            # Single file
            if args.force:
                filename = os.path.basename(args.path)
                db.query(RepairDocument)\
                    .filter(RepairDocument.source_file == filename)\
                    .delete()
                db.commit()

            total_added = add_single_document(args.path, db, dry_run=args.dry_run)

        after_count = document_count(db)

        if args.dry_run:
            logger.info(f"\n[DRY RUN] Would add ~{total_added} chunks")
        else:
            logger.info(f"\n✅ Added {total_added} new chunks")
            logger.info(f"   Before: {before_count} | After: {after_count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from app.core.logger import logger
from app.rag_ingest.markdown_parser import MarkdownParser
from app.rag_ingest.milvus_store import MilvusVectorStore


def iter_markdown_files(md_dir: str | Path, *, limit: Optional[int] = None) -> Iterable[Path]:
    files = sorted(Path(md_dir).glob("*.md"))
    if limit is not None:
        files = files[:limit]
    yield from files


def ingest_markdown_dir(
    md_dir: str | Path,
    *,
    batch_size: int = 20,
    drop_existing: bool = False,
    limit: Optional[int] = None,
    enable_semantic_chunking: bool = True,
) -> int:
    md_dir = Path(md_dir)
    if not md_dir.is_dir():
        raise FileNotFoundError(f"Markdown directory does not exist: {md_dir}")

    store = MilvusVectorStore()
    store.create_collection(drop_existing=drop_existing)
    store.create_connection()

    parser = MarkdownParser(enable_semantic_chunking=enable_semantic_chunking)
    pending = []
    total = 0

    files = list(iter_markdown_files(md_dir, limit=limit))
    if not files:
        logger.warning(f"No Markdown files found in {md_dir}")
        return 0

    for md_file in files:
        try:
            pending.extend(parser.parse_markdown_to_documents(md_file))
        except Exception:
            logger.exception(f"Failed to parse Markdown file: {md_file}")
            continue

        if len(pending) >= batch_size:
            store.add_documents(pending)
            total += len(pending)
            logger.info(f"Milvus ingest progress: documents={total}")
            pending.clear()

    if pending:
        store.add_documents(pending)
        total += len(pending)

    logger.info(f"Milvus ingest completed: files={len(files)}, documents={total}")
    return total


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Markdown files into Milvus hybrid RAG.")
    parser.add_argument("--md-dir", required=True, help="Directory containing .md files.")
    parser.add_argument("--batch-size", type=int, default=20, help="Documents per Milvus write batch.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of Markdown files.")
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop and recreate the configured Milvus collection before ingest.",
    )
    parser.add_argument(
        "--skip-semantic-chunking",
        action="store_true",
        help="Parse and merge Markdown without SemanticChunker.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    total = ingest_markdown_dir(
        args.md_dir,
        batch_size=args.batch_size,
        drop_existing=args.drop_existing,
        limit=args.limit,
        enable_semantic_chunking=not args.skip_semantic_chunking,
    )
    print(f"Milvus ingest completed, documents={total}")


if __name__ == "__main__":
    main()

"""CLI entry point for preparing and indexing a GraphRAG workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.graphrag_cli.config import GraphRAGCLIConfig
from app.graphrag_cli.indexer import GraphRAGCLIIndexer, prepare_workspace_input


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a GraphRAG workspace input directory and run graphrag index."
    )
    parser.add_argument(
        "--root",
        default=str(GraphRAGCLIConfig.workspace_root),
        help="GraphRAG workspace root containing settings.yaml.",
    )
    parser.add_argument(
        "--md-dir",
        default=None,
        help="Optional directory of .md files to copy into <root>/input before indexing.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit copied Markdown files.")
    parser.add_argument(
        "--clear-input",
        action="store_true",
        help="Clear <root>/input before copying files from --md-dir.",
    )
    parser.add_argument(
        "--method",
        default="standard",
        choices=["standard", "fast"],
        help="GraphRAG indexing method.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional GraphRAG output directory override.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3600.0,
        help="Index timeout in seconds.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = Path(args.root)

    if args.md_dir:
        copied = prepare_workspace_input(
            md_dir=args.md_dir,
            workspace_root=root,
            limit=args.limit,
            clear_input=args.clear_input,
        )
        print(f"GraphRAG workspace input prepared, copied={len(copied)}")

    result = GraphRAGCLIIndexer().index_sync(
        root=root,
        method=args.method,
        output=args.output,
        timeout_seconds=args.timeout,
    )
    print(f"GraphRAG index completed, returncode={result.returncode}, elapsed={result.elapsed_seconds:.2f}s")
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())


if __name__ == "__main__":
    main()

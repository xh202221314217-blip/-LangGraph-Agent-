"""Smoke command for the GraphRAG CLI wrapper."""

from __future__ import annotations

import argparse
import sys

from app.graphrag_cli import GraphRAGCLIConfig, GraphRAGCLIError, GraphRAGCLIRetriever


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a GraphRAG CLI wrapper smoke query.")
    parser.add_argument(
        "--query",
        default="GAAFET 相比 FinFET 的关键优势是什么？",
        help="Question to send to GraphRAG.",
    )
    parser.add_argument(
        "--method",
        default=None,
        choices=["local", "global", "drift", "basic"],
        help="GraphRAG query method. Defaults to GRAPHRAG_CLI_DEFAULT_METHOD or local.",
    )
    parser.add_argument("--root", default=None, help="GraphRAG workspace root.")
    parser.add_argument("--data", default=None, help="Optional GraphRAG output data directory.")
    parser.add_argument("--response-type", default=None, help="Optional GraphRAG response type.")
    parser.add_argument("--timeout", type=float, default=None, help="Timeout in seconds.")
    args = parser.parse_args()

    retriever = GraphRAGCLIRetriever(GraphRAGCLIConfig.from_env())
    try:
        result = retriever.query_sync(
            args.query,
            method=args.method,
            root=args.root,
            data=args.data,
            response_type=args.response_type,
            timeout_seconds=args.timeout,
        )
    except (GraphRAGCLIError, ValueError) as exc:
        print(f"GraphRAG CLI smoke failed: {exc}", file=sys.stderr)
        return 1

    print(f"method={result.method}")
    print(f"root={result.root}")
    print(f"returncode={result.returncode}")
    print(f"elapsed_seconds={result.elapsed_seconds:.2f}")
    print("text:")
    print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

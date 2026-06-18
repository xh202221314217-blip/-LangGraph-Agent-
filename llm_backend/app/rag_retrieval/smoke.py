from __future__ import annotations

import argparse

from app.rag_retrieval.milvus_retriever import MilvusHybridRetriever, MilvusRetrieverConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test Milvus hybrid retrieval.")
    parser.add_argument("--query", required=True, help="Question or keyword query.")
    parser.add_argument("--top-k", type=int, default=None, help="Override retrieval top-k.")
    parser.add_argument(
        "--filter-category",
        default=None,
        help="Override category filter. Use an empty string to disable filtering.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = MilvusRetrieverConfig(
        top_k=args.top_k or MilvusRetrieverConfig.top_k,
        filter_category=(
            MilvusRetrieverConfig.filter_category
            if args.filter_category is None
            else args.filter_category
        ),
    )
    documents = MilvusHybridRetriever(config=config).search(args.query)
    print(f"documents={len(documents)}")
    for index, document in enumerate(documents, start=1):
        title = document.metadata.get("title") or document.metadata.get("filename") or ""
        preview = " ".join((document.page_content or "").split())[:240]
        print(f"[{index}] {title}\n{preview}\n")


if __name__ == "__main__":
    main()

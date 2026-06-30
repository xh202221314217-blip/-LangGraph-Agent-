"""Quick smoke checks for the GraphRAG CLI + Milvus hybrid RAG merge.

This script intentionally avoids external LLM calls. It verifies local wiring,
static assets, CLI availability, and legacy route isolation.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LLM_BACKEND = PROJECT_ROOT / "llm_backend"
STATIC_DIST = LLM_BACKEND / "static" / "dist"


class SmokeFailure(RuntimeError):
    """Raised when a smoke check fails."""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run(command: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def check_static_frontend() -> None:
    expected = [
        STATIC_DIST / "index.html",
        STATIC_DIST / "assets" / "app.css",
        STATIC_DIST / "assets" / "app.js",
    ]
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in expected if not path.exists()]
    if missing:
        raise SmokeFailure(f"Missing static frontend files: {missing}")

    combined = "\n".join(_read(path) for path in expected)
    required_terms = ["Markdown Knowledge RAG", "/api/langgraph/query", "method=\"post\"", "requestSubmit"]
    missing_terms = [term for term in required_terms if term not in combined]
    if missing_terms:
        raise SmokeFailure(f"Static frontend is missing expected terms: {missing_terms}")

    forbidden_terms = ["商品", "订单", "供应商", "智能家居", "ProductService", "/api/products"]
    found = [term for term in forbidden_terms if term in combined]
    if found:
        raise SmokeFailure(f"Static frontend still contains legacy terms: {found}")


def check_active_runtime_boundary() -> None:
    active_files = [
        LLM_BACKEND / "app" / "lg_agent" / "lg_builder.py",
        LLM_BACKEND / "app" / "lg_agent" / "lg_prompts.py",
        LLM_BACKEND / "main.py",
    ]
    combined = "\n".join(_read(path) for path in active_files)
    forbidden = ["kg_sub_graph", "NorthwindCypherRetriever", "create_multi_tool_workflow"]
    found = [term for term in forbidden if term in combined]
    if found:
        raise SmokeFailure(f"Active runtime files reference legacy KG path: {found}")

    main_py = _read(LLM_BACKEND / "main.py")
    if "RAGChatService()" in main_py:
        raise SmokeFailure("Deprecated /chat-rag route still calls RAGChatService().")
    if "status_code=410" not in main_py:
        raise SmokeFailure("Deprecated /chat-rag route should return HTTP 410.")


def check_graphrag_cli_help(cli_path: str, timeout: float) -> None:
    query_help = _run([cli_path, "query", "--help"], timeout=timeout)
    if query_help.returncode != 0:
        raise SmokeFailure(
            "GraphRAG query help failed: "
            f"returncode={query_help.returncode} stderr={query_help.stderr.strip()[:400]}"
        )

    help_text = query_help.stdout + query_help.stderr
    compact_help = "".join(help_text.split())
    missing_methods = [method for method in ["local", "global", "basic"] if method not in compact_help]
    if missing_methods:
        raise SmokeFailure(f"GraphRAG query help missing methods: {missing_methods}")

    drift_probe = _run(
        [
            cli_path,
            "query",
            "--method",
            "drift",
            "--query",
            "smoke",
            "--root",
            "/tmp/no-such-graphrag-workspace",
        ],
        timeout=timeout,
    )
    drift_output = drift_probe.stdout + drift_probe.stderr
    if "Invalid value for '--method'" in drift_output or "Invalid value for '--root'" not in drift_output:
        raise SmokeFailure("GraphRAG CLI did not accept --method drift.")

    index_help = _run([cli_path, "index", "--help"], timeout=timeout)
    if index_help.returncode != 0:
        raise SmokeFailure(
            "GraphRAG index help failed: "
            f"returncode={index_help.returncode} stderr={index_help.stderr.strip()[:400]}"
        )


def check_compile() -> None:
    targets = [
        "llm_backend/app/graphrag_cli",
        "llm_backend/app/rag_ingest",
        "llm_backend/app/rag_retrieval",
        "llm_backend/app/lg_agent",
        "llm_backend/app/smoke",
        "llm_backend/main.py",
    ]
    result = _run([sys.executable, "-m", "compileall", "-q", *targets], timeout=60)
    if result.returncode != 0:
        raise SmokeFailure(
            "Python compile smoke failed: "
            f"stdout={result.stdout.strip()[:400]} stderr={result.stderr.strip()[:400]}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run quick local smoke checks for the merged RAG app.")
    parser.add_argument(
        "--graphrag-cli",
        default=str(PROJECT_ROOT / ".venv" / "bin" / "graphrag"),
        help="Path to the graphrag CLI executable.",
    )
    parser.add_argument(
        "--skip-cli-help",
        action="store_true",
        help="Skip GraphRAG CLI help checks.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-command timeout in seconds.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    checks = [
        ("static frontend", check_static_frontend),
        ("active runtime boundary", check_active_runtime_boundary),
        ("python compile", check_compile),
    ]

    if not args.skip_cli_help:
        checks.append(
            (
                "GraphRAG CLI help",
                lambda: check_graphrag_cli_help(args.graphrag_cli, args.timeout),
            )
        )

    for name, check in checks:
        check()
        print(f"ok - {name}")

    print("merged RAG smoke checks passed")


if __name__ == "__main__":
    main()

"""Async wrapper around `graphrag index`."""

from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.graphrag_cli.config import GraphRAGCLIConfig
from app.graphrag_cli.retriever import GraphRAGCLIError


GraphRAGIndexMethod = Literal["standard", "fast"]
VALID_INDEX_METHODS = {"standard", "fast"}


@dataclass(frozen=True)
class GraphRAGIndexResult:
    """Structured result returned by GraphRAG index."""

    root: str
    method: str
    output: str | None
    stdout: str
    stderr: str
    returncode: int
    elapsed_seconds: float
    command: tuple[str, ...]


class GraphRAGCLIIndexer:
    """Run GraphRAG indexing through the installed CLI."""

    def __init__(self, config: GraphRAGCLIConfig | None = None) -> None:
        self.config = config or GraphRAGCLIConfig.from_env()

    async def index(
        self,
        *,
        root: str | Path | None = None,
        method: str = "standard",
        output: str | Path | None = None,
        timeout_seconds: float | None = None,
    ) -> GraphRAGIndexResult:
        selected_root = Path(root) if root is not None else self.config.workspace_root
        if not selected_root.exists():
            raise FileNotFoundError(f"GraphRAG workspace root does not exist: {selected_root}")

        if method not in VALID_INDEX_METHODS:
            raise ValueError(
                f"Unsupported GraphRAG index method '{method}'. "
                f"Expected one of: {', '.join(sorted(VALID_INDEX_METHODS))}."
            )

        selected_output = Path(output) if output is not None else None
        selected_timeout = timeout_seconds or self.config.timeout_seconds
        command = [
            self.config.cli_path,
            "index",
            "--root",
            str(selected_root),
            "--method",
            method,
        ]
        if selected_output is not None:
            command.extend(["--output", str(selected_output)])

        start = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=selected_timeout,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise GraphRAGCLIError(
                f"GraphRAG CLI index timed out after {selected_timeout:.1f}s: {' '.join(command)}"
            ) from exc

        elapsed = time.monotonic() - start
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = process.returncode if process.returncode is not None else -1

        if returncode != 0:
            detail = (stderr or stdout).strip()
            raise GraphRAGCLIError(
                "GraphRAG CLI index failed "
                f"(returncode={returncode}, method={method}, root={selected_root}). "
                f"{detail}"
            )

        return GraphRAGIndexResult(
            root=str(selected_root),
            method=method,
            output=str(selected_output) if selected_output is not None else None,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            elapsed_seconds=elapsed,
            command=tuple(command),
        )

    def index_sync(self, **kwargs) -> GraphRAGIndexResult:
        """Synchronous convenience wrapper for scripts and smoke checks."""

        return asyncio.run(self.index(**kwargs))


def prepare_workspace_input(
    *,
    md_dir: str | Path,
    workspace_root: str | Path,
    limit: int | None = None,
    clear_input: bool = False,
) -> list[Path]:
    """Copy Markdown files into a GraphRAG workspace input directory."""

    source_dir = Path(md_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Markdown directory does not exist: {source_dir}")

    input_dir = Path(workspace_root) / "input"
    if clear_input and input_dir.exists():
        shutil.rmtree(input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(source_dir.glob("*.md"))
    if limit is not None:
        files = files[:limit]

    copied: list[Path] = []
    for source in files:
        destination = input_dir / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        copied.append(destination)
    return copied

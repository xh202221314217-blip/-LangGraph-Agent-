"""Async wrapper around `graphrag query`."""

from __future__ import annotations

import asyncio
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.graphrag_cli.config import GraphRAGCLIConfig


GraphRAGQueryMethod = Literal["local", "global", "drift", "basic"]
VALID_METHODS = {"local", "global", "drift", "basic"}


class GraphRAGCLIError(RuntimeError):
    """Raised when GraphRAG CLI execution fails."""


@dataclass(frozen=True)
class GraphRAGCLIResult:
    """Structured result returned by GraphRAG CLI."""

    query: str
    method: str
    root: str
    data: str | None
    response_type: str | None
    text: str
    stdout: str
    stderr: str
    returncode: int
    elapsed_seconds: float
    command: tuple[str, ...]


class GraphRAGCLIRetriever:
    """Run GraphRAG local indexes through the installed CLI."""

    def __init__(self, config: GraphRAGCLIConfig | None = None) -> None:
        self.config = config or GraphRAGCLIConfig.from_env()

    async def query(
        self,
        query: str,
        *,
        method: str | None = None,
        root: str | Path | None = None,
        data: str | Path | None = None,
        response_type: str | None = None,
        timeout_seconds: float | None = None,
    ) -> GraphRAGCLIResult:
        """Execute `graphrag query` and return cleaned text plus raw process output."""

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")

        selected_method = method or self.config.default_method
        if selected_method not in VALID_METHODS:
            raise ValueError(
                f"Unsupported GraphRAG query method '{selected_method}'. "
                f"Expected one of: {', '.join(sorted(VALID_METHODS))}."
            )

        selected_root = Path(root) if root is not None else self.config.workspace_root
        selected_data = Path(data) if data is not None else None
        selected_response_type = response_type
        if selected_response_type is None:
            selected_response_type = self.config.response_type
        selected_timeout = timeout_seconds or self.config.timeout_seconds

        command = self._build_command(
            query=normalized_query,
            method=selected_method,
            root=selected_root,
            data=selected_data,
            response_type=selected_response_type,
        )

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
                f"GraphRAG CLI query timed out after {selected_timeout:.1f}s: "
                f"{self._format_command(command)}"
            ) from exc

        elapsed = time.monotonic() - start
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = process.returncode if process.returncode is not None else -1

        if returncode != 0:
            detail = (stderr or stdout).strip()
            raise GraphRAGCLIError(
                "GraphRAG CLI query failed "
                f"(returncode={returncode}, method={selected_method}, root={selected_root}). "
                f"{detail}"
            )

        return GraphRAGCLIResult(
            query=normalized_query,
            method=selected_method,
            root=str(selected_root),
            data=str(selected_data) if selected_data is not None else None,
            response_type=selected_response_type,
            text=clean_graphrag_stdout(stdout),
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            elapsed_seconds=elapsed,
            command=tuple(command),
        )

    def query_sync(self, *args, **kwargs) -> GraphRAGCLIResult:
        """Synchronous convenience wrapper for scripts and smoke checks."""

        return asyncio.run(self.query(*args, **kwargs))

    def _build_command(
        self,
        *,
        query: str,
        method: str,
        root: Path,
        data: Path | None,
        response_type: str | None,
    ) -> list[str]:
        command = [
            self.config.cli_path,
            "query",
            "--root",
            str(root),
            "--method",
            method,
            "--query",
            query,
        ]
        if data is not None:
            command.extend(["--data", str(data)])
        if response_type:
            command.extend(["--response-type", response_type])
        return command

    @staticmethod
    def _format_command(command: list[str]) -> str:
        return shlex.join(command)


def clean_graphrag_stdout(stdout: str) -> str:
    """Remove CLI log preamble and return the response body when possible."""

    text = stdout.strip()
    if not text:
        return ""

    marker_match = re.search(r"SUCCESS:\s+.+?Response:\s*", text, flags=re.IGNORECASE)
    if marker_match:
        return text[marker_match.end() :].strip()

    lines = []
    skip_info_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("INFO: Vector Store Args:"):
            skip_info_block = True
            continue
        if skip_info_block:
            if stripped == "}":
                skip_info_block = False
            continue
        if stripped.startswith("INFO:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()

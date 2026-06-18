"""Configuration for the GraphRAG CLI wrapper."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class GraphRAGCLIConfig:
    """Runtime options for invoking `graphrag query`."""

    cli_path: str = str(PROJECT_ROOT / ".venv" / "bin" / "graphrag")
    workspace_root: Path = PROJECT_ROOT / "llm_backend" / "app" / "graphrag_workspaces" / "ragtest"
    default_method: str = "local"
    response_type: str | None = None
    timeout_seconds: float = 180.0

    @classmethod
    def from_env(cls) -> "GraphRAGCLIConfig":
        """Build config from environment variables with local defaults."""

        response_type = os.getenv("GRAPHRAG_CLI_RESPONSE_TYPE")
        timeout = os.getenv("GRAPHRAG_CLI_TIMEOUT_SECONDS")
        return cls(
            cli_path=os.getenv("GRAPHRAG_CLI_PATH", cls.cli_path),
            workspace_root=Path(
                os.getenv("GRAPHRAG_CLI_WORKSPACE_ROOT", str(cls.workspace_root))
            ),
            default_method=os.getenv("GRAPHRAG_CLI_DEFAULT_METHOD", cls.default_method),
            response_type=response_type or cls.response_type,
            timeout_seconds=float(timeout) if timeout else cls.timeout_seconds,
        )

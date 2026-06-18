from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.core.config import settings
from app.rag_ingest.milvus_store import MilvusVectorStore


@dataclass(frozen=True)
class MilvusRetrieverConfig:
    top_k: int = settings.MILVUS_SEARCH_TOP_K
    score_threshold: float = settings.MILVUS_SEARCH_SCORE_THRESHOLD
    ranker_type: str = "rrf"
    rrf_k: int = settings.MILVUS_RRF_K
    filter_category: str = settings.MILVUS_FILTER_CATEGORY


class MilvusHybridRetriever:
    """LangChain Document retriever for Milvus dense+sparse hybrid search."""

    def __init__(
        self,
        *,
        store: Optional[MilvusVectorStore] = None,
        config: Optional[MilvusRetrieverConfig] = None,
    ) -> None:
        self.store = store or MilvusVectorStore()
        self.config = config or MilvusRetrieverConfig()
        self._retriever = None

    def as_retriever(self):
        if self._retriever is None:
            vector_store = self.store.vector_store or self.store.create_connection()
            search_kwargs = {
                "k": self.config.top_k,
                "score_threshold": self.config.score_threshold,
                "ranker_type": self.config.ranker_type,
                "ranker_params": {"k": self.config.rrf_k},
            }
            if self.config.filter_category:
                category = self.config.filter_category.replace("\\", "\\\\").replace('"', '\\"')
                search_kwargs["expr"] = f'category == "{category}"'

            self._retriever = vector_store.as_retriever(
                search_type="similarity",
                search_kwargs=search_kwargs,
            )
        return self._retriever

    def search(self, query: str) -> List:
        """Return LangChain Document results from hybrid Milvus retrieval."""

        return list(self.as_retriever().invoke(query))

    def create_tool(
        self,
        *,
        name: str = "milvus_hybrid_retriever",
        description: str = "搜索并返回 Markdown 技术知识库中的相关文档块证据。",
    ):
        try:
            from langchain_core.tools import create_retriever_tool
        except ImportError as exc:
            raise RuntimeError("langchain_core is required to create retriever tools.") from exc

        return create_retriever_tool(self.as_retriever(), name, description)

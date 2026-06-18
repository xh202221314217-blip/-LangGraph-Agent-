"""Runtime fusion for GraphRAG CLI and Milvus hybrid RAG retrieval."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document

from app.core.logger import get_logger
from app.graphrag_cli import GraphRAGCLIError, GraphRAGCLIRetriever
from app.rag_retrieval import MilvusHybridRetriever


logger = get_logger(service="knowledge_fusion")


@dataclass(frozen=True)
class MilvusDocumentEvidence:
    """A compact, serializable view of a LangChain document result."""

    index: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeFusionResult:
    """Combined retrieval result used by the LangGraph answer node."""

    question: str
    graphrag_text: str = ""
    milvus_documents: list[MilvusDocumentEvidence] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return bool(self.graphrag_text.strip() or self.milvus_documents)

    def to_context(self) -> str:
        """Format retrieval results as a grounded context block for the LLM."""

        sections: list[str] = []
        if self.graphrag_text.strip():
            sections.append(
                "## GraphRAG CLI 结果\n"
                f"{self.graphrag_text.strip()}"
            )

        if self.milvus_documents:
            doc_lines = ["## Milvus hybrid RAG 文档块证据"]
            for doc in self.milvus_documents:
                source = _format_source(doc.metadata)
                doc_lines.append(
                    f"[M{doc.index}] {source}\n{doc.content.strip()}"
                )
            sections.append("\n\n".join(doc_lines))

        if self.errors:
            sections.append("## 检索错误\n" + "\n".join(f"- {err}" for err in self.errors))

        if not sections:
            return "未检索到可用上下文。"
        return "\n\n".join(sections)


class HybridKnowledgeRetriever:
    """Run GraphRAG and Milvus retrieval concurrently and merge their evidence."""

    def __init__(
        self,
        *,
        graphrag_retriever: GraphRAGCLIRetriever | None = None,
        milvus_retriever: MilvusHybridRetriever | None = None,
        milvus_content_limit: int = 1600,
    ) -> None:
        self.graphrag_retriever = graphrag_retriever or GraphRAGCLIRetriever()
        self.milvus_retriever = milvus_retriever or MilvusHybridRetriever()
        self.milvus_content_limit = milvus_content_limit

    async def retrieve(self, question: str) -> KnowledgeFusionResult:
        """Retrieve from both backends. One backend may fail without aborting the other."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        graphrag_task = asyncio.create_task(self._query_graphrag(normalized_question))
        milvus_task = asyncio.create_task(self._query_milvus(normalized_question))

        graphrag_result, milvus_result = await asyncio.gather(
            graphrag_task,
            milvus_task,
            return_exceptions=True,
        )

        errors: list[str] = []
        graphrag_text = ""
        milvus_documents: list[MilvusDocumentEvidence] = []

        if isinstance(graphrag_result, Exception):
            logger.warning(f"GraphRAG retrieval failed: {graphrag_result}")
            errors.append(f"GraphRAG CLI 检索失败：{graphrag_result}")
        else:
            graphrag_text = graphrag_result.strip()

        if isinstance(milvus_result, Exception):
            logger.warning(f"Milvus hybrid retrieval failed: {milvus_result}")
            errors.append(f"Milvus hybrid RAG 检索失败：{milvus_result}")
        else:
            milvus_documents = self._compact_documents(milvus_result)

        return KnowledgeFusionResult(
            question=normalized_question,
            graphrag_text=graphrag_text,
            milvus_documents=milvus_documents,
            errors=errors,
        )

    async def _query_graphrag(self, question: str) -> str:
        result = await self.graphrag_retriever.query(question)
        return result.text

    async def _query_milvus(self, question: str) -> list[Document]:
        return await asyncio.to_thread(self.milvus_retriever.search, question)

    def _compact_documents(self, documents: list[Document]) -> list[MilvusDocumentEvidence]:
        compacted: list[MilvusDocumentEvidence] = []
        for index, document in enumerate(documents, start=1):
            content = (document.page_content or "").strip()
            if not content:
                continue
            if len(content) > self.milvus_content_limit:
                content = content[: self.milvus_content_limit].rstrip() + "\n..."
            compacted.append(
                MilvusDocumentEvidence(
                    index=index,
                    content=content,
                    metadata=dict(document.metadata or {}),
                )
            )
        return compacted


def _format_source(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "source=unknown"

    source_keys = ("source", "file_path", "filename", "title", "pk", "id")
    parts = []
    for key in source_keys:
        value = metadata.get(key)
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "source=metadata"

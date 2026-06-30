import asyncio

from langchain_core.documents import Document

from app.lg_agent.knowledge_fusion import HybridKnowledgeRetriever


class FakeMilvus:
    def search(self, question):
        return [Document(page_content="milvus ok", metadata={"source": "test"})]


def test_graphrag_disabled_uses_only_milvus():
    async def run():
        retriever = HybridKnowledgeRetriever(
            use_graphrag=False,
            milvus_retriever=FakeMilvus(),
        )
        result = await retriever.retrieve("test question")
        assert result.graphrag_text == ""
        assert len(result.milvus_documents) == 1
        assert "GraphRAG CLI 结果" not in result.to_context()

    asyncio.run(run())

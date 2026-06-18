from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

from app.core.config import settings


def create_embedding_function(provider: Optional[str] = None):
    """Create the dense embedding function used by Milvus."""

    provider = (provider or settings.RAG_EMBEDDING_PROVIDER).lower()

    if provider == "huggingface":
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError as exc:
            raise RuntimeError(
                "langchain_huggingface is required for RAG_EMBEDDING_PROVIDER=huggingface."
            ) from exc

        return HuggingFaceEmbeddings(
            model_name=settings.RAG_EMBEDDING_MODEL,
            model_kwargs={"device": settings.RAG_EMBEDDING_DEVICE},
            encode_kwargs={"normalize_embeddings": settings.RAG_EMBEDDING_NORMALIZE},
        )

    if provider == "openai":
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:
            raise RuntimeError(
                "langchain_openai is required for RAG_EMBEDDING_PROVIDER=openai."
            ) from exc

        api_key = (
            settings.RAG_OPENAI_EMBEDDING_API_KEY
            or settings.EMBEDDING_API_KEY
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            raise RuntimeError(
                "RAG_OPENAI_EMBEDDING_API_KEY, EMBEDDING_API_KEY, DASHSCOPE_API_KEY, "
                "or OPENAI_API_KEY is required for "
                "RAG_EMBEDDING_PROVIDER=openai."
            )
        return OpenAIEmbeddings(
            model=settings.RAG_OPENAI_EMBEDDING_MODEL,
            api_key=api_key,
            base_url=settings.RAG_OPENAI_EMBEDDING_BASE_URL,
            chunk_size=settings.EMBEDDING_BATCH_SIZE,
            check_embedding_ctx_length=False,
        )

    raise ValueError(f"Unsupported RAG_EMBEDDING_PROVIDER: {provider}")


@dataclass(frozen=True)
class MilvusStoreConfig:
    uri: str = settings.MILVUS_URI
    collection_name: str = settings.MILVUS_COLLECTION_NAME
    dense_dimension: int = settings.MILVUS_DENSE_DIMENSION
    text_max_length: int = settings.MILVUS_TEXT_MAX_LENGTH
    consistency_level: str = settings.MILVUS_CONSISTENCY_LEVEL


class MilvusVectorStore:
    """Create and write the dense+sparse hybrid Milvus collection."""

    metadata_fields = (
        "category",
        "source",
        "filename",
        "filetype",
        "title",
        "category_depth",
    )

    def __init__(
        self,
        config: Optional[MilvusStoreConfig] = None,
        embedding_function=None,
    ) -> None:
        self.config = config or MilvusStoreConfig()
        self.embedding_function = embedding_function
        self.vector_store = None

    def create_collection(self, *, drop_existing: bool = False) -> None:
        try:
            from pymilvus import Function, IndexType, MilvusClient
            from pymilvus.client.types import DataType, FunctionType, MetricType
        except ImportError as exc:
            raise RuntimeError(
                "pymilvus is required to create the Milvus collection."
            ) from exc

        client = MilvusClient(uri=self.config.uri)
        if self.config.collection_name in client.list_collections():
            if not drop_existing:
                return
            self._drop_collection(client)

        schema = client.create_schema()
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(
            field_name="text",
            datatype=DataType.VARCHAR,
            max_length=self.config.text_max_length,
            enable_analyzer=True,
            analyzer_params={"tokenizer": "jieba", "filter": ["cnalphanumonly"]},
        )
        schema.add_field(field_name="category", datatype=DataType.VARCHAR, max_length=1000)
        schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=1000)
        schema.add_field(field_name="filename", datatype=DataType.VARCHAR, max_length=1000)
        schema.add_field(field_name="filetype", datatype=DataType.VARCHAR, max_length=1000)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=1000)
        schema.add_field(field_name="category_depth", datatype=DataType.INT64)
        schema.add_field(field_name="sparse", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(
            field_name="dense",
            datatype=DataType.FLOAT_VECTOR,
            dim=self.config.dense_dimension,
        )

        schema.add_function(
            Function(
                name="text_bm25_emb",
                input_field_names=["text"],
                output_field_names=["sparse"],
                function_type=FunctionType.BM25,
            )
        )

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="sparse",
            index_name="sparse_inverted_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                "bm25_k1": 1.2,
                "bm25_b": 0.75,
            },
        )
        index_params.add_index(
            field_name="dense",
            index_name="dense_inverted_index",
            index_type=IndexType.HNSW,
            metric_type=MetricType.IP,
            params={"M": 16, "efConstruction": 64},
        )
        client.create_collection(
            collection_name=self.config.collection_name,
            schema=schema,
            index_params=index_params,
        )

    def create_connection(self):
        try:
            from langchain_milvus import BM25BuiltInFunction, Milvus
        except ImportError as exc:
            raise RuntimeError(
                "langchain_milvus is required to connect to Milvus."
            ) from exc

        self.vector_store = Milvus(
            embedding_function=self.embedding_function or create_embedding_function(),
            collection_name=self.config.collection_name,
            builtin_function=BM25BuiltInFunction(),
            vector_field=["dense", "sparse"],
            primary_field="id",
            text_field="text",
            consistency_level=self.config.consistency_level,
            auto_id=True,
            connection_args={"uri": self.config.uri},
        )
        return self.vector_store

    def add_documents(self, documents: Iterable) -> List[str]:
        if self.vector_store is None:
            self.create_connection()
        prepared_documents = [self._prepare_document(document) for document in documents]
        if not prepared_documents:
            return []
        ids = self.vector_store.add_documents(prepared_documents)
        collection = getattr(self.vector_store, "col", None)
        if collection is not None:
            try:
                collection.flush()
            except Exception:
                pass
        return ids

    def _drop_collection(self, client) -> None:
        try:
            client.release_collection(collection_name=self.config.collection_name)
        except Exception:
            pass
        for index_name in client.list_indexes(collection_name=self.config.collection_name):
            client.drop_index(
                collection_name=self.config.collection_name,
                index_name=index_name,
            )
        client.drop_collection(collection_name=self.config.collection_name)

    def _prepare_document(self, document):
        from langchain_core.documents import Document

        metadata = dict(document.metadata or {})
        for field in self.metadata_fields:
            metadata.setdefault(field, 0 if field == "category_depth" else "")
        metadata["category_depth"] = int(metadata.get("category_depth") or 0)

        for field in self.metadata_fields:
            if field != "category_depth":
                metadata[field] = str(metadata.get(field) or "")[:1000]

        return Document(
            page_content=(document.page_content or "")[: self.config.text_max_length],
            metadata=metadata,
        )

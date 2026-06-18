from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List

from app.core.logger import logger
from app.rag_ingest.milvus_store import create_embedding_function


class MarkdownParser:
    """Parse Markdown files into LangChain Documents for Milvus indexing."""

    def __init__(
        self,
        *,
        enable_semantic_chunking: bool = True,
        semantic_chunk_threshold: int = 5000,
        embedding_function=None,
    ) -> None:
        self.enable_semantic_chunking = enable_semantic_chunking
        self.semantic_chunk_threshold = semantic_chunk_threshold
        self.embedding_function = embedding_function
        self._text_splitter = None

    @property
    def text_splitter(self):
        if not self.enable_semantic_chunking:
            return None
        if self._text_splitter is None:
            try:
                from langchain_experimental.text_splitter import SemanticChunker
            except ImportError as exc:
                raise RuntimeError(
                    "langchain_experimental is required for semantic chunking. "
                    "Install requirements or pass enable_semantic_chunking=False."
                ) from exc

            embedding = self.embedding_function or create_embedding_function()
            self._text_splitter = SemanticChunker(
                embedding,
                breakpoint_threshold_type="percentile",
                sentence_split_regex=r"(?<=[。！？.!?])",
            )
        return self._text_splitter

    def parse_markdown_to_documents(self, md_file: str | Path):
        raw_documents = self.parse_markdown(md_file)
        logger.info(f"Markdown parsed: file={md_file}, elements={len(raw_documents)}")

        merged_documents = self.merge_title_content(raw_documents)
        logger.info(f"Markdown merged: file={md_file}, documents={len(merged_documents)}")

        chunk_documents = self.text_chunker(merged_documents)
        logger.info(f"Markdown chunked: file={md_file}, documents={len(chunk_documents)}")
        return chunk_documents

    def parse_markdown(self, md_file: str | Path):
        md_path = Path(md_file)
        if not md_path.is_file():
            raise FileNotFoundError(f"Markdown file does not exist: {md_path}")

        try:
            from langchain_community.document_loaders import UnstructuredMarkdownLoader
        except ImportError as exc:
            raise RuntimeError(
                "langchain_community and unstructured are required to parse Markdown files. "
                "Install requirements before running Milvus ingest."
            ) from exc

        loader = UnstructuredMarkdownLoader(
            file_path=str(md_path),
            mode="elements",
            strategy="fast",
        )
        try:
            return list(loader.lazy_load())
        except Exception as exc:
            logger.warning(
                f"Unstructured Markdown parsing failed for {md_path}; "
                f"falling back to plain Markdown parser: {exc}"
            )
            return self._parse_markdown_plain(md_path)

    def merge_title_content(self, documents: Iterable):
        merged_documents = []
        parent_documents = {}

        for document in documents:
            metadata = dict(document.metadata or {})
            metadata.pop("languages", None)
            document.metadata = metadata

            parent_id = metadata.get("parent_id")
            category = metadata.get("category")
            element_id = metadata.get("element_id")

            self._normalize_metadata(document)

            if category == "NarrativeText" and parent_id is None:
                merged_documents.append(document)
                continue

            if category == "Title":
                document.metadata["title"] = document.page_content
                if parent_id in parent_documents:
                    parent = parent_documents[parent_id]
                    document.page_content = f"{parent.page_content} -> {document.page_content}"
                if element_id:
                    parent_documents[element_id] = document
                else:
                    merged_documents.append(document)
                continue

            if parent_id and parent_id in parent_documents:
                parent = parent_documents[parent_id]
                parent.page_content = f"{parent.page_content} {document.page_content}"
                parent.metadata["category"] = "content"
            else:
                merged_documents.append(document)

        merged_documents.extend(parent_documents.values())
        for document in merged_documents:
            self._normalize_metadata(document)
        return merged_documents

    def text_chunker(self, documents: List):
        if not self.enable_semantic_chunking:
            return documents

        splitter = self.text_splitter
        chunked_documents = []
        for document in documents:
            if len(document.page_content) > self.semantic_chunk_threshold:
                chunked_documents.extend(splitter.split_documents([document]))
            else:
                chunked_documents.append(document)
        for document in chunked_documents:
            self._normalize_metadata(document)
        return chunked_documents

    @staticmethod
    def _normalize_metadata(document) -> None:
        metadata = dict(document.metadata or {})
        source = metadata.get("source") or metadata.get("filename") or ""
        filename = metadata.get("filename") or (Path(source).name if source else "")

        category_depth = metadata.get("category_depth", 0)
        try:
            category_depth = int(category_depth or 0)
        except (TypeError, ValueError):
            category_depth = 0

        metadata.update(
            {
                "category": str(metadata.get("category") or ""),
                "source": str(source),
                "filename": str(filename),
                "filetype": str(metadata.get("filetype") or Path(filename).suffix or ".md"),
                "title": str(metadata.get("title") or ""),
                "category_depth": category_depth,
            }
        )
        document.metadata = metadata

    @staticmethod
    def _parse_markdown_plain(md_file: Path):
        from langchain_core.documents import Document

        text = md_file.read_text(encoding="utf-8")
        sections = []
        current_title = ""
        current_depth = 0
        current_lines = []

        def flush() -> None:
            content = "\n".join(line for line in current_lines).strip()
            if not content and not current_title:
                return
            page_content = content or current_title
            sections.append(
                Document(
                    page_content=page_content,
                    metadata={
                        "category": "content",
                        "source": str(md_file),
                        "filename": md_file.name,
                        "filetype": md_file.suffix or ".md",
                        "title": current_title,
                        "category_depth": current_depth,
                    },
                )
            )

        for line in text.splitlines():
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading:
                flush()
                current_title = heading.group(2).strip()
                current_depth = len(heading.group(1))
                current_lines = [current_title]
            else:
                current_lines.append(line)

        flush()
        if not sections and text.strip():
            sections.append(
                Document(
                    page_content=text.strip(),
                    metadata={
                        "category": "content",
                        "source": str(md_file),
                        "filename": md_file.name,
                        "filetype": md_file.suffix or ".md",
                        "title": "",
                        "category_depth": 0,
                    },
                )
            )
        return sections

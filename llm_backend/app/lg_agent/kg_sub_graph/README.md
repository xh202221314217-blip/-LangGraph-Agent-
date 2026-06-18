# Legacy Neo4j KG Modules

This directory is retained for historical reference only.

The active first-version Markdown knowledge path does not import or call these modules. Runtime knowledge questions are handled by:

- `llm_backend/app/lg_agent/lg_builder.py`
- `llm_backend/app/lg_agent/knowledge_fusion.py`
- `llm_backend/app/graphrag_cli`
- `llm_backend/app/rag_retrieval`

Do not wire `kg_sub_graph`, text2cypher, predefined Cypher, or Neo4j workflows into the active application unless Neo4j support is explicitly reopened as a new phase.

# GraphRAG Parquet 到 Neo4j 快速查询需求文档

## 1. 背景与目标

当前知识库查询主链路通过 `graphrag query` CLI 访问 GraphRAG 本地索引。该方式能用，但每次查询都有 CLI 启动、配置加载、索引读取和 LLM 查询流程开销，交互速度偏慢。

本需求的目标是新增一条更快的结构化图查询链路：

```text
GraphRAG index 输出 parquet
-> 导入 Neo4j 节点/属性/关系
-> 用户问题 text2cypher
-> 执行 Cypher
-> 成功则把节点、关系、文本证据返回给 LLM
-> 失败则把失败信息返回给 LLM，由 LLM 走降级回答
```

该链路只解决“GraphRAG CLI 查询慢”的运行时问题，不替代 GraphRAG index。GraphRAG 仍负责从 Markdown 构建 parquet/lancedb 等索引产物。

## 2. 非目标

- 不重写 GraphRAG index。
- 不接入旧电商 Neo4j schema、旧 Northwind 示例或旧智能家居 prompt。
- 不做 Cypher 自动修复重试，第一版失败即返回错误。
- 不做复杂图谱本体设计，先按 GraphRAG parquet 字段落库。
- 不新增 Neo4j 之外的图数据库。

## 3. 当前可复用基础

- GraphRAG 工作区示例：`llm_backend/app/graphrag_workspaces/ragtest`
- 当前 parquet 目录：`llm_backend/app/graphrag_workspaces/ragtest/output`
- 当前融合节点：`llm_backend/app/lg_agent/knowledge_fusion.py`
- GraphRAG CLI wrapper：`llm_backend/app/graphrag_cli`
- Neo4j docker 服务已保留在 `docker-compose.yml`，默认认证为 `neo4j/12345678`
- 依赖中已有 `langchain_neo4j==0.4.0`

后续智能体实现时优先复用以上内容。只有 `pandas/pyarrow/neo4j` 缺失时才补依赖；不要引入新的图抽象框架。

## 4. 数据源与字段

第一版只读取 GraphRAG index 输出的 6 个 parquet：

```text
entities.parquet
relationships.parquet
text_units.parquet
documents.parquet
communities.parquet
community_reports.parquet
```

已知字段：

```text
entities: id, human_readable_id, title, type, text_unit_ids, frequency, degree, description
relationships: id, human_readable_id, source, target, weight, combined_degree, text_unit_ids, description
text_units: id, human_readable_id, text, n_tokens, document_ids, entity_ids, relationship_ids
documents: id, human_readable_id, title, text, text_unit_ids, creation_date
communities: id, human_readable_id, community, level, parent, children, title, entity_ids, relationship_ids, text_unit_ids
community_reports: id, human_readable_id, community, level, title, summary, full_content, rank, rating_explanation
```

实现时必须容忍字段缺失：用 `df.get("column")` 或等价逻辑读取，缺失字段写 `null` 或空列表。

## 5. Neo4j 图模型

第一版使用固定标签和固定关系类型，避免动态 label/type 带来的 Cypher 注入和 schema 膨胀。

### 5.1 节点

```text
(:Entity {
  id,
  human_readable_id,
  title,
  entity_type,
  description,
  frequency,
  degree,
  text_unit_ids
})

(:TextUnit {
  id,
  human_readable_id,
  text,
  n_tokens,
  document_ids,
  entity_ids,
  relationship_ids
})

(:Document {
  id,
  human_readable_id,
  title,
  text,
  text_unit_ids,
  creation_date
})

(:Community {
  id,
  human_readable_id,
  community,
  level,
  parent,
  children,
  title,
  entity_ids,
  relationship_ids,
  text_unit_ids
})

(:CommunityReport {
  id,
  human_readable_id,
  community,
  level,
  title,
  summary,
  full_content,
  rank,
  rating_explanation
})
```

### 5.2 关系

```text
(:Entity)-[:RELATED_TO {
  id,
  human_readable_id,
  weight,
  combined_degree,
  text_unit_ids,
  description
}]->(:Entity)

(:Entity)-[:MENTIONED_IN]->(:TextUnit)
(:TextUnit)-[:PART_OF]->(:Document)
(:Community)-[:HAS_ENTITY]->(:Entity)
(:Community)-[:HAS_TEXT_UNIT]->(:TextUnit)
(:Community)-[:HAS_RELATIONSHIP]->(:Entity)  # ponytail: 第一版只连到相关实体，后续如需关系节点再拆 Relationship 节点
(:Community)-[:HAS_REPORT]->(:CommunityReport)
(:Community)-[:PARENT_OF]->(:Community)
```

注意：`relationships.parquet.source/target` 通常对应实体 title，而不是实体 id。导入时应优先按 `Entity.title` 匹配 source/target；如果未来确认字段变化，再增加 id 匹配兜底。

## 6. 导入流程

新增模块建议：

```text
llm_backend/app/graphrag_neo4j/
  __init__.py
  config.py
  importer.py
  query.py
  smoke.py
```

### 6.1 配置

通过环境变量读取：

```text
GRAPHRAG_NEO4J_URI=bolt://localhost:7687
GRAPHRAG_NEO4J_USER=neo4j
GRAPHRAG_NEO4J_PASSWORD=12345678
GRAPHRAG_NEO4J_DATABASE=neo4j
GRAPHRAG_NEO4J_OUTPUT_DIR=llm_backend/app/graphrag_workspaces/ragtest/output
GRAPHRAG_NEO4J_QUERY_TIMEOUT_SECONDS=20
```

### 6.2 导入命令

提供 CLI：

```bash
PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_neo4j.importer \
  --output-dir llm_backend/app/graphrag_workspaces/ragtest/output \
  --clear
```

`--clear` 只删除本导入器创建的标签数据：

```cypher
MATCH (n)
WHERE n:Entity OR n:TextUnit OR n:Document OR n:Community OR n:CommunityReport
DETACH DELETE n
```

不要清空整库中未知标签，避免误删旧数据。

### 6.3 约束与索引

导入前创建：

```cypher
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT text_unit_id IF NOT EXISTS FOR (n:TextUnit) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT community_id IF NOT EXISTS FOR (n:Community) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT report_id IF NOT EXISTS FOR (n:CommunityReport) REQUIRE n.id IS UNIQUE;
CREATE INDEX entity_title IF NOT EXISTS FOR (n:Entity) ON (n.title);
CREATE FULLTEXT INDEX entity_text IF NOT EXISTS FOR (n:Entity) ON EACH [n.title, n.description];
CREATE FULLTEXT INDEX text_unit_text IF NOT EXISTS FOR (n:TextUnit) ON EACH [n.text];
```

社区版 Neo4j 不支持多数据库管理时，使用默认 `neo4j` database。

### 6.4 写入方式

- 用 `pandas.read_parquet` 读取 parquet。
- 将 `NaN` 转为 `None`。
- 将 numpy 类型转为 Python 原生类型。
- list 字段保持 list；字符串化 list 只作为最后兜底。
- 每类节点用 `UNWIND $rows AS row MERGE ... SET n += row` 批量写入。
- 批大小默认 500，可通过参数覆盖。
- `RELATED_TO` 关系使用 `MERGE (s:Entity {title: row.source})` 不允许创建空壳实体；必须 `MATCH` 到 source 和 target 才写关系。未匹配的关系记录到日志和导入结果。

导入结果返回：

```json
{
  "status": "success",
  "nodes": {
    "Entity": 123,
    "TextUnit": 456
  },
  "relationships": {
    "RELATED_TO": 789,
    "MENTIONED_IN": 100
  },
  "skipped": {
    "RELATED_TO_unmatched_entity": 3
  }
}
```

## 7. text2cypher 查询流程

新增 `GraphRAGNeo4jRetriever`，对外提供：

```python
async def query(self, question: str) -> GraphRAGNeo4jResult:
    ...
```

返回对象包含：

```python
text: str                 # 给 LLM 的结构化上下文或错误信息
cypher: str | None
rows: list[dict]
success: bool
error: str | None
elapsed_seconds: float
```

### 7.1 Cypher 生成 prompt

LLM 只允许生成只读 Cypher：

```text
你是 Neo4j Cypher 生成器。根据用户问题生成一个只读 Cypher 查询。
只能使用以下标签、关系、属性：

标签：
Entity(id, title, entity_type, description, frequency, degree)
TextUnit(id, text, n_tokens)
Document(id, title, text)
Community(id, title, level)
CommunityReport(id, title, summary, full_content, rank)

关系：
(Entity)-[:RELATED_TO]->(Entity)
(Entity)-[:MENTIONED_IN]->(TextUnit)
(TextUnit)-[:PART_OF]->(Document)
(Community)-[:HAS_ENTITY]->(Entity)
(Community)-[:HAS_TEXT_UNIT]->(TextUnit)
(Community)-[:HAS_REPORT]->(CommunityReport)
(Community)-[:PARENT_OF]->(Community)

规则：
1. 只返回 Cypher，不要解释。
2. 必须是 MATCH/CALL db.index.fulltext.queryNodes 开头的只读查询。
3. 禁止 CREATE、MERGE、SET、DELETE、DROP、CALL apoc、LOAD CSV。
4. 必须 LIMIT 20 以内。
5. 对中文关键词优先使用 fulltext index。
```

### 7.2 Cypher 安全校验

执行前必须做最小安全校验：

- 去掉 markdown code fence。
- 只允许单条语句。
- 必须以 `MATCH` 或 `CALL db.index.fulltext.queryNodes` 开头。
- 禁止关键词：`CREATE`, `MERGE`, `SET`, `DELETE`, `DETACH`, `DROP`, `REMOVE`, `LOAD`, `APOC`, `CALL apoc`, `CREATE INDEX`, `CREATE CONSTRAINT`
- 必须包含 `LIMIT`，且 limit <= 20；没有则追加 `LIMIT 10`。

校验失败时不要执行，直接返回失败结果给 LLM。

### 7.3 查询成功输出

查询成功后，把 rows 格式化成短上下文：

```text
Neo4j 图查询成功。
Cypher:
MATCH ...

结果:
1. Entity: GAAFET
   description: ...
   related: FinFET, nanosheet
   evidence: text unit 摘要...
```

上下文最长控制在 6000 字符。超出时截断每个字段，不再追加总结 LLM 调用。

### 7.4 查询失败输出

任何失败都返回给 LLM，不抛到主流程外：

```text
Neo4j 图查询失败。
原因: Cypher 安全校验失败: 包含 DELETE
Cypher: ...

请不要臆造图查询结果；可改用 GraphRAG CLI 或 Milvus 证据回答。
```

失败类型至少包括：

- `text2cypher_failed`
- `cypher_validation_failed`
- `neo4j_connection_failed`
- `cypher_execution_failed`
- `empty_result`

`empty_result` 也算失败，因为没有节点信息可提供。

## 8. 接入主流程

第一版接入 `llm_backend/app/lg_agent/knowledge_fusion.py`，不要重启旧 `kg_sub_graph`。

推荐顺序：

1. 同时启动 Neo4j 查询和现有 Milvus 查询。
2. Neo4j 成功时，把 Neo4j 上下文放在 GraphRAG CLI 结果位置之前。
3. Neo4j 失败时，把失败信息放入“检索错误”段。
4. 现有 GraphRAG CLI 查询可以保留为兜底，但建议通过环境变量控制：

```text
RAG_USE_NEO4J_FAST_QUERY=true
RAG_USE_GRAPHRAG_CLI_FALLBACK=true
```

推荐运行时策略：

```text
Neo4j 成功 -> Neo4j + Milvus -> LLM
Neo4j 失败且 fallback=true -> GraphRAG CLI + Milvus -> LLM，并附带 Neo4j 失败原因
Neo4j 失败且 fallback=false -> Milvus + 失败原因 -> LLM
```

## 9. 验收标准

### 9.1 导入验收

运行：

```bash
docker compose --env-file llm_backend/.env --profile legacy-neo4j up -d neo4j

PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_neo4j.importer \
  --output-dir llm_backend/app/graphrag_workspaces/ragtest/output \
  --clear
```

应满足：

- 命令返回 `status=success`
- Neo4j 中存在 `Entity/TextUnit/Document/Community/CommunityReport`
- `RELATED_TO`、`MENTIONED_IN`、`PART_OF` 至少有一种关系存在
- 重复运行不会创建重复节点

### 9.2 查询验收

运行：

```bash
PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_neo4j.smoke \
  --query "GAAFET 相比 FinFET 的关键优势是什么？"
```

应满足：

- 能生成只读 Cypher
- 能从 Neo4j 返回实体或文本节点信息
- 总耗时明显低于 `graphrag query --method local` 的冷启动耗时
- Cypher 执行失败时返回结构化错误，不中断程序

### 9.3 主流程验收

调用：

```bash
curl -N -X POST http://localhost:8000/api/langgraph/query \
  -F 'query=GAAFET 相比 FinFET 的关键优势是什么？' \
  -F 'user_id=1'
```

应满足：

- 回答上下文中优先使用 Neo4j 图查询结果。
- Neo4j 查询失败时，最终回答明确知道图查询失败，不把失败结果当证据。
- Milvus 仍可作为文档块证据来源。
- 不重新引入旧电商/智能家居 KG prompt。

## 10. 最小测试要求

新增一个不依赖外部 LLM 的本地测试或 smoke：

```text
llm_backend/app/graphrag_neo4j/smoke.py
```

它至少验证：

- parquet 目录存在且能读取。
- Cypher 安全校验能拦截 `DELETE`。
- `MATCH (n) RETURN n LIMIT 1` 类型只读查询能通过校验。
- Neo4j 可连接时能执行一次 `RETURN 1 AS ok`。

如果要测试 text2cypher，需要真实 LLM key，放到可选 smoke，不阻塞本地快速检查。

## 11. 实施顺序

1. 新增 `graphrag_neo4j/config.py`，读取 Neo4j 与 parquet 配置。
2. 新增 `importer.py`，完成 parquet 读取、约束创建、节点和关系导入。
3. 新增 `query.py`，完成 text2cypher、Cypher 校验、Neo4j 执行、结果格式化。
4. 新增 `smoke.py`，验证导入前置、校验器和 Neo4j 连接。
5. 修改 `knowledge_fusion.py`，把 Neo4j 快速查询接入现有融合上下文。
6. 更新 `README.md`，只追加 Neo4j 快速查询命令，不改掉现有 GraphRAG CLI + Milvus 主说明。

## 12. 风险与处理

- GraphRAG parquet 字段可能随版本变化：导入器必须容忍缺列，并在日志中列出缺失字段。
- text2cypher 可能生成危险或错误 Cypher：执行前必须做只读校验，失败即返回错误。
- GraphRAG 关系 source/target 可能匹配不到实体：不要创建空壳实体，记录 skipped。
- Neo4j fulltext 中文分词效果有限：第一版接受；只有召回差被验证后再加中文分词插件。
- 查询结果可能太长：固定截断，不再额外调用 LLM 总结。

## 13. 完成定义

本需求完成时，应具备：

- 一个可重复运行的 parquet -> Neo4j 导入命令。
- 一个自然语言 -> Cypher -> Neo4j 查询 retriever。
- 一个失败不抛出、成功返回节点信息的结构化结果对象。
- 主知识库流程能优先使用 Neo4j 快速图查询，并保留 GraphRAG CLI 或 Milvus 兜底。
- 文档化的运行命令和 smoke 验证。

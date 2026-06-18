# GraphRAG CLI + Hybrid RAG 合并需求文档与执行计划

## 1. 文档目的

本文档用于指导多个模型接力完成项目合并。后续每个模型在开始工作前都应先阅读本文档，确认当前阶段、已完成内容、未完成内容和验收标准，再执行自己的任务。

目标是将两个本地项目合并成一个可运行的大项目：

- 宿主项目：`/home/aetherlens/projects/deepseek_agent`
- 传统 RAG 来源项目：`/home/aetherlens/projects/rag_project`

本文档同时承担三类作用：

- 需求文档：说明最终系统要做什么。
- 执行计划：把任务拆成多个阶段，每个阶段都有明确验收标准。
- 接力文档：记录当前进度、上下文、关键决策、阻塞点，方便后续模型继续工作。

## 2. 最新核心决策

已决策：**第一版放弃将 GraphRAG parquet 转移到 Neo4j。**

新的第一版方案：

- GraphRAG 只负责 index 和 query。
- 入库时使用 GraphRAG CLI：`graphrag index --root <workspace>`。
- 查询时使用 GraphRAG CLI：`graphrag query --method local|global|drift|basic --query "<question>" --root <workspace>`。
- GraphRAG CLI 直接读取 index 阶段生成的 parquet/lancedb 等本地索引产物。
- 不实现 Neo4j loader。
- 不设计 Neo4j schema。
- 不生成 Cypher。
- 不迁移实体/关系到 Neo4j。
- Milvus dense+sparse hybrid RAG 仍然保留，作为传统文档块召回链路。

该方案的目标是先用少量 Markdown 文档验证最小可行链路，避免过早引入 Neo4j、schema 设计、动态标签、关系分类和 text2cypher 等复杂度。

## 3. 项目背景

`deepseek_agent` 当前提供：

- FastAPI 后端，入口为 `llm_backend/main.py`。
- 静态前端，挂载目录为 `llm_backend/static/dist`。
- LangGraph 主流程，核心文件为 `llm_backend/app/lg_agent/lg_builder.py`。
- 原 Neo4j 知识图谱检索流程，目录为 `llm_backend/app/lg_agent/kg_sub_graph`。
- 本地 GraphRAG 包、配置和样例数据，目录为 `llm_backend/app/graphrag`。

`rag_project` 当前提供：

- Markdown 文档数据，主要位于 `/home/aetherlens/projects/rag_project/md/md`。
- Markdown 解析与切分逻辑，位于 `RAG_PROJECT/RAG_PROJECT/documents/markdown_parser.py`。
- Milvus dense+sparse 双向量 collection 创建逻辑，位于 `RAG_PROJECT/RAG_PROJECT/documents/milvus_db.py`。
- Markdown 到 Milvus 的入库脚本，位于 `RAG_PROJECT/RAG_PROJECT/documents/write_milvus.py`。
- Hybrid 检索器，位于 `RAG_PROJECT/RAG_PROJECT/tools/retriever_tools.py`。

新的合并方向：

- 不复用原电商 Neo4j 数据库和 schema。
- 不把 GraphRAG parquet 写入 Neo4j。
- 使用 `rag_project` 中的 Markdown 文档作为统一语料来源。
- GraphRAG 入库：Markdown -> `graphrag index` -> 本地 GraphRAG index 产物。
- GraphRAG 检索：用户问题 -> `graphrag query --method local|global|drift|basic` -> GraphRAG 答案或上下文。
- 传统 RAG 入库：Markdown -> unstructured 解析/切分 -> Milvus dense+sparse hybrid。
- 前端、FastAPI 主入口和 LangGraph 主流程继续以 `deepseek_agent` 为宿主。

## 4. 最终目标

最终系统应满足：

1. 用户仍通过现有前端和 FastAPI 接口提问。
2. LangGraph 意图识别继续作为统一入口。
3. 对知识库类问题，系统可以调用：
   - GraphRAG CLI 检索链路
   - Milvus dense+sparse hybrid 文档块召回链路
4. 后端融合 GraphRAG 结果和 Milvus 文档块结果，生成最终回答。
5. 入库流程可以从同一批 Markdown 文档构建 GraphRAG index 和 Milvus collection。
6. 原电商 KG schema、原智能家居业务提示词、原商品/订单/客户/供应商预定义 Cypher 不应出现在新主流程中。
7. Neo4j 不属于第一版目标；如后续需要图数据库可视化或 Cypher 查询，再作为增强项重新评估。

## 5. 目标架构

运行时查询流程：

1. 前端调用 `llm_backend/main.py` 中的 LangGraph SSE 接口。
2. `lg_builder.py` 中的 router 判断问题类型。
3. 知识库类问题进入合并检索流程。
4. 合并检索流程调用：
   - GraphRAG CLI retriever
   - Milvus hybrid retriever
5. fusion 节点整理 GraphRAG 结果和 Milvus 证据上下文。
6. LLM 基于融合上下文生成最终答案。

GraphRAG CLI retriever 第一版实现方式：

```bash
graphrag query \
  --root llm_backend/app/graphrag_workspaces/ragtest \
  --method local \
  --query "用户问题"
```

可选参数：

```bash
graphrag query \
  --root llm_backend/app/graphrag_workspaces/ragtest \
  --method global \
  --query "用户问题" \
  --response-type "Multiple Paragraphs"
```

也可以在需要时使用 `--data <output_dir>` 直接指定 GraphRAG index 输出目录。

入库流程：

1. 从 `/home/aetherlens/projects/rag_project/md/md` 选择 Markdown 文档。
2. GraphRAG 入库：
   - 创建 GraphRAG workspace。
   - 将 Markdown 文档转换或复制到 workspace input。
   - 运行 `graphrag index --root <workspace>`。
   - 保留 GraphRAG 输出的 parquet/lancedb 等本地索引产物。
3. Milvus 入库：
   - 复用 `rag_project` 的 Markdown 解析和切分逻辑。
   - 写入包含 dense 和 sparse 字段的 Milvus collection。
   - 保留 BM25 sparse 和 dense embedding 的 hybrid 检索能力。

## 6. GraphRAG CLI 查询策略

GraphRAG CLI 支持以下查询方法：

- `local`
- `global`
- `drift`
- `basic`

第一版推荐：

- 先固定使用 `local` 跑通端到端链路。
- 跑通后再增加 method 选择逻辑。

method 选择建议：

- `local`：适合具体实体、具体技术、局部事实、某个概念的上下文解释。
- `global`：适合整体总结、主题归纳、趋势分析、跨文档综合问题。
- `drift`：适合从具体实体出发扩展到相关主题和上下文的问题。
- `basic`：适合轻量文本检索或兜底查询。

第一版 GraphRAG retriever 可直接通过 Python `subprocess` 调用 CLI。后续如果 CLI 启动开销过大，再改为 GraphRAG Python API。

GraphRAG CLI 输出处理建议：

- 第一版可以把 CLI stdout 作为 GraphRAG 结果文本。
- 如果 CLI 输出中包含日志，需要 wrapper 做最小清洗，只保留回答正文。
- 如果需要流式体验，可先不对 GraphRAG 子过程做流式透传，而是等待结果返回后再进入融合生成。
- 后续如果需要证据级融合，应评估 GraphRAG Python API 是否能返回 context，而不是只返回最终答案。

## 7. 当前状态

最后更新时间：2026-06-17

已完成：

- 已检索 `deepseek_agent` 与 `rag_project` 的核心结构。
- 已确认 `deepseek_agent` 适合作为合并后的 FastAPI、前端、LangGraph 宿主项目。
- 已确认本地 GraphRAG CLI 支持：
  - `graphrag init`
  - `graphrag index --root ./ragtest`
  - `graphrag update`
  - `graphrag query`
- 已确认 `graphrag query` 支持：
  - `--method local|global|drift|basic`
  - `--query`
  - `--root`
  - `--data`
  - `--response-type`
  - `--streaming`
- 已确认当前样例 GraphRAG parquet 产物字段：
  - `entities.parquet`: `id`, `human_readable_id`, `title`, `type`, `text_unit_ids`, `frequency`, `degree`, `description`
  - `relationships.parquet`: `id`, `human_readable_id`, `source`, `target`, `weight`, `combined_degree`, `text_unit_ids`, `description`
  - `text_units.parquet`: `id`, `human_readable_id`, `text`, `n_tokens`, `document_ids`, `entity_ids`, `relationship_ids`
  - `documents.parquet`: `id`, `human_readable_id`, `title`, `text`, `text_unit_ids`, `creation_date`
  - `communities.parquet`: `id`, `human_readable_id`, `community`, `level`, `parent`, `children`, `title`, `entity_ids`, `relationship_ids`, `text_unit_ids`
  - `community_reports.parquet`: `id`, `human_readable_id`, `community`, `level`, `title`, `summary`, `full_content`, `rank`, `rating_explanation`
- 已确认 `rag_project` 中 Milvus collection 支持 dense 和 sparse 字段，使用 BM25 内置函数生成 sparse 字段，并使用 RRF 风格参数融合检索结果。
- 已创建本文档：`docs/merge_kg_rag_plan.md`。
- 已根据最新决策将主线改为 GraphRAG CLI 检索链路，Neo4j loader 已降级为非第一版目标。

未完成：

- 尚未实施任何代码合并。
- 尚未创建新的 GraphRAG test workspace。
- 尚未使用 `rag_project` Markdown 跑通新的 GraphRAG index。
- 尚未实现 GraphRAG CLI retriever wrapper。
- 尚未将 `rag_project` 的 Milvus 入库/检索代码迁移到 `deepseek_agent`。
- 尚未重写 router、tool selection、guardrails 等提示词。
- 尚未进行端到端入库与查询验证。

已知问题：

- `llm_backend/app/services/indexing_service.py` 中 `_get_config_file()` 引用了未定义的 `self.config_mapping`。在修复或替换前，不要依赖当前 `/api/upload` 的 GraphRAG 入库路径。
- 原 Neo4j KG 子图仍存在于代码中，但不应作为第一版合并主线。

## 8. 执行原则

- 以 `deepseek_agent` 作为唯一运行应用。
- 第一版不做 Neo4j 集成。
- 第一版不做 Cypher 生成。
- 第一版不实现 GraphRAG parquet 到 Neo4j loader。
- 优先新增模块，不要一开始大规模重写旧 KG 模块。
- 每个阶段都必须能独立验收。
- GraphRAG 入库和 Milvus 入库应分离，二者共享 Markdown 语料但写入不同存储。
- GraphRAG 查询第一版优先使用 CLI wrapper。
- 每个模型完成工作后，都必须更新本文档的“当前状态”或新增“阶段执行记录”。
- 如果某阶段未通过验收，不应继续推进后续阶段。

## 9. 阶段计划

### 阶段 0：基线验证

目标：

确认当前环境、命令、依赖和导入路径，为后续合并建立可复现基线。

任务：

1. 确认 `deepseek_agent` 的 Python 虚拟环境可用。
2. 确认 GraphRAG CLI 可从 `deepseek_agent/.venv` 运行。
3. 确认 `graphrag query --help` 可显示 `local|global|drift|basic`。
4. 确认 `rag_project` 中 Milvus 相关模块的导入路径和依赖状态。
5. 梳理必要环境变量。

验收标准：

- 执行 `cd /home/aetherlens/projects/deepseek_agent && .venv/bin/graphrag index --help` 能打印帮助信息。
- 执行 `cd /home/aetherlens/projects/deepseek_agent && .venv/bin/graphrag query --help` 能打印帮助信息，并包含 `local|global|drift|basic`。
- 执行 `cd /home/aetherlens/projects/rag_project && .venv/bin/python -c "from RAG_PROJECT.RAG_PROJECT.documents.milvus_db import MilvusVectorSave"` 成功，或把失败原因和修复方式记录到本文档。
- 本文档的“环境变量清单”被补充完整。
- 阶段 0 不改动应用行为。

### 阶段 1：GraphRAG 测试工作区与 CLI 查询验证

目标：

用少量 Markdown 文档跑通 GraphRAG index，并用 GraphRAG CLI 直接查询本地 index。

任务：

1. 创建测试工作区：`llm_backend/app/graphrag_workspaces/ragtest`。
2. 从 `/home/aetherlens/projects/rag_project/md/md` 复制 3 到 5 个 Markdown 文件。
3. 运行 `graphrag init --root llm_backend/app/graphrag_workspaces/ragtest --force`。
4. 根据中文技术 Markdown 文档调整 GraphRAG settings 和 prompts。
5. 运行 `graphrag index --root llm_backend/app/graphrag_workspaces/ragtest --method standard`。
6. 写一个小检查命令，打印各 parquet 行数和字段。
7. 使用 `graphrag query --method local --query "<测试问题>" --root llm_backend/app/graphrag_workspaces/ragtest` 验证查询。
8. 可选：分别验证 `global`、`drift`、`basic`。

验收标准：

- workspace 中存在 `input` 目录，并包含测试文档。
- workspace 中生成 `entities.parquet`、`relationships.parquet`、`text_units.parquet`、`documents.parquet`、`communities.parquet`、`community_reports.parquet`。
- 检查命令能打印所有 parquet 的行数和字段。
- `graphrag query --method local` 能返回与测试 Markdown 相关的回答。
- 本文档记录实际执行命令、产物路径、测试问题和查询结果摘要。
- 如果失败，本文档记录完整错误信息、缺失环境变量或配置项。

### 阶段 2：GraphRAG CLI Retriever Wrapper

目标：

在 `deepseek_agent` 中实现一个最小 GraphRAG CLI wrapper，使后端代码可以调用 GraphRAG 本地 index。

建议新增文件：

- `llm_backend/app/graphrag_cli/__init__.py`
- `llm_backend/app/graphrag_cli/retriever.py`
- `llm_backend/app/graphrag_cli/config.py`

任务：

1. 增加配置项：
   - GraphRAG CLI 路径
   - GraphRAG workspace root
   - 默认 query method
   - response type
   - timeout
2. 使用 `asyncio.create_subprocess_exec` 或同步 `subprocess.run` 调用 `graphrag query`。
3. 支持参数：
   - `query`
   - `method`
   - `root`
   - `data`，可选
   - `response_type`，可选
4. 捕获 stdout、stderr、return code。
5. 对 CLI 输出做最小清洗，返回结构化结果。
6. 增加一个简单 smoke script 或测试函数。

验收标准：

- wrapper 可以对测试 workspace 执行 `local` 查询并返回文本。
- wrapper 在 CLI 返回非 0 状态时能返回清晰错误。
- wrapper 有 timeout，避免请求无限挂起。
- wrapper 不依赖 Neo4j。
- wrapper 的 smoke 命令记录到本文档。

### 阶段 3：迁移 Milvus 传统 RAG 入库

目标：

把 `rag_project` 的 Markdown 解析、Milvus collection 创建和 hybrid 检索能力迁移到 `deepseek_agent`。

建议新增文件：

- `llm_backend/app/rag_ingest/__init__.py`
- `llm_backend/app/rag_ingest/markdown_parser.py`
- `llm_backend/app/rag_ingest/milvus_store.py`
- `llm_backend/app/rag_ingest/write_milvus.py`
- `llm_backend/app/rag_retrieval/__init__.py`
- `llm_backend/app/rag_retrieval/milvus_retriever.py`

任务：

1. 迁移 Markdown 解析和语义切分逻辑。
2. 迁移 Milvus schema 创建逻辑，保留 dense 和 sparse 字段。
3. 在 `app/core/config.py` 中新增 Milvus 和 embedding 配置。
4. 保留 BM25 sparse 生成能力。
5. 保留 dense embedding 能力。
6. 保留 RRF 风格 hybrid 检索参数。
7. 提供 Markdown 目录入库脚本或 CLI。

验收标准：

- 能创建 Milvus collection，默认不删除已有 collection。
- 能导入一个小型 Markdown 目录。
- 对已知关键词查询时，Milvus retriever 返回至少 1 条文档结果。
- retriever 返回 LangChain `Document` 或明确记录的内部结果类型。
- 迁移完成后，运行时不依赖 `/home/aetherlens/projects/rag_project` 的源码导入。

### 阶段 4：重写提示词与路由

目标：

将主流程从“电商/智能家居 KG”改为“Markdown 文档知识库 GraphRAG CLI + Milvus hybrid RAG”。

任务：

1. 重写 router prompt，使知识库类问题进入合并检索路径。
2. 重写 tool descriptions，使工具描述面向 GraphRAG CLI 查询和 Milvus 文档块检索。
3. 移除或停用旧电商 predefined Cypher 工具。
4. 移除或停用 text2cypher/Neo4j KG 工具在第一版主流程中的调用。
5. 重写 guardrails，从电商经营范围判断改为文档知识库相关性判断。
6. 清理或标记旧智能家居、电商、商品、订单、客户、供应商相关提示词。

验收标准：

- active prompt 中不再出现智能家居经营范围、商品库存、订单、客户、供应商等旧业务主线。
- 已知 Markdown 概念问题能路由到 GraphRAG CLI + Milvus 检索路径。
- 普通闲聊问题仍能路由到 general query。
- tool selection 能选择 GraphRAG CLI 查询工具，不再引用旧电商标签。
- 本文档记录至少 3 个测试问题及预期路由结果。

### 阶段 5：实现合并检索节点

目标：

实现运行时同时调用 GraphRAG CLI 和 Milvus hybrid RAG 的检索节点，并融合上下文。

建议新增文件：

- `llm_backend/app/retrieval/__init__.py`
- `llm_backend/app/retrieval/graphrag_cli_retriever.py`
- `llm_backend/app/retrieval/vector_retriever.py`
- `llm_backend/app/retrieval/fusion.py`

任务：

1. 实现 `graphrag_cli_retriever.search(query, method="local")`。
2. 实现 `vector_retriever.search(query)`。
3. 实现 `fusion.build_context(graphrag_result, vector_results)`。
4. 将 fusion 上下文接入 LangGraph research path。
5. 保持现有前端 SSE 流式响应兼容。

验收标准：

- GraphRAG CLI retriever 能返回 GraphRAG 查询结果。
- Milvus retriever 能返回文档块证据。
- 混合问题的最终 LLM prompt 同时包含 GraphRAG 结果和 Milvus 文档证据。
- `/api/langgraph/query` 仍能向前端返回 SSE 数据。
- GraphRAG CLI 或 Milvus 单侧不可用时，系统能降级，并在日志中明确失败来源。

### 阶段 6：入库接口或命令

目标：

为 GraphRAG index 和 Milvus RAG 入库提供可操作入口。

任务：

1. 决定入库优先使用 CLI、FastAPI endpoint，或二者都支持。
2. 替换或修复当前 `/api/upload` 入库逻辑。
3. 提供 GraphRAG workspace index 命令或接口。
4. 提供 GraphRAG CLI query smoke 命令或接口。
5. 提供 Markdown directory -> Milvus ingest 命令或接口。
6. 为长任务提供状态输出或日志说明。

验收标准：

- 用户能通过文档化命令或 endpoint 启动 GraphRAG index。
- 用户能通过文档化命令或 endpoint 执行 GraphRAG query smoke test。
- 用户能通过文档化命令或 endpoint 启动 Milvus 入库。
- 如果通过 FastAPI 暴露，长任务不会阻塞普通聊天请求。
- `self.config_mapping` 未定义问题被修复，或该旧路径不再是 active path。
- 入库错误以结构化形式返回或清晰记录到日志。

### 阶段 7：端到端验证

目标：

用真实 Markdown 文档验证完整系统。

任务：

1. 选择小型 Markdown 样本。
2. 完成 GraphRAG index。
3. 直接验证 GraphRAG CLI query。
4. 完成 Markdown 到 Milvus 导入。
5. 直接验证 Milvus 检索。
6. 通过 FastAPI LangGraph 接口验证最终回答。
7. 验证前端页面调用正常。

验收标准：

- GraphRAG CLI 能对测试 workspace 返回有效回答。
- Milvus 能返回 hybrid 检索结果。
- `/api/langgraph/query` 能针对至少 3 个 Markdown 语料问题返回有证据支撑的回答。
- general chat 仍可用。
- Markdown 知识库问题不会出现旧电商业务回答。
- 本文档记录最终验证命令、结果和残余问题。

### 阶段 8：清理与文档完善

目标：

清理旧路径，完善操作文档，让后续开发者能复现部署、入库和查询。

任务：

1. 更新 README，说明环境、依赖、启动、GraphRAG index、GraphRAG query、Milvus 入库、FastAPI 查询。
2. 标记或隔离旧电商 KG 模块。
3. 清理 dead import 和废弃路由。
4. 增加最小 smoke test 或 smoke script。
5. 更新依赖文件。

验收标准：

- 新开发者能根据 README 跑通小样本 GraphRAG index/query、Milvus 入库和 FastAPI 查询。
- `deepseek_agent` 与 `rag_project` 的依赖差异已被记录或解决。
- 旧电商 KG/Neo4j 模块不会被 active runtime path 调用。
- smoke test/script 可重复运行。

## 10. 推荐执行顺序

必须按顺序推进：

1. 阶段 0：基线验证
2. 阶段 1：GraphRAG 测试工作区与 CLI 查询验证
3. 阶段 2：GraphRAG CLI Retriever Wrapper
4. 阶段 3：迁移 Milvus 传统 RAG 入库
5. 阶段 4：重写提示词与路由
6. 阶段 5：实现合并检索节点
7. 阶段 6：入库接口或命令
8. 阶段 7：端到端验证
9. 阶段 8：清理与文档完善

不要在 GraphRAG CLI query 和 Milvus 直接检索都未验证前启动阶段 5。否则失败时很难判断问题来自 index、CLI wrapper、Milvus、融合还是 LangGraph 接线。

## 11. 环境变量清单

待阶段 0 补充。

预计至少需要：

- GraphRAG indexing 使用的 LLM API key/base URL/model。
- GraphRAG query 使用的 LLM API key/base URL/model。
- runtime answering 使用的 LLM API key/base URL/model。
- GraphRAG embedding 模型/API 配置。
- Milvus embedding 模型名称、设备、归一化参数。
- Milvus URI、collection 名。
- 现有 FastAPI app 需要的 MySQL、Redis、JWT 等配置。

Neo4j 环境变量不是第一版必需项。

## 12. 待决策问题

1. GraphRAG workspace 位置：
   - 测试建议：`llm_backend/app/graphrag_workspaces/ragtest`。
   - 生产路径在阶段 1 后决定。

2. GraphRAG query method 选择：
   - 第一版固定 `local`。
   - 后续可根据问题类型选择 `local`、`global`、`drift`、`basic`。

3. GraphRAG 调用方式：
   - 第一版使用 CLI wrapper。
   - 如果 CLI 启动开销大，后续改为 Python API。

4. 入库入口：
   - 第一版建议 CLI 优先。
   - FastAPI endpoint 等 CLI 稳定后再暴露。

5. GraphRAG 与 Milvus 融合方式：
   - 第一版可将 GraphRAG 回答作为一个高层结果，将 Milvus 文档块作为证据补充。
   - 后续如需严格证据融合，应研究 GraphRAG Python API/context 输出。

6. Prompt 语言：
   - 当前语料主要是中文技术 Markdown。
   - GraphRAG prompt 和运行时 prompt 建议中文优先。

## 13. 已降级为后续增强项的内容

以下内容不是第一版目标：

- GraphRAG parquet -> Neo4j loader
- Neo4j schema 设计
- Neo4j 多数据库或新容器
- Cypher 生成
- text2cypher
- 实体类型动态标签
- 关系类型分类
- Neo4j Browser 图谱可视化

只有当 GraphRAG CLI + Milvus hybrid RAG 第一版链路验证成功，且明确需要图数据库能力时，才重新评估这些增强项。

## 14. 接力协议

后续模型开始前必须：

1. 阅读本文档。
2. 查看 `git status`。
3. 根据“当前状态”判断下一阶段。
4. 不要假设上一阶段已完成，除非验收标准已满足。

后续模型完成后必须：

1. 更新“当前状态”。
2. 记录执行过的命令和关键结果。
3. 标记已完成的验收标准。
4. 记录阻塞点和完整错误信息。
5. 除非用户要求扩大范围，否则只处理当前阶段任务。

## 15. 下一步

下一位模型应从阶段 0：基线验证开始。

当前只完成了调研和本文档改写，尚未开始合并实现。

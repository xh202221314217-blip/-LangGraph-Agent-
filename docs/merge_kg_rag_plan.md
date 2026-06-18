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

最后更新时间：2026-06-18

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
- 已完成阶段 0 基线验证：
  - `deepseek_agent/.venv` 可用，Python 版本为 3.12.13。
  - `.venv/bin/graphrag index --help` 可打印帮助信息。
  - `.venv/bin/graphrag query --help` 可打印帮助信息，并包含 `local|global|drift|basic`。
  - `rag_project` 的 Milvus 相关源码依赖已安装，但从仓库根目录直接导入存在源码导入路径问题，详见“阶段执行记录”。
- 已完成阶段 1 GraphRAG 测试工作区与 CLI 查询验证：
  - 已创建 `llm_backend/app/graphrag_workspaces/ragtest`。
  - 已复制 5 个 `rag_project` Markdown 技术文档到 workspace `input`。
  - 已使用百炼 OpenAI-compatible 接口完成 `graphrag index --method standard`。
  - 已生成 6 个目标 parquet 和 lancedb 向量索引。
  - 已通过 `graphrag query --method local` 查询验证。
- 已完成阶段 2 GraphRAG CLI Retriever Wrapper：
  - 已新增 `llm_backend/app/graphrag_cli` 包。
  - 已实现环境变量可配置的 CLI wrapper。
  - 已实现异步 `graphrag query` 调用、stdout/stderr/return code 捕获、timeout 和最小 stdout 清洗。
  - 已新增可重复运行的 smoke 命令。
- 已完成阶段 3 Milvus 传统 RAG 入库/检索迁移：
  - 已新增 `llm_backend/app/rag_ingest` 和 `llm_backend/app/rag_retrieval` 包。
  - 已迁移 Markdown 解析、语义切分入口、Milvus dense+sparse schema、BM25 Function、HNSW/dense 与 sparse inverted index。
  - 已新增 Markdown 目录入库 CLI 和 Milvus hybrid retriever。
  - 已通过独立 smoke collection 验证：创建 collection、导入 5 条文档、关键词检索返回 4 条 LangChain `Document`。
  - 迁移后的运行时不依赖 `/home/aetherlens/projects/rag_project` 源码导入。
- 已完成阶段 4 重写提示词与路由：
  - 已将 active router prompt 从电商/智能家居 KG 改为 Markdown 技术文档知识库路由。
  - 已将 general/additional/image/RAG/hallucination prompts 改为文档知识库语境。
  - 已新增 GraphRAG CLI 与 Milvus hybrid RAG 的工具描述。
  - 已从 `llm_backend/app/lg_agent/lg_builder.py` active path 中移除旧 Neo4j/Cypher multi-tool 子图导入与调用。
  - 已将知识库问题路由到第一版 GraphRAG CLI + Milvus hybrid RAG 检索路径占位；真实并行检索与融合回答留到阶段 5 实现。
- 已完成阶段 5 合并检索节点：
  - 已新增 `llm_backend/app/lg_agent/knowledge_fusion.py`。
  - 已实现运行时并发调用 GraphRAG CLI 和 Milvus hybrid RAG。
  - 已将 `lg_builder.py` 中知识库路径从检索计划占位替换为真实检索、上下文融合和最终回答生成。
  - 已在 `AgentState` 中新增 `documents` 字段，用于保存融合后的检索上下文。
  - 已验证 GraphRAG CLI 可返回结果，Milvus retriever 可返回文档块证据，融合上下文同时包含两侧结果。
  - 单侧失败会降级为另一侧结果，并在融合上下文和日志中记录失败来源。

未完成：

- 尚未进行端到端入库与查询验证。

已知问题：

- `llm_backend/app/services/indexing_service.py` 中 `_get_config_file()` 引用了未定义的 `self.config_mapping`。在修复或替换前，不要依赖当前 `/api/upload` 的 GraphRAG 入库路径。
- 原 Neo4j KG 子图仍存在于代码中，但不应作为第一版合并主线。
- `rag_project/RAG_PROJECT/RAG_PROJECT/documents/milvus_db.py` 使用顶层导入 `from documents...`、`from llm_models...`、`from utils...`。从 `/home/aetherlens/projects/rag_project` 直接执行验收命令时，`RAG_PROJECT/RAG_PROJECT` 未在 `sys.path` 中，会触发 `ModuleNotFoundError: No module named 'documents'`。
- 给 `PYTHONPATH` 加上 `/home/aetherlens/projects/rag_project/RAG_PROJECT/RAG_PROJECT` 后，导入会继续加载 `BAAI/bge-large-zh-v1.5`。当前环境设置了 `HF_ENDPOINT=https://hf-mirror.com`，该镜像请求失败且本地无模型缓存，最终报错为无法连接镜像并找不到缓存文件。官方 `https://huggingface.co` 在本机可达。
- DeepSeek API 当前不能支持 GraphRAG index 所需的完整调用链路；GraphRAG index/query workspace 配置应使用百炼 OpenAI-compatible 接口。运行时普通聊天、总结和融合回答可优先使用 DeepSeek。
- 百炼 `text-embedding-v3` embedding 接口每批 input 不能超过 10；GraphRAG 默认 `embed_text.batch_size=16` 会失败，`ragtest/settings.yaml` 已设置为 `embed_text.batch_size=8`。
- `unstructured` Markdown parser 在当前环境会尝试下载 NLTK 数据，下载地址返回 `HTTP Error 403: Forbidden`。迁移后的 `MarkdownParser` 已增加纯 Markdown 文本兜底解析，优先使用 `unstructured`，失败时按 Markdown 标题段落切分。
- 当前 `llm_backend/.env` 未配置 `RAG_OPENAI_EMBEDDING_API_KEY` 或 `OPENAI_API_KEY`，因此生产路径如选择 `RAG_EMBEDDING_PROVIDER=openai` 需要补充 key；默认 HuggingFace embedding 仍可能受 `HF_ENDPOINT` 和模型缓存影响。
- 阶段 5 生产默认 Milvus 检索路径仍会使用 `RAG_EMBEDDING_PROVIDER=huggingface`，当前环境因 `HF_ENDPOINT=https://hf-mirror.com` 且无本地模型缓存，默认 collection 检索会在 embedding 初始化时失败。融合层已能降级到 GraphRAG；生产要启用 Milvus 默认链路，需要缓存 `BAAI/bge-large-zh-v1.5`、修正 `HF_ENDPOINT`，或配置 `RAG_EMBEDDING_PROVIDER=openai` 与有效 embedding key。

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

### 阶段执行记录：阶段 0 基线验证

执行时间：2026-06-18。

执行命令与结果：

```bash
cd /home/aetherlens/projects/deepseek_agent
.venv/bin/python --version
```

结果：成功，版本为 `Python 3.12.13`。

```bash
cd /home/aetherlens/projects/deepseek_agent
.venv/bin/graphrag index --help
```

结果：成功，打印 `graphrag index` 帮助信息，包含 `--root`、`--method [standard|fast]`、`--output` 等参数。

```bash
cd /home/aetherlens/projects/deepseek_agent
.venv/bin/graphrag query --help
```

结果：成功，打印 `graphrag query` 帮助信息，`--method` 支持 `local|global|drift|basic`，同时支持 `--query`、`--root`、`--data`、`--response-type`、`--streaming`。

```bash
cd /home/aetherlens/projects/rag_project
.venv/bin/python -c "from RAG_PROJECT.RAG_PROJECT.documents.milvus_db import MilvusVectorSave"
```

结果：失败。失败原因是 `milvus_db.py` 内部使用 `from documents.markdown_parser import MarkdownParser` 这类顶层导入，仓库根目录执行时没有把 `/home/aetherlens/projects/rag_project/RAG_PROJECT/RAG_PROJECT` 加入 `sys.path`，报错为 `ModuleNotFoundError: No module named 'documents'`。

验证修复方式：

```bash
cd /home/aetherlens/projects/rag_project
PYTHONPATH=/home/aetherlens/projects/rag_project/RAG_PROJECT/RAG_PROJECT \
  .venv/bin/python -c "from RAG_PROJECT.RAG_PROJECT.documents.milvus_db import MilvusVectorSave"
```

结果：导入路径问题解决，但导入会继续初始化 `HuggingFaceEmbeddings(model_name="BAAI/bge-large-zh-v1.5", model_kwargs={"device": "cuda"})`。当前 shell 环境存在 `HF_ENDPOINT=https://hf-mirror.com`，该镜像访问返回跳转/元数据异常，且本地没有模型缓存，因此最终失败于模型下载。`curl -I https://huggingface.co/BAAI/bge-large-zh-v1.5/resolve/main/config.json` 可返回 307，说明官方 Hugging Face 端点可达。

阶段 0 结论：

- `deepseek_agent` 的 Python 虚拟环境和 GraphRAG CLI 基线通过。
- GraphRAG CLI query method 能力满足阶段 1 前置条件。
- `rag_project` Milvus 相关依赖已在 `.venv` 中存在；当前阻塞点是源码导入路径和 BGE 模型下载/缓存，不是缺少 Milvus Python 包。
- 阶段 0 未改动应用行为，未修改代码，未创建 workspace，未下载大模型。

阶段 1 前建议：

- GraphRAG 阶段可继续推进，不依赖 `rag_project` 的 Milvus 导入。
- 后续迁移 Milvus 代码时，应改为包内相对导入或迁移到 `deepseek_agent` 自身包结构，避免依赖手动 `PYTHONPATH`。
- 若继续复用 `rag_project` 的 embedding 初始化，建议显式配置 `HF_ENDPOINT=https://huggingface.co` 或预先缓存 `BAAI/bge-large-zh-v1.5`，并确认运行环境有可用 CUDA；否则将 `model_kwargs` 调整为可配置，允许 CPU 兜底。

### 阶段执行记录：阶段 1 GraphRAG 测试工作区与 CLI 查询验证

执行时间：2026-06-18。

重要提醒：

- DeepSeek API 不能用于 GraphRAG index 操作。本阶段 GraphRAG workspace 的 chat 和 embedding 均配置为百炼 OpenAI-compatible 接口。
- workspace `.env` 保存本地密钥值，但仓库通过 `llm_backend/app/graphrag_workspaces/.gitignore` 忽略 `**/.env`，避免误提交；GraphRAG `cache/` 和 `logs/` 也被忽略，避免提交大量中间缓存与运行日志。

测试工作区：

- `llm_backend/app/graphrag_workspaces/ragtest`

测试文档：

- `tech_report_kvtvbuvp.md`
- `tech_report_hwbh0qqf.md`
- `tech_report_lnwngbun.md`
- `tech_report_m7we5422.md`
- `tech_report_vebl21yh.md`

执行命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
mkdir -p llm_backend/app/graphrag_workspaces/ragtest/input
cp /home/aetherlens/projects/rag_project/md/md/tech_report_{kvtvbuvp,hwbh0qqf,lnwngbun,m7we5422,vebl21yh}.md \
  llm_backend/app/graphrag_workspaces/ragtest/input/
.venv/bin/graphrag init --root llm_backend/app/graphrag_workspaces/ragtest --force
```

配置调整：

- `settings.yaml` 使用 `api_base=https://dashscope.aliyuncs.com/compatible-mode/v1`。
- chat model 使用 `qwen-plus`。
- embedding model 使用 `text-embedding-v3`。
- 显式设置 `encoding_model: cl100k_base`，避免 GraphRAG/tiktoken 无法识别 `qwen-plus`。
- `input.file_pattern` 设置为 `.*\\.md$$`，适配 Markdown 输入并转义 Python `Template` 的 `$`。
- 复制已有中文 GraphRAG prompts 到 `ragtest/prompts`。
- `embed_text.batch_size` 设置为 `8`，绕开百炼 embedding 每批 input 不能超过 10 的限制。
- `entity_types` 调整为技术文档相关类型：`technology`、`material`、`process`、`device`、`application`、`metric`、`challenge`、`solution`、`organization`、`product`。

index 命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
.venv/bin/graphrag index --root llm_backend/app/graphrag_workspaces/ragtest --method standard
```

结果：成功，最终输出 `All workflows completed successfully`。

中间失败与修复：

- 第一次失败：`file_pattern: ".*\\.md$"` 中的 `$` 被 GraphRAG 配置加载的 Python `Template` 当成非法占位符。修复为 `.*\\.md$$`。
- 第二次失败：`qwen-plus` 无法被 tiktoken 自动映射 tokenizer。修复为 chat 和 embedding 模型均显式设置 `encoding_model: cl100k_base`。
- 第三次失败：百炼 embedding 接口返回 `batch size is invalid, it should not be larger than 10`。修复为在 `embed_text` 段设置 `batch_size: 8`。注意该字段不属于 `models.default_embedding_model`，放在模型段不会生效。

parquet 检查命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
.venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
root = Path('llm_backend/app/graphrag_workspaces/ragtest/output')
for name in ['entities','relationships','text_units','documents','communities','community_reports']:
    path = root / f'{name}.parquet'
    df = pd.read_parquet(path)
    print(f'{name}.parquet rows={len(df)} columns={list(df.columns)}')
PY
```

检查结果：

- `entities.parquet`: 91 行，字段为 `id`, `human_readable_id`, `title`, `type`, `description`, `text_unit_ids`, `frequency`, `degree`, `x`, `y`。
- `relationships.parquet`: 94 行，字段为 `id`, `human_readable_id`, `source`, `target`, `description`, `weight`, `combined_degree`, `text_unit_ids`。
- `text_units.parquet`: 12 行，字段为 `id`, `human_readable_id`, `text`, `n_tokens`, `document_ids`, `entity_ids`, `relationship_ids`, `covariate_ids`。
- `documents.parquet`: 5 行，字段为 `id`, `human_readable_id`, `title`, `text`, `text_unit_ids`, `creation_date`, `metadata`。
- `communities.parquet`: 17 行，字段为 `id`, `human_readable_id`, `community`, `level`, `parent`, `children`, `title`, `entity_ids`, `relationship_ids`, `text_unit_ids`, `period`, `size`。
- `community_reports.parquet`: 17 行，字段为 `id`, `human_readable_id`, `community`, `level`, `parent`, `children`, `title`, `summary`, `full_content`, `rank`, `rating_explanation`, `findings`, `full_content_json`, `period`, `size`。

lancedb 产物：

- `output/lancedb/default-community-full_content.lance`
- `output/lancedb/default-text_unit-text.lance`
- `output/lancedb/default-entity-description.lance`

local 查询命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
.venv/bin/graphrag query \
  --root llm_backend/app/graphrag_workspaces/ragtest \
  --method local \
  --query "GAAFET 相比 FinFET 的关键优势是什么？"
```

结果：成功，GraphRAG 返回与测试 Markdown 相关的中文回答。回答摘要：GAAFET 相比 FinFET 的核心优势包括 360 度全周向栅极控制、短沟道效应和 DIBL 抑制更强、静电控制效率提升、纳米片/纳米线沟道带来更高设计自由度，以及在 3nm 及以下节点具备更好的可扩展性和能效。

阶段 1 结论：

- 验收通过。
- 阶段 2 可以基于 `llm_backend/app/graphrag_workspaces/ragtest` 实现 GraphRAG CLI retriever wrapper。

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

### 阶段执行记录：阶段 2 GraphRAG CLI Retriever Wrapper

执行时间：2026-06-18。

新增文件：

- `llm_backend/app/graphrag_cli/__init__.py`
- `llm_backend/app/graphrag_cli/config.py`
- `llm_backend/app/graphrag_cli/retriever.py`
- `llm_backend/app/graphrag_cli/smoke.py`

实现内容：

- `GraphRAGCLIConfig` 支持通过环境变量覆盖：
  - `GRAPHRAG_CLI_PATH`
  - `GRAPHRAG_CLI_WORKSPACE_ROOT`
  - `GRAPHRAG_CLI_DEFAULT_METHOD`
  - `GRAPHRAG_CLI_RESPONSE_TYPE`
  - `GRAPHRAG_CLI_TIMEOUT_SECONDS`
- `GraphRAGCLIRetriever.query()` 使用 `asyncio.create_subprocess_exec` 调用 `graphrag query`。
- 支持 `query`、`method`、`root`、`data`、`response_type`、`timeout_seconds` 参数。
- 返回 `GraphRAGCLIResult`，包含清洗后的 `text`、原始 `stdout`、`stderr`、`returncode`、耗时和实际命令。
- 当 CLI 返回非 0 状态时抛出 `GraphRAGCLIError`，错误中包含 return code、method、root 和 CLI 输出摘要。
- 当执行超过 timeout 时杀掉子进程并抛出 `GraphRAGCLIError`。
- wrapper 为独立模块，不导入 Neo4j，也不依赖旧 KG 子图。

验证命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m compileall -q llm_backend/app/graphrag_cli
```

结果：成功。

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_cli.smoke --help
```

结果：成功打印 smoke 参数，包括 `--query`、`--method`、`--root`、`--data`、`--response-type`、`--timeout`。

smoke 查询命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_cli.smoke \
  --method local \
  --query "GAAFET 相比 FinFET 的关键优势是什么？" \
  --timeout 180
```

结果：成功。返回 `returncode=0`，耗时约 `81.04` 秒。清洗后的正文不包含 `INFO: Vector Store Args` 前置日志，回答摘要为：GAAFET 相比 FinFET 的关键优势包括 360 度全周向栅极控制、静电控制效率提升、短沟道效应抑制更强、纳米片/纳米线沟道带来更高设计自由度、相同功耗下性能提升或相同性能下降低功耗，以及支撑 3nm 及以下先进制程延续。

非 0 状态验证命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
from app.graphrag_cli import GraphRAGCLIRetriever, GraphRAGCLIError
try:
    GraphRAGCLIRetriever().query_sync(
        "test question",
        root="/tmp/no-such-graphrag-workspace",
        timeout_seconds=30,
    )
except GraphRAGCLIError as exc:
    print(str(exc)[:1000])
else:
    raise SystemExit("expected GraphRAGCLIError")
PY
```

结果：成功捕获错误。错误信息包含 `returncode=2`，并保留 CLI 关于 `--root` 路径不存在的提示。

timeout 验证命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
from app.graphrag_cli import GraphRAGCLIRetriever, GraphRAGCLIError
try:
    GraphRAGCLIRetriever().query_sync(
        "GAAFET 相比 FinFET 的关键优势是什么？",
        timeout_seconds=0.001,
    )
except GraphRAGCLIError as exc:
    print(exc)
else:
    raise SystemExit("expected timeout")
PY
```

结果：成功触发 timeout，wrapper 返回 `GraphRAG CLI query timed out`，并终止子进程。

阶段 2 结论：

- 验收通过。
- 阶段 3 可以开始迁移 Milvus 传统 RAG 入库与检索代码。

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

### 阶段执行记录：阶段 3 Milvus 传统 RAG 入库

执行时间：2026-06-18。

新增文件：

- `llm_backend/app/rag_ingest/__init__.py`
- `llm_backend/app/rag_ingest/markdown_parser.py`
- `llm_backend/app/rag_ingest/milvus_store.py`
- `llm_backend/app/rag_ingest/write_milvus.py`
- `llm_backend/app/rag_retrieval/__init__.py`
- `llm_backend/app/rag_retrieval/milvus_retriever.py`
- `llm_backend/app/rag_retrieval/smoke.py`

修改文件：

- `llm_backend/app/core/config.py`
- `requirements.txt`

实现内容：

- `MarkdownParser` 迁移了 `unstructured` elements 解析、标题/正文合并和可选 `SemanticChunker` 语义切分。
- `MarkdownParser` 增加纯 Markdown 兜底解析器；当前环境中 `unstructured` 下载 NLTK 数据失败时，会按 Markdown 标题段落切分。
- `MilvusVectorStore` 可创建 dense+sparse hybrid collection，默认 `drop_existing=False`，不会删除已有 collection。
- Milvus schema 保留 `text`、`category`、`source`、`filename`、`filetype`、`title`、`category_depth`、`sparse`、`dense` 字段。
- `text` 字段启用 jieba analyzer，`sparse` 通过 Milvus BM25 Function 生成。
- `sparse` 使用 `SPARSE_INVERTED_INDEX` + `BM25`；`dense` 使用 `HNSW` + `IP`。
- dense embedding 延迟创建，支持 `RAG_EMBEDDING_PROVIDER=huggingface|openai`。
- `write_milvus.py` 提供 Markdown 目录入库 CLI，支持 `--md-dir`、`--batch-size`、`--limit`、`--drop-existing`、`--skip-semantic-chunking`。
- `MilvusHybridRetriever` 返回 LangChain `Document`，保留 RRF 风格 `ranker_type="rrf"` 和 `ranker_params={"k": ...}`。

依赖调整：

- 新增并约束到当前 LangChain 0.3 兼容线：
  - `langchain-experimental>=0.3.4,<0.4.0`
  - `langchain-huggingface>=0.1.2,<1.0.0`
  - `langchain-milvus>=0.1.8,<0.2.0`
  - `pymilvus>=2.5.0,<2.6.0`
  - `unstructured[md]>=0.15.0,<0.16.0`
- 当前 `.venv` 已同步安装并通过 `pip check`。

验证命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m compileall -q \
  llm_backend/app/rag_ingest \
  llm_backend/app/rag_retrieval \
  llm_backend/app/core/config.py
```

结果：成功。

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m app.rag_ingest.write_milvus --help
PYTHONPATH=llm_backend .venv/bin/python -m app.rag_retrieval.smoke --help
```

结果：两个 CLI 均可打印帮助信息。

```bash
cd /home/aetherlens/projects/deepseek_agent
.venv/bin/pip check
```

结果：`No broken requirements found.`。

Milvus schema 验证：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
from app.rag_ingest import MilvusVectorStore
MilvusVectorStore().create_collection()
PY
```

结果：成功创建或复用默认 `t_collection01`，未传 `drop_existing=True`，因此不会删除已有 collection。后续用 `MilvusClient.list_collections()` 确认存在 `t_collection01`，并确认索引包含 `sparse_inverted_index` 和 `dense_inverted_index`。

最小入库/检索 smoke：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
# 使用测试用固定 1024 维 embedding，避免依赖外部 API 或 HuggingFace 模型下载。
# collection: codex_stage3_smoke
# source: llm_backend/app/graphrag_workspaces/ragtest/input/tech_report_kvtvbuvp.md
PY
```

结果：成功。实际执行结果为 `inserted=5`、`results=4`，返回类型为 LangChain `Document`。前两条结果来自 `tech_report_kvtvbuvp.md`，标题分别为“利用蚀刻技术实现纳米级电路图案的方法”和“蚀刻技术的基本原理与分类”。

阶段 3 结论：

- 验收通过。
- Milvus collection 创建、Markdown 小样本导入、关键词检索和 Document 返回类型均已验证。
- 生产 embedding 仍需要后续根据部署环境选择并配置：HuggingFace 本地模型缓存，或 `RAG_EMBEDDING_PROVIDER=openai` 搭配 `RAG_OPENAI_EMBEDDING_API_KEY`/`OPENAI_API_KEY`。
- 阶段 4 可以开始重写 router、tool selection 和 guardrails 提示词。

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

### 阶段执行记录：阶段 4 重写提示词与路由

执行时间：2026-06-18。

修改文件：

- `llm_backend/app/lg_agent/lg_prompts.py`
- `llm_backend/app/lg_agent/lg_builder.py`
- `docs/merge_kg_rag_plan.md`

实现内容：

- `ROUTER_SYSTEM_PROMPT` 已改为 Markdown 技术文档知识库路由器。
- `general-query` 现在表示不需要查询本地 Markdown 知识库的普通问题。
- `additional-query` 现在用于缺少主题、范围、对象等检索必要信息的问题。
- `graphrag-query` 现在用于技术概念、材料、工艺、器件、应用、指标、挑战、方案、文档事实查询、文档比较和文档总结等知识库问题。
- `GET_ADDITIONAL_SYSTEM_PROMPT`、`GET_IMAGE_SYSTEM_PROMPT`、`RAGSEARCH_SYSTEM_PROMPT`、`CHECK_HALLUCINATIONS` 已切换到文档知识库语境。
- 新增 `KNOWLEDGE_TOOL_DESCRIPTIONS`，描述第一版可用的 GraphRAG CLI 查询与 Milvus hybrid RAG 文档块检索。
- `lg_builder.py` 不再在 active path 导入或调用旧 Neo4j/Cypher multi-tool workflow、Northwind retriever、predefined Cypher dict 或 graph schema helper。
- `create_research_plan` 目前作为阶段 4 检索路径占位：知识库问题会进入该节点，并根据用户问题生成 GraphRAG CLI、Milvus hybrid RAG 或二者并用的简短检索计划。阶段 5 会把该占位替换为真实并行检索、上下文融合和最终回答。

验证命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m compileall -q \
  llm_backend/app/lg_agent/lg_prompts.py \
  llm_backend/app/lg_agent/lg_builder.py
```

结果：成功。

```bash
cd /home/aetherlens/projects/deepseek_agent
rg "电商|智能家居|商品|订单|客户|供应商|Cypher|Neo4j|经营范围" \
  llm_backend/app/lg_agent/lg_prompts.py \
  llm_backend/app/lg_agent/lg_builder.py
```

结果：无匹配。

```bash
cd /home/aetherlens/projects/deepseek_agent
rg "kg_sub_graph|NorthwindCypherRetriever|create_multi_tool_workflow|get_neo4j_graph|predefined_cypher" \
  llm_backend/app/lg_agent/lg_builder.py
```

结果：无匹配。

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
from app.lg_agent.lg_builder import graph, route_query
from app.lg_agent.lg_states import AgentState
print(type(graph).__name__)
print(route_query(AgentState(messages=[], router={"type": "graphrag-query", "logic": "doc question", "question": "GAAFET"})))
print(route_query(AgentState(messages=[], router={"type": "general-query", "logic": "chat", "question": "hi"})))
PY
```

结果：成功，输出 `CompiledStateGraph`、`create_research_plan`、`respond_to_general_query`。

测试问题与预期路由：

- `GAAFET 相比 FinFET 的关键优势是什么？` -> `graphrag-query` -> `create_research_plan`，预期阶段 5 使用 GraphRAG CLI + Milvus hybrid RAG。
- `请总结这些文档里提到的蚀刻技术分类。` -> `graphrag-query` -> `create_research_plan`，预期阶段 5 使用 GraphRAG CLI + Milvus hybrid RAG。
- `你好，帮我把这句话翻译成英文。` -> `general-query` -> `respond_to_general_query`。
- `这个方案有什么优势？` -> `additional-query`，因为缺少明确主题或上下文对象。

阶段 4 结论：

- 验收通过。
- active prompt 和主流程 builder 不再携带旧电商/智能家居/Neo4j/Cypher 主线。
- 阶段 5 可以开始实现真实的 GraphRAG CLI + Milvus hybrid RAG 并行检索与融合回答节点。

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

### 阶段执行记录：阶段 5 合并检索节点

执行时间：2026-06-18。

修改文件：

- `llm_backend/app/lg_agent/knowledge_fusion.py`
- `llm_backend/app/lg_agent/lg_builder.py`
- `llm_backend/app/lg_agent/lg_states.py`
- `docs/merge_kg_rag_plan.md`

实现内容：

- 新增 `HybridKnowledgeRetriever`，使用 `asyncio.create_task` + `asyncio.gather(..., return_exceptions=True)` 并发调用：
  - `GraphRAGCLIRetriever.query()`
  - `MilvusHybridRetriever.search()`
- 新增 `KnowledgeFusionResult.to_context()`，把 GraphRAG 回答和 Milvus `Document` 证据格式化为最终 LLM prompt 的 `<context>` 内容。
- 新增 `MilvusDocumentEvidence`，保留文档块内容和 `source`、`filename`、`title`、`pk` 等来源元数据。
- `lg_builder.py` 中 `create_research_plan` 不再生成检索计划，而是执行真实检索、构造 `RAGSEARCH_SYSTEM_PROMPT`、调用 DeepSeek 生成最终回答。
- `AgentState` 新增 `documents` 字段，保存融合上下文，供后续质检或调试使用。
- GraphRAG 或 Milvus 任一侧失败时，不中断整个知识库回答流程；失败来源会写入日志和融合上下文的“检索错误”段。

验证命令：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m compileall -q \
  llm_backend/main.py \
  llm_backend/app/lg_agent \
  llm_backend/app/graphrag_cli \
  llm_backend/app/rag_retrieval
```

结果：成功。

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
from app.lg_agent.lg_builder import graph, route_query
from app.lg_agent.lg_states import AgentState
print(type(graph).__name__)
print(route_query(AgentState(messages=[], router={'type': 'graphrag-query', 'logic': 'doc', 'question': 'GAAFET'})))
PY
```

结果：成功，输出 `CompiledStateGraph`、`create_research_plan`。说明 active LangGraph 和 `/api/langgraph/query` 使用的 graph 可正常导入，知识库问题仍进入同一 SSE 消费路径。

GraphRAG + 默认 Milvus 降级验证：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend GRAPHRAG_CLI_TIMEOUT_SECONDS=120 .venv/bin/python - <<'PY'
import asyncio
from app.lg_agent.knowledge_fusion import HybridKnowledgeRetriever

async def main():
    result = await HybridKnowledgeRetriever(milvus_content_limit=300).retrieve('GAAFET 相比 FinFET 的关键优势是什么？')
    print('has_evidence=', result.has_evidence)
    print('graphrag_chars=', len(result.graphrag_text))
    print('milvus_docs=', len(result.milvus_documents))
    print('errors=', len(result.errors))

asyncio.run(main())
PY
```

结果：GraphRAG 成功返回约 927 字结果；默认 Milvus 检索失败于 HuggingFace mirror 模型加载；融合层未中断，`has_evidence=True`，`errors=1`，错误来源明确为 `Milvus hybrid RAG 检索失败`。

Milvus retriever 证据验证：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
from app.rag_ingest.milvus_store import MilvusVectorStore, MilvusStoreConfig
from app.rag_retrieval.milvus_retriever import MilvusHybridRetriever, MilvusRetrieverConfig

class FixedEmbeddings:
    def embed_query(self, text):
        return [0.01] * 1024
    def embed_documents(self, texts):
        return [[0.01] * 1024 for _ in texts]

store = MilvusVectorStore(
    config=MilvusStoreConfig(collection_name='codex_stage3_smoke'),
    embedding_function=FixedEmbeddings(),
)
retriever = MilvusHybridRetriever(
    store=store,
    config=MilvusRetrieverConfig(top_k=2, score_threshold=0.0, filter_category=''),
)
results = retriever.search('蚀刻技术 分类')
print('results=', len(results))
PY
```

结果：成功，`results=2`，返回文档块来源为 `llm_backend/app/graphrag_workspaces/ragtest/input/tech_report_kvtvbuvp.md`。

融合上下文双侧验证：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend GRAPHRAG_CLI_TIMEOUT_SECONDS=120 .venv/bin/python - <<'PY'
# 使用真实 GraphRAG CLI + 阶段 3 smoke collection 的固定 embedding Milvus retriever。
# 查询：蚀刻技术有哪些分类？
PY
```

结果：成功，`has_evidence=True`、`graphrag_chars=1109`、`milvus_docs=2`、`errors=[]`，融合上下文同时包含 `## GraphRAG CLI 结果` 和 `## Milvus hybrid RAG 文档块证据`。

阶段 5 结论：

- 验收通过。
- 运行时知识库路径已具备 GraphRAG CLI + Milvus hybrid RAG 并发检索、上下文融合、LLM  grounded answer 生成和单侧失败降级能力。
- 生产默认 Milvus 链路仍需补齐 embedding 环境：缓存 HuggingFace 模型、修正 `HF_ENDPOINT`，或配置 OpenAI-compatible embedding key。

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

阶段 0 已梳理。本文只记录变量名和用途，不记录本地密钥值。

`deepseek_agent` 现有 FastAPI/LangGraph 运行变量，来源为 `llm_backend/.env` 和 `llm_backend/app/core/config.py`：

- `DEEPSEEK_API_KEY`：DeepSeek API key。
- `DEEPSEEK_BASE_URL`：DeepSeek API base URL。
- `DEEPSEEK_MODEL`：DeepSeek 文本模型名。
- `VISION_API_KEY`：视觉模型 API key。
- `VISION_BASE_URL`：视觉模型 API base URL。
- `VISION_MODEL`：视觉模型名。
- `OLLAMA_BASE_URL`：Ollama 服务地址。
- `OLLAMA_CHAT_MODEL`：Ollama 聊天模型名。
- `OLLAMA_REASON_MODEL`：Ollama 推理模型名。
- `OLLAMA_EMBEDDING_MODEL`：Ollama embedding 模型名。
- `OLLAMA_AGENT_MODEL`：Ollama agent 模型名。
- `CHAT_SERVICE`：聊天服务选择，当前枚举为 `deepseek` 或 `ollama`。
- `REASON_SERVICE`：推理服务选择，当前枚举为 `deepseek` 或 `ollama`。
- `AGENT_SERVICE`：agent 服务选择，当前枚举为 `deepseek` 或 `ollama`。
- `SERPAPI_KEY`：SerpAPI 搜索 key。
- `SEARCH_RESULT_COUNT`：搜索结果数量。
- `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME`：MySQL 连接配置。
- `REDIS_HOST`、`REDIS_PORT`、`REDIS_DB`、`REDIS_PASSWORD`：Redis 连接配置。
- `REDIS_CACHE_EXPIRE`：Redis 语义缓存过期时间。
- `REDIS_CACHE_THRESHOLD`：Redis 语义缓存相似度阈值。
- `SECRET_KEY`、`ALGORITHM`、`ACCESS_TOKEN_EXPIRE_MINUTES`：JWT 配置。
- `EMBEDDING_TYPE`、`EMBEDDING_MODEL`、`EMBEDDING_THRESHOLD`：现有 embedding 配置。

`deepseek_agent` 现有 GraphRAG 配置变量：

- `GRAPHRAG_PROJECT_DIR`：当前 GraphRAG 项目目录，现默认指向 `llm_backend/app/graphrag`。
- `GRAPHRAG_DATA_DIR`：GraphRAG 数据目录名。
- `GRAPHRAG_QUERY_TYPE`：GraphRAG 查询类型，第一版建议固定 `local`。
- `GRAPHRAG_RESPONSE_TYPE`：GraphRAG 响应类型。
- `GRAPHRAG_COMMUNITY_LEVEL`：GraphRAG community level。
- `GRAPHRAG_DYNAMIC_COMMUNITY`：是否启用动态 community selection。

阶段 1 创建新 GraphRAG workspace 后，还需要根据 workspace 的 `settings.yaml` 梳理 GraphRAG index/query 实际使用的 LLM 和 embedding 变量。若使用 OpenAI-compatible 服务，预计至少需要 API key、base URL、chat model、embedding model；具体变量名以 `graphrag init` 生成的配置为准。

阶段 1 `ragtest` workspace 实际使用变量：

- `GRAPHRAG_API_KEY`：GraphRAG chat API key，当前使用百炼 key。
- `GRAPHRAG_API_BASE`：GraphRAG chat base URL，当前为百炼 OpenAI-compatible endpoint。
- `GRAPHRAG_MODEL_NAME`：GraphRAG chat model，当前为 `qwen-plus`。
- `GRAPHRAG_EMBEDDING_API_KEY`：GraphRAG embedding API key，当前使用百炼 key。
- `GRAPHRAG_EMBEDDING_API_BASE`：GraphRAG embedding base URL，当前为百炼 OpenAI-compatible endpoint。
- `GRAPHRAG_EMBEDDING_MODEL_NAME`：GraphRAG embedding model，当前为 `text-embedding-v3`。

注意：DeepSeek API 不用于 GraphRAG index。普通运行时回答、融合总结等非 GraphRAG index 操作可优先使用 DeepSeek。

`rag_project` Milvus/RAG 来源项目变量，来源为 `/home/aetherlens/projects/rag_project/.env` 和 `RAG_PROJECT/RAG_PROJECT/utils/env_utils.py`：

- `MILVUS_URI`：Milvus 服务地址，当前默认值为 `http://localhost:19530`。
- `COLLECTION_NAME`：Milvus collection 名，当前默认值为 `t_collection01`。
- `LLM_PROVIDER`：LLM provider，当前代码支持 `deepseek` 和 `openai`。
- `DEEPSEEK_API_KEY`：DeepSeek API key。
- `OPENAI_API_KEY`：OpenAI-compatible API key，当前 embedding 代码用于百炼兼容接口。
- `TAVILY_API_KEY`：Tavily 搜索 key，仅 web search fallback 需要。

阶段 3 已迁移到 `deepseek_agent` 的 Milvus/RAG 配置变量：

- `MILVUS_URI`：Milvus 服务地址，默认 `http://localhost:19530`。
- `MILVUS_COLLECTION_NAME`：Milvus collection 名，默认 `t_collection01`。
- `MILVUS_DENSE_DIMENSION`：dense 向量维度，默认 `1024`。
- `MILVUS_TEXT_MAX_LENGTH`：Milvus `text` 字段最大长度，默认 `6000`。
- `MILVUS_CONSISTENCY_LEVEL`：Milvus 一致性级别，默认 `Strong`。
- `MILVUS_SEARCH_TOP_K`：Milvus retriever 默认返回数量，默认 `4`。
- `MILVUS_SEARCH_SCORE_THRESHOLD`：Milvus retriever 分数阈值，默认 `0.0`。RRF 分数通常较小，不建议第一版设为 `0.1`。
- `MILVUS_RRF_K`：RRF ranker 参数，默认 `100`。
- `MILVUS_FILTER_CATEGORY`：默认检索过滤类别，默认 `content`。
- `RAG_EMBEDDING_PROVIDER`：Milvus dense embedding provider，支持 `huggingface` 或 `openai`，默认 `huggingface`。
- `RAG_EMBEDDING_MODEL`：HuggingFace embedding 模型名，默认 `BAAI/bge-large-zh-v1.5`。
- `RAG_EMBEDDING_DEVICE`：HuggingFace embedding 运行设备，默认 `cpu`。
- `RAG_EMBEDDING_NORMALIZE`：是否归一化 HuggingFace embedding，默认 `True`。
- `RAG_OPENAI_EMBEDDING_API_KEY`：OpenAI-compatible embedding API key。
- `RAG_OPENAI_EMBEDDING_BASE_URL`：OpenAI-compatible embedding base URL，默认百炼 endpoint。
- `RAG_OPENAI_EMBEDDING_MODEL`：OpenAI-compatible embedding 模型，默认 `text-embedding-v3`。

当前 shell 额外影响变量：

- `HF_ENDPOINT=https://hf-mirror.com`：会影响 Hugging Face 模型下载。阶段 0 验证中该镜像导致 `BAAI/bge-large-zh-v1.5` 下载失败；官方 `https://huggingface.co` 可达。
- `OLLAMA_MODELS=/mnt/d/ollama/models`：影响 Ollama 本地模型目录。

Neo4j 变量不是第一版必需项，但当前旧代码和 `.env` 仍包含：

- `NEO4J_URL`、`NEO4J_USERNAME`、`NEO4J_PASSWORD`、`NEO4J_DATABASE`。

第一版主流程不应依赖这些 Neo4j 变量。

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

下一位模型应从阶段 4：重写提示词与路由开始。

阶段 0、1、2、3 已通过各自验收。不要启动阶段 5，除非阶段 4 已完成并记录路由/prompt 验收结果。

## 16. 阶段 5 后配置调整：百炼 embedding 优先

执行日期：2026-06-18。

阶段 5 完成后，embedding 默认链路统一调整为百炼 OpenAI-compatible 接口：

- `EMBEDDING_TYPE=openai`。
- `EMBEDDING_MODEL=text-embedding-v3`。
- `EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`。
- `EMBEDDING_BATCH_SIZE=8`，继续规避百炼每批 input 不能超过 10 的限制。
- `RAG_EMBEDDING_PROVIDER=openai`。
- `RAG_OPENAI_EMBEDDING_MODEL=text-embedding-v3`。
- `GRAPHRAG_EMBEDDING_MODEL_NAME=text-embedding-v3`。

代码层同步调整：

- Redis semantic cache 默认使用 OpenAI-compatible embedding；Ollama 仅在显式配置 `EMBEDDING_TYPE=ollama` 时使用。
- 预定义 Cypher query matcher 默认使用 OpenAI-compatible embedding；Ollama 仅作为显式 fallback。
- 旧 PDF/FAISS `EmbeddingService` 从 `paraphrase-multilingual-MiniLM-L12-v2` 切到 `text-embedding-v3`，向量维度跟 `MILVUS_DENSE_DIMENSION=1024` 保持一致。已有 384 维 FAISS 索引需要重建。
- Milvus dense embedding 默认使用 `langchain_openai.OpenAIEmbeddings` + 百炼 endpoint。
- GraphRAG 主 workspace 和 `ragtest` workspace 均通过 `GRAPHRAG_EMBEDDING_*` 变量使用百炼 embedding。

Ollama 不再作为默认优先级。当前保留 `OLLAMA_*` 变量只用于显式选择 Ollama 或本地 fallback。

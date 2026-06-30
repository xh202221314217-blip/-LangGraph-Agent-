# DeepSeek Agent Markdown Knowledge RAG

基于 FastAPI + LangGraph 的 Markdown 技术文档问答应用。当前第一版知识路径组合了：

- GraphRAG CLI，用于图风格的本地/全局文档推理。
- Milvus 稠密+稀疏混合检索，用于提供源文档分块证据。
- 兼容 DeepSeek 的聊天模型，用于路由、普通对话和最终的有依据回答。

旧的电商 Neo4j 知识图谱代码仅作为历史参考保留在 `llm_backend/app/lg_agent/kg_sub_graph` 下；它不属于当前活跃的运行路径。

## 启动项目

需要先准备 `llm_backend/.env`，可从 `llm_backend/.env.example` 复制后填写模型 Key、MySQL、Redis、Milvus 等配置。

需要启动的容器由 `docker-compose.yml` 管理：

```text
mysql              MySQL，localhost:3307
redis              Redis，localhost:6379
milvus-etcd        Milvus 依赖
milvus-minio       Milvus 依赖，localhost:9000/9001
milvus-standalone  Milvus，localhost:19530 和 localhost:9091
```

启动容器：

```bash
cd /home/aetherlens/projects/deepseek_agent
docker compose --env-file llm_backend/.env up -d
```

`--env-file llm_backend/.env` 用来让 Compose 读取 `DB_PORT`、`DB_PASSWORD`、`DB_NAME` 等数据库配置。仓库里的 Neo4j 只给旧知识图谱代码保留，默认不会启动。

首次创建数据库表，或需要清空并重建表时，再运行：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python llm_backend/scripts/init_db.py
```

`init_db.py` 会先删除再创建表，不需要每次启动都执行。数据库表已经存在时，直接启动服务即可。

普通启动方式：

```bash
cd /home/aetherlens/projects/deepseek_agent/llm_backend
../.venv/bin/python run.py
```

已验证也可以用 `uv` 启动：

```bash
cd /home/aetherlens/projects/deepseek_agent/llm_backend
uv run --with-requirements ../requirements.txt uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir .
```

启动后访问：

- 前端：`http://localhost:8000`
- 健康检查：`http://localhost:8000/health`
- API 文档：`http://localhost:8000/docs`

## 当前运行路径

1. 前端将用户问题发送到 `POST /api/langgraph/query`。
2. `llm_backend/app/lg_agent/lg_builder.py` 对请求进行路由。
3. 知识库问题调用 `llm_backend/app/lg_agent/knowledge_fusion.py`。
4. Fusion 并发查询：
   - `app.graphrag_cli.GraphRAGCLIRetriever`
   - `app.rag_retrieval.MilvusHybridRetriever`
5. 最终答案基于融合后的 GraphRAG 文本和 Milvus 文档证据生成。

本版本不需要 Neo4j、Cypher 生成，以及电商产品/订单/客户流程。

## 环境搭建

```bash
cd /home/aetherlens/projects/deepseek_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

根据 `llm_backend/.env.example` 创建 `llm_backend/.env`，并填写本地密钥、数据库设置和 Milvus 设置。

完整知识路径所需的最少服务：

- MySQL，供现有会话/用户服务使用。
- Milvus，地址为 `MILVUS_URI`，默认 `http://localhost:19530`。
- Redis，如果启用了语义缓存功能。
- 用于 DeepSeek 聊天和 DashScope/百炼 embedding 的 OpenAI 兼容 API。

## 环境说明

测试工作区的 GraphRAG 索引/查询使用工作区设置中的 OpenAI 兼容 DashScope/百炼变量：

- `GRAPHRAG_API_KEY`
- `GRAPHRAG_API_BASE`
- `GRAPHRAG_MODEL_NAME`
- `GRAPHRAG_EMBEDDING_API_KEY`
- `GRAPHRAG_EMBEDDING_API_BASE`
- `GRAPHRAG_EMBEDDING_MODEL_NAME`

Milvus 稠密 embedding 使用：

- `RAG_EMBEDDING_PROVIDER=openai`
- `RAG_OPENAI_EMBEDDING_API_KEY`
- `RAG_OPENAI_EMBEDDING_BASE_URL`
- `RAG_OPENAI_EMBEDDING_MODEL=text-embedding-v3`

仍然支持 `RAG_EMBEDDING_PROVIDER=huggingface`，但需要已缓存配置的模型，或可用的 Hugging Face endpoint。在此环境中，`HF_ENDPOINT=https://hf-mirror.com` 之前加载 `BAAI/bge-large-zh-v1.5` 失败过。

## 启动 FastAPI

```bash
cd /home/aetherlens/projects/deepseek_agent/llm_backend
../.venv/bin/python run.py
```

默认 URL：

- 前端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

## GraphRAG 工作区索引

小型测试工作区为：

```text
llm_backend/app/graphrag_workspaces/ragtest
```

为现有工作区输入建立索引：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_cli.index_workspace \
  --root llm_backend/app/graphrag_workspaces/ragtest \
  --method standard \
  --timeout 3600
```

索引前将 Markdown 文件复制到工作区：

```bash
PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_cli.index_workspace \
  --root llm_backend/app/graphrag_workspaces/ragtest \
  --md-dir /home/aetherlens/projects/rag_project/md/md \
  --limit 5 \
  --clear-input \
  --method standard \
  --timeout 3600
```

GraphRAG `standard` 索引可能较慢。stage-7 的五文件样本耗时约 1963 秒。

## GraphRAG 查询冒烟测试

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m app.graphrag_cli.smoke \
  --method local \
  --query "GAAFET 相比 FinFET 的关键优势是什么？" \
  --timeout 180
```

可通过以下变量配置 wrapper：

- `GRAPHRAG_CLI_PATH`
- `GRAPHRAG_CLI_WORKSPACE_ROOT`
- `GRAPHRAG_CLI_DEFAULT_METHOD`
- `GRAPHRAG_CLI_RESPONSE_TYPE`
- `GRAPHRAG_CLI_TIMEOUT_SECONDS`

## Milvus Markdown 导入

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m app.rag_ingest.write_milvus \
  --md-dir llm_backend/app/graphrag_workspaces/ragtest/input \
  --batch-size 20
```

常用参数：

- `--drop-existing` 重新创建已配置的 collection。
- `--limit N` 仅导入前 N 个 Markdown 文件。
- `--skip-semantic-chunking` 使用 Markdown fallback parser，不进行语义分块。

## FastAPI 知识查询

服务器运行后：

```bash
curl -N -X POST http://localhost:8000/api/langgraph/query \
  -F 'query=GAAFET 相比 FinFET 的关键优势是什么？' \
  -F 'user_id=1'
```

响应格式为 Server-Sent Events。前端使用同一个 endpoint。

## 可重复冒烟检查

不调用外部 LLM API 的快速本地检查：

```bash
cd /home/aetherlens/projects/deepseek_agent
PYTHONPATH=llm_backend .venv/bin/python -m app.smoke.merged_rag_smoke
```

该命令验证：

- GraphRAG CLI help 可用，并暴露 `local|global|drift|basic`。
- 活跃 Python 包可编译。
- 活跃的 LangGraph prompt/builder 文件不会导入或引用旧 KG 运行路径。
- 静态前端是 Markdown 知识库客户端。
- 已废弃的 `/chat-rag` 路由不再调用已移除的 `RAGChatService`。

完整外部检查仍然是上面的三个命令：GraphRAG 查询冒烟测试、Milvus 导入，以及 FastAPI `/api/langgraph/query`。

## 依赖说明

`deepseek_agent` 现在拥有迁移后的 RAG 代码。运行时不再导入 `/home/aetherlens/projects/rag_project` 源模块。

从 RAG 合并中新增的依赖：

- `graphrag==2.1.0`
- `langchain-experimental>=0.3.4,<0.4.0`
- `langchain-huggingface>=0.1.2,<1.0.0`
- `langchain-milvus>=0.1.8,<0.2.0`
- `pymilvus>=2.5.0,<2.6.0`
- `unstructured[md]>=0.15.0,<0.16.0`

由于仓库中仍保留历史模块，`langchain_neo4j` 等旧 KG 依赖仍然安装。活跃的 GraphRAG + Milvus 路径不需要它们。

## 旧代码边界

历史 Neo4j/Cypher 模块保留在：

```text
llm_backend/app/lg_agent/kg_sub_graph
```

除非项目明确重新开启 Neo4j 支持，否则不要将这些模块接入第一版运行时。活跃的第一版路径是 `GraphRAG CLI + Milvus hybrid RAG`。

## 上传行为

`POST /api/upload` 会保存文件并返回推荐的 CLI 命令。它不会运行 GraphRAG 索引或 Milvus 导入，因为二者都可能是长时间运行的操作。请使用文档中的 CLI 命令完成导入。

# GraphRAG 可选开关执行文档

## 0. 任务目标

在当前分支 `feat/graphrag-delect` 中增加后端配置开关：

```env
USE_GRAPHRAG=True
```

最终行为：

- `USE_GRAPHRAG=True`：保持当前行为，同时执行 GraphRAG CLI 查询和 Milvus hybrid 检索。
- `USE_GRAPHRAG=False`：停用运行时 GraphRAG 查询，只执行 Milvus hybrid 检索。

关闭 GraphRAG 时，不能启动 `graphrag query` 子进程，不能因为 GraphRAG CLI 路径、workspace、API key 缺失导致知识库问答失败。

## 1. 不做的事

- 不删除 GraphRAG 代码、依赖、workspace、历史文档。
- 不改上传、索引、Milvus 入库逻辑。
- 不加前端开关。
- 不重命名 `graphrag-query` 路由类型。第一版先让它继续代表“本地知识库查询”。

## 2. 当前代码入口

- 后端配置：`llm_backend/app/core/config.py`
- 环境变量样例：`llm_backend/.env.example`
- 查询融合：`llm_backend/app/lg_agent/knowledge_fusion.py`
- LangGraph 知识库节点：`llm_backend/app/lg_agent/lg_builder.py:create_research_plan`
- GraphRAG CLI wrapper：`llm_backend/app/graphrag_cli/*`
- Milvus hybrid retriever：`llm_backend/app/rag_retrieval/*`

## 3. Agent A：配置开关

### 输入

现有配置文件：

- `llm_backend/app/core/config.py`
- `llm_backend/.env.example`

### 修改步骤

1. 在 `llm_backend/app/core/config.py` 的 `Settings` 中增加：

```python
USE_GRAPHRAG: bool = True
```

2. 在 `llm_backend/.env.example` 的 GraphRAG 配置前或附近增加：

```env
# Runtime knowledge retrieval switch
USE_GRAPHRAG=True
```

3. 不修改真实 `llm_backend/.env`，除非执行人需要本地手动验证。

### 验收

运行：

```bash
PYTHONPATH=llm_backend .venv/bin/python - <<'PY'
from app.core.config import settings
print(settings.USE_GRAPHRAG)
PY
```

预期默认输出：

```text
True
```

## 4. Agent B：融合检索器开关

### 输入

文件：

- `llm_backend/app/lg_agent/knowledge_fusion.py`

### 修改步骤

1. 引入配置：

```python
from app.core.config import settings
```

2. 给 `HybridKnowledgeRetriever.__init__` 增加参数：

```python
use_graphrag: bool = settings.USE_GRAPHRAG
```

3. 保存开关，只在开启时创建 GraphRAG retriever：

```python
self.use_graphrag = use_graphrag
self.graphrag_retriever = (
    graphrag_retriever or GraphRAGCLIRetriever()
) if use_graphrag else None
```

4. 修改 `retrieve()`：

- `self.use_graphrag=True` 时，沿用当前 GraphRAG + Milvus 两个 task 的并发逻辑。
- `self.use_graphrag=False` 时，只执行 Milvus task。
- GraphRAG 关闭是正常状态，不向 `errors` 增加“GraphRAG 已关闭”。

5. 修改 `_query_graphrag()`：

如果类型检查需要，给 `self.graphrag_retriever is None` 加一个防御性异常。该异常不应在关闭路径触发，因为关闭路径不会调用 `_query_graphrag()`。

### 验收

写一个最小自检脚本或测试，构造假的 Milvus retriever：

```python
from langchain_core.documents import Document
from app.lg_agent.knowledge_fusion import HybridKnowledgeRetriever

class FakeMilvus:
    def search(self, question):
        return [Document(page_content="milvus ok", metadata={"source": "test"})]

async def main():
    retriever = HybridKnowledgeRetriever(
        use_graphrag=False,
        milvus_retriever=FakeMilvus(),
    )
    result = await retriever.retrieve("test question")
    assert result.graphrag_text == ""
    assert len(result.milvus_documents) == 1
    assert "GraphRAG CLI 结果" not in result.to_context()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

预期：脚本无异常退出。

## 5. Agent C：返回步骤标记

### 输入

文件：

- `llm_backend/app/lg_agent/lg_builder.py`

### 修改步骤

1. 确认文件中可访问 `settings`。如果未导入，增加：

```python
from app.core.config import settings
```

2. 在 `create_research_plan()` 返回前生成真实步骤：

```python
steps = ["milvus_hybrid_search", "fusion_answer"]
if settings.USE_GRAPHRAG:
    steps.insert(0, "graphrag_cli_query")
```

3. 把返回值里的固定 steps：

```python
"steps": ["graphrag_cli_query", "milvus_hybrid_search", "fusion_answer"]
```

替换为：

```python
"steps": steps
```

### 验收

代码检查即可：

- `USE_GRAPHRAG=True` 时 steps 包含 `graphrag_cli_query`。
- `USE_GRAPHRAG=False` 时 steps 不包含 `graphrag_cli_query`。

## 6. Agent D：集成验证

### 前置

Milvus 已启动，且目标 collection 已导入 Markdown 文档。

### 验证 1：GraphRAG 开启

配置：

```env
USE_GRAPHRAG=True
```

执行知识库问答接口，例如项目已有的 `/api/langgraph/query` 调用方式。

预期：

- 日志出现 GraphRAG 检索记录。
- 日志出现 Milvus hybrid 检索记录。
- 返回 `steps` 包含 `graphrag_cli_query`、`milvus_hybrid_search`、`fusion_answer`。
- GraphRAG 有结果时，`documents` 包含 `## GraphRAG CLI 结果`。

### 验证 2：GraphRAG 关闭

配置：

```env
USE_GRAPHRAG=False
```

执行同一个知识库问答接口。

预期：

- 不启动 `graphrag query`。
- 日志不出现 GraphRAG CLI 查询成功或失败记录。
- 日志出现 Milvus hybrid 检索记录。
- 返回 `steps` 只包含 `milvus_hybrid_search`、`fusion_answer`。
- `documents` 不包含 `## GraphRAG CLI 结果`。
- 即使 GraphRAG workspace 或 CLI 路径不可用，请求也不因此失败。

## 7. 推荐执行顺序

1. Agent A 先做配置开关。
2. Agent B 做核心检索逻辑。
3. Agent C 做返回步骤标记。
4. Agent D 做集成验证。

Agent B 和 Agent C 都依赖 Agent A 的 `settings.USE_GRAPHRAG`。Agent D 必须最后执行。

## 8. 最终验收标准

功能完成必须同时满足：

- `.env.example` 有 `USE_GRAPHRAG=True`。
- `Settings` 有 `USE_GRAPHRAG: bool = True`。
- `USE_GRAPHRAG=False` 时不会创建或调用 `GraphRAGCLIRetriever`。
- `USE_GRAPHRAG=False` 时知识库问答仍能用 Milvus hybrid 生成回答。
- `steps` 反映真实执行路径。
- 没有提交真实 `.env`。

## 9. 风险

- 关闭 GraphRAG 后，回答质量完全依赖 Milvus collection 的导入质量。
- `graphrag-query` 路由名会继续存在，可能造成命名误解；后续确实需要清理时再统一改为 `knowledge-query`。


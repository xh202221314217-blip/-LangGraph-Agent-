from typing import Any, Callable, Coroutine, Dict, List
import asyncio
import os
from pathlib import Path
from pydantic import BaseModel, Field

# 导入GraphRAG相关模块
import app.graphrag.graphrag.api as api
from app.graphrag.graphrag.config.load_config import load_config
from app.graphrag.graphrag.callbacks.noop_query_callbacks import NoopQueryCallbacks
from app.graphrag.graphrag.utils.storage import load_table_from_storage
from app.graphrag.graphrag.storage.file_pipeline_storage import FilePipelineStorage
from app.lg_agent.kg_sub_graph.kg_neo4j_conn import get_neo4j_graph
from app.core.logger import get_logger
from langchain_deepseek import ChatDeepSeek
from app.core.config import settings
from app.lg_agent.kg_sub_graph.agentic_rag_agents.retrievers.cypher_examples.northwind_retriever import NorthwindCypherRetriever
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.cypher_tools.utils import create_text2cypher_generation_node, create_text2cypher_validation_node, create_text2cypher_execution_node



# 获取日志记录器
logger = get_logger(service="cypher_tools")

def create_deepseek_model(tags: List[str] | None = None):
    """Create the model used by Text2Cypher requests."""
    return ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        model_name=settings.DEEPSEEK_MODEL,
        temperature=0.7,
        tags=tags or [],
    )

# 定义GraphRAG查询的输入状态类型
class CypherQueryInputState(BaseModel):
    task: str
    query: str
    steps: List[str]

# 定义GraphRAG查询的输出状态类型
class CypherQueryOutputState(BaseModel):
    task: str
    query: str
    errors: List[str]
    records: Dict[str, Any]
    steps: List[str]


def _is_schema_query(query: str) -> bool:
    schema_terms = ("schema", "模式", "图谱结构", "数据库结构", "节点标签", "关系类型")
    return any(term in query for term in schema_terms)


def _query_graph_schema(neo4j_graph) -> Dict[str, Any]:
    labels = [
        row["label"]
        for row in neo4j_graph.query(
            "CALL db.labels() YIELD label RETURN label ORDER BY label"
        )
    ]
    relationship_types = [
        row["relationshipType"]
        for row in neo4j_graph.query(
            "CALL db.relationshipTypes() YIELD relationshipType "
            "RETURN relationshipType ORDER BY relationshipType"
        )
    ]
    product_supplier_relationships = neo4j_graph.query(
        "MATCH (p:Product)-[r]->(s:Supplier) "
        "RETURN DISTINCT 'Product' AS start_node, type(r) AS relationship, "
        "'Supplier' AS end_node ORDER BY relationship"
    )

    return {
        "node_labels": labels,
        "relationship_types": relationship_types,
        "product_supplier_relationships": product_supplier_relationships,
    }

# 定义GraphRAG API包装器

def create_cypher_query_node(
) -> Callable[
    [CypherQueryInputState],
    Coroutine[Any, Any, Dict[str, List[CypherQueryOutputState] | List[str]]],
]:
    """
    创建 Text2Cypher 查询节点，用于LangGraph工作流。

    返回
    -------
    Callable[[CypherQueryInputState], Dict[str, List[CypherQueryOutputState] | List[str]]]
        名为`cypher_query`的LangGraph节点。
    """

    async def cypher_query(
        state: Dict[str, Any],
    ) -> Dict[str, List[CypherQueryOutputState] | List[str]]:
        """
        执行Text2Cypher查询并返回结果。
        """
        errors = list()
        # 获取查询文本
        query = state.get("task", "")  #task问题
        if not query:
            errors.append("未提供查询文本")
 
        model = create_deepseek_model(tags=["research_plan"])

        # 2. 获取Neo4j图数据库连接
        neo4j_graph = None
        try:
            neo4j_graph = get_neo4j_graph()
            logger.info("success to get Neo4j graph database connection")
        except Exception as e:
            logger.error(f"failed to get Neo4j graph database connection: {e}")
            errors.append("无法连接Neo4j图数据库")
            return {
                "cyphers": [
                    CypherQueryOutputState(
                        **{
                            "task": state.get("task", ""),
                            "query": query,
                            "errors": errors,
                            "records": {"result": []},
                            "steps": ["execute_cypher_query"],
                        }
                    )
                ],
                "steps": ["execute_cypher_query"],
            }

        if _is_schema_query(query):
            try:
                schema_records = _query_graph_schema(neo4j_graph)
            except Exception as e:
                errors.append(f"查询Neo4j schema失败: {e}")
                schema_records = {"result": []}

            return {
                "cyphers": [
                    CypherQueryOutputState(
                        **{
                            "task": state.get("task", ""),
                            "query": query,
                            "errors": errors,
                            "records": {"schema": schema_records},
                            "steps": ["execute_cypher_query"],
                        }
                    )
                ],
                "steps": ["execute_cypher_query"],
            }

        # step 2. 创建自定义检索器实例，根据 Graph Schema 创建 Cypher 示例，用来引导大模型生成正确的Cypher 查询语句
        cypher_retriever = NorthwindCypherRetriever()

        # Step 3.根据自定义的 Cypher 示例，引导大模型生成 当前输入 问题的 Cypher 查询语句
        cypher_generation = create_text2cypher_generation_node(
            llm=model, graph=neo4j_graph, cypher_example_retriever=cypher_retriever
        )

        cypher_result = await cypher_generation(state)
        #  TODO: Example 1. 直接使用大模型生成 Cypher 查询语句        #这段代码的作用是什么
        """
        # 安装依赖
        pip install neo4j-graphrag
        
        from neo4j_graphrag.retrievers import Text2CypherRetriever
        from neo4j_graphrag.llm import OpenAILLM
        import time
        import pandas as pd
        from neo4j import GraphDatabase

        NEO4J_URI="bolt://localhost"
        NEO4J_USERNAME="neo4j"
        NEO4J_PASSWORD="g1601522830"
        NEO4J_DATABASE="neo4j"

        driver = GraphDatabase.driver(
            NEO4J_URI, 
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
            )

        # 这里可以填写 DeepSeek 模型
        client = OpenAILLM(api_key="", base_url="https://api.deepseek.com", model_name='deepseek-chat')

        
        # 定义用户输入：
        examples = [
        "USER INPUT: 'Which actors starred in the Matrix?' QUERY: MATCH (p:Person)-[:ACTED_IN]->(m:Movie) WHERE m.title = 'The Matrix' RETURN p.name"
        ]

        # 初始化检索器
        retriever = Text2CypherRetriever(
            driver=driver,
            llm=client,
            neo4j_schema=neo4j_schema,  # 可以通过 retrieve_and_parse_schema_from_graph_for_prompts 获取动态的Schema
            examples=examples,
        )

        
        # 执行检索：
        query_text = "juju 都有哪些朋友？"
        print(retriever.search(query_text=query_text))
        """

        # step 4. 验证生成的 Cypher 查询语句是否正确
        validate_cypher = create_text2cypher_validation_node(
            llm=model,
            graph=neo4j_graph,
            llm_validation=True,
            cypher_statement=cypher_result
        )

        # step 5. 获取执行Cypher查询的全部信息
        execute_info = await validate_cypher(state=state) #由于不在agent流程中，因此return不会进入主state。

        # step 6. 执行 Cypher 查询语句
        execute_cypher = create_text2cypher_execution_node(
            graph=neo4j_graph, cypher=execute_info
        )

        final_result = await execute_cypher(state) #由于不在agent流程中，因此return不会进入主state。

        # 封装 单次子任务执行的 输出结果并通过Pydantic模型限定格式
        return {
            "cyphers": [
                CypherQueryOutputState(
                        **{
                            "task": state.get("task", ""),
                            "query": query,
                            "statement": "",
                            "parameters":"",
                            "errors": errors,
                            "records": {"result": final_result["cyphers"][0]["records"]} if final_result.get("cyphers") and len(final_result["cyphers"]) > 0 else {"result": []},
                            "steps": ["execute_cypher_query"],
                        }
                    )
                ],
                "steps": ["execute_cypher_query"],
            }
  
    return cypher_query


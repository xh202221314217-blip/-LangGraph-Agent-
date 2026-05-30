from typing import Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_neo4j import Neo4jGraph
from langgraph.constants import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph
from pydantic import BaseModel

# 导入输入输出状态定义
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.state import (
    InputState,
    OutputState,
    OverallState,
)
# 导入guardrails逻辑
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.guardrails.node import create_guardrails_node
# 导入分解节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.planner import create_planner_node
# 导入工具选择节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.tool_selection import create_tool_selection_node
# 导入 text2cypher 节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.cypher_tools import create_cypher_query_node
# 导入Cypher示例检索器基类
from app.lg_agent.kg_sub_graph.agentic_rag_agents.retrievers.cypher_examples.base import BaseCypherExampleRetriever
# 导入预定义Cypher节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.predefined_cypher import create_predefined_cypher_node
# 导入自定义工具函数节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.customer_tools import create_graphrag_query_node



from ...components.errors import create_error_tool_selection_node
from ...components.final_answer import create_final_answer_node



from ...components.summarize import create_summarization_node



from .edges import (
    guardrails_conditional_edge,
    map_reduce_planner_to_tool_selection,
)

from dataclasses import dataclass, field
# 强制要求数据类中的所有字段必须以关键字参数的形式提供。即不能以位置参数的方式传递。
@dataclass(kw_only=True)
class AgentState(InputState):
    """The router's classification of the user's query."""
    steps: list[str] = field(default_factory=list)
    """Populated by the retriever. This is a list of documents that the agent can reference."""
    question: str = field(default_factory=str) # 这个参数用来与子图进行交互
    answer: str = field(default_factory=str)  # 这个参数用来与子图进行交互


def create_multi_tool_workflow(
    llm: BaseChatModel,
    graph: Neo4jGraph,
    tool_schemas: List[type[BaseModel]],
    predefined_cypher_dict: Dict[str, str],
    cypher_example_retriever: BaseCypherExampleRetriever,
    scope_description: Optional[str] = None,
    llm_cypher_validation: bool = True,
    max_attempts: int = 3,
    attempt_cypher_execution_on_final_attempt: bool = False,
    default_to_text2cypher: bool = True,
) -> CompiledStateGraph:
    """
创建一个基于 LangGraph 的多工具 Agent 工作流。

该工作流允许 Agent 从多个工具中进行选择，
并完成每一个识别出的任务。

参数
-------
llm : BaseChatModel
    用于处理任务的大语言模型（LLM）。

graph : Neo4jGraph
    Neo4j 图数据库包装器。

tool_schemas : List[BaseModel]
    一个由 Pydantic 类组成的列表，
    用于定义可用工具的 Schema。

predefined_cypher_dict : Dict[str, str]
    一个 Python 字典：
    - key：Cypher 查询名称
    - value：对应的 Cypher 查询语句

scope_description : Optional[str], optional
    应用范围的简短描述。
    默认为 None。

cypher_example_retriever : BaseCypherExampleRetriever
    用于收集 Cypher 示例的检索器，
    通常用于 Few-shot Prompting。

llm_cypher_validation : bool, optional
    是否使用提供的 LLM 对生成的 Cypher 进行校验。
    默认为 True。

max_attempts : int, optional
    允许生成有效 Cypher 的最大尝试次数。
    默认为 3。

attempt_cypher_execution_on_final_attempt : bool, optional
    ⚠️ 该选项可能存在危险。

    是否在最后一次尝试时强制执行 Cypher，
    即使 Cypher 中可能仍然包含错误。
    
    默认为 False。

default_to_text2cypher : bool, optional
    当 LLM 没有返回任何工具调用时，
    是否默认尝试执行 Text2Cypher。
    
    默认为 True。

initial_state : Optional[InputState], optional
    从父图（Parent Graph）传入的初始状态。
    
    默认为 None。

返回
-------
CompiledStateGraph
    编译后的工作流对象。
"""
    # 1. 创建guardrails节点
    # Guardrails 节点决定传入的问题是否在检索的范围内（比如是否和电商（自家的产品相关））。如果不在，则提供默认消息，并且工作流路由到最终的答案生成。
    guardrails = create_guardrails_node(
        llm=llm, graph=graph, scope_description=scope_description
    )

    # 2. 如果通过guardrails，则会针对用户的问题进行任务分解
    planner = create_planner_node(llm=llm)

    # 3. 创建cypher_query节点，用来根据用户的问题生成Cypher查询语句
    cypher_query = create_cypher_query_node()

    predefined_cypher = create_predefined_cypher_node(
        graph=graph, predefined_cypher_dict=predefined_cypher_dict
    )

    customer_tools = create_graphrag_query_node()

    # 工具选择节点，根据用户的问题选择合适的工具
    tool_selection = create_tool_selection_node(
        llm=llm,
        tool_schemas=tool_schemas,
        default_to_text2cypher=default_to_text2cypher,
    )
    summarize = create_summarization_node(llm=llm)

    final_answer = create_final_answer_node()

    # 创建状态图
    main_graph_builder = StateGraph(OverallState, input=InputState, output=OutputState)

    main_graph_builder.add_node(guardrails)
    main_graph_builder.add_node(planner)
    main_graph_builder.add_node("cypher_query", cypher_query)
    main_graph_builder.add_node(predefined_cypher)
    main_graph_builder.add_node("customer_tools", customer_tools)
    main_graph_builder.add_node(summarize)
    main_graph_builder.add_node(tool_selection)
    main_graph_builder.add_node(final_answer)


    # 添加边
    main_graph_builder.add_edge(START, "guardrails")
    main_graph_builder.add_conditional_edges(
        "guardrails",
        guardrails_conditional_edge,
    )
    main_graph_builder.add_conditional_edges(
        "planner",
        map_reduce_planner_to_tool_selection,  # type: ignore[arg-type, unused-ignore]
        ["tool_selection"],
    )

    main_graph_builder.add_edge("cypher_query", "summarize")
    main_graph_builder.add_edge("predefined_cypher", "summarize")
    main_graph_builder.add_edge("customer_tools", "summarize")
    main_graph_builder.add_edge("summarize", "final_answer")

    main_graph_builder.add_edge("final_answer", END)

    return main_graph_builder.compile()


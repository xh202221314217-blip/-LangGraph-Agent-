from typing import Any, Callable, Coroutine, Dict, List

from langchain_neo4j import Neo4jGraph
from langchain_core.language_models import BaseChatModel

from app.lg_agent.kg_sub_graph.agentic_rag_agents.constants import NO_CYPHER_RESULTS
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.state import PredefinedCypherInputState
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.text2cypher.state import CypherOutputState
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.predefined_cypher.utils import create_vector_query_matcher
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.predefined_cypher.descriptions import QUERY_DESCRIPTIONS


def create_predefined_cypher_node(
    graph: Neo4jGraph, predefined_cypher_dict: Dict[str, str]
) -> Callable[
    [PredefinedCypherInputState],
    Coroutine[Any, Any, Dict[str, List[CypherOutputState] | List[str]]],
]:
    """
    Create a predefined Cypher execution node for a LangGraph workflow.

    Parameters
    ----------
    graph : Neo4jGraph
        The Neo4j graph wrapper.
    predefined_cypher_dict : Dict[str, str]
        A Python dictionary with Cypher query names as keys and parameterized Cypher queries as values.

    Returns
    -------
    Callable[[PredefinedCypherInputState], Dict[str, List[CypherOutputState] | List[str]]]
        The LangGraph node named `predefined_cypher`.
    """
    async def predefined_cypher(
        state: PredefinedCypherInputState,
    ) -> Dict[str, List[CypherOutputState] | List[str]]:
        """
        Executes a predefined Cypher statement with found parameters.
        """
        errors = list()

        statement_name = state.get("query_name", "")  #工具名称
        params = state.get(  #工具参数
            "query_parameters", dict()
        )  
        """
        {
            "query": "product_by_category",
            "parameters": {
                "category_name": "智能音箱"
            }
        }
        """
        print("statement_name", statement_name)
        print("params", params)
        
        # 将parameters中的每个值转换为字符串
        parameters = params.get("parameters", {})
        """
        parameters = {
            "category_name": "智能音箱"
        }
        """

        for key, value in parameters.items():
            parameters[key] = str(value)
        
        statement = predefined_cypher_dict.get(params.get("query"))   #这里实际就是工具调用
        """
        (
            "MATCH (p:Product)-[:BELONGS_TO]->(c:Category) "
            "WHERE c.CategoryName = $category_name "
            "RETURN p.ProductName, p.UnitPrice, p.UnitsInStock"
        )
        """

        print("statement", statement)
        if statement is not None:
            records = graph.query(query=statement, params=parameters)  #这里实际就是工具调用
            print(f"records: {records}")
            
        else:
            errors.append(
                f"Unable to find the specified Cypher statement: {statement_name}"
            )
            records = list()

        return {
            "cyphers": [
                CypherOutputState(
                    **{
                        "task": state.get("task", ""),
                        "statement": statement or "",
                        "parameters": params,
                        "errors": errors,
                        "records": records or NO_CYPHER_RESULTS,
                        "steps": ["execute_predefined_cypher"],
                    }
                )
            ],
            "steps": ["execute_predefined_cypher"],
        }

    return predefined_cypher

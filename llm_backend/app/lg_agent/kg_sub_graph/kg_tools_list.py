from pydantic import BaseModel
from pydantic import Field


class cypher_query(BaseModel):
    """如果用户问的是关于产品价格、库存、规格等，则使用这个工具，生成Cypher查询语句进行查询"""

    task: str = Field(..., description="The task the Cypher query must answer.")

class predefined_cypher(BaseModel):
    """这个工具包含预定义的Cypher查询语句，用于快速响应各种电商场景的查询需求。
    根据用户问题的类型，可以选择以下类别的查询：
    1. 产品类查询：
       - product_by_name: 通过产品名称查询产品信息
       - product_by_category: 通过类别名称查询该类别下的所有产品
       - product_by_supplier: 查询特定供应商提供的所有产品
       - products_low_stock: 查询库存不足的产品
       - products_popular: 查询最受欢迎(评论最多)的产品
    2. 客户类查询：
       - customer_by_name: 通过名称查询客户信息
       - customer_orders: 查询特定客户的所有订单
       - customer_purchase_history: 查询特定客户的购买历史
    3. 订单类查询：
       - order_by_id: 通过订单ID查询订单信息
       - order_details: 查询特定订单的详细信息(包含的产品)
       - recent_orders: 查询最近的订单
       - delayed_orders: 查询延迟发货的订单
    4. 供应商类查询：
       - supplier_by_country: 查询特定国家的供应商
       - supplier_products: 查询特定供应商提供的所有产品
       - suppliers_by_category: 查询生产或供应某个类别产品的公司
    5. 类别类查询：
       - all_categories: 查询所有产品类别
       - category_products: 查询特定类别下的所有产品
       - category_product_count: 查询每个类别包含的产品数量
    6. 员工类查询：
       - employee_by_name: 通过姓名查询员工信息
       - employee_processed_orders: 查询特定员工处理的所有订单
    7. 评论类查询：
       - product_reviews: 查询特定产品的所有评论
       - top_rated_products: 查询评分最高的产品
    8. 销售分析类查询：
       - product_sales: 查询特定产品的总销售额
       - category_sales: 查询各类别的总销售额
       - monthly_sales: 查询每月的销售情况
    9. 智能家居相关查询：
       - smart_home_products: 查询所有智能家居产品
       - smart_speakers: 查询智能音箱类产品
       - smart_lighting: 查询智能灯具类产品及其供应公司
    请根据用户的问题选择最合适的查询，并根据需要替换查询中的参数值（如$product_name, $category_name等）。
    """
    query: str = Field(..., description="query the graph must include the question")
    parameters: dict = Field(..., description="parameters for the query to Neo4j")

class microsoft_graphrag_query(BaseModel):
    """如果用户问的问题是关于产品的故障、售后、保修、维修、退换货以及评价等，则使用这个工具"""
    query: str = Field(..., description="query the graph must include the question")
    

class real_time_network_query(BaseModel):
    """如果用户问的问题是关于一些实时的产品有效信息需要联网检索的话，则使用这个工具"""
    query: str = Field(..., description="query the network must include the question")


'''
解释tool使用方法：llm中使用bind_tools()绑定这些schema后，当用户输入一个问题时，LLM会根据问题的内容和上下文来判断应该使用哪个工具来处理这个问题。
LLM会分析用户的问题，识别出其中的关键词和意图，然后选择最合适的工具来生成查询语句或进行网络检索。
具体的：schema的类名会成为工具的名称，属性会成为工具的输入参数。
假设llm决定使用predefined_cypher工具，其返回的AImessage是：
AIMessage(
    tool_calls=[
        {
            "name": "predefined_cypher",
            "args": {
                "query": "product_by_name",
                "parameters": {
                    "product_name": "智能音箱"  #该参数由模型推理得出
                }
            }
        }
    ]
)
'''

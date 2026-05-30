@echo off

REM Neo4j Admin导入命令
REM 适用于Neo4j 2025.02.0及更高版本
REM 生成时间: 2026-05-13 17:01:14

neo4j-admin database import full neo4j --overwrite-destination ^
  --nodes=Product="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/product_nodes.csv" ^
  --nodes=Category="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/category_nodes.csv" ^
  --nodes=Supplier="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/supplier_nodes.csv" ^
  --nodes=Customer="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/customer_nodes.csv" ^
  --nodes=Employee="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/employee_nodes.csv" ^
  --nodes=Shipper="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/shipper_nodes.csv" ^
  --nodes=Order="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/order_nodes.csv" ^
  --nodes=Review="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/review_nodes.csv" ^
  --relationships=BELONGS_TO="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/product_category_edges.csv" ^
  --relationships=SUPPLIED_BY="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/product_supplier_edges.csv" ^
  --relationships=PLACED="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/customer_order_edges.csv" ^
  --relationships=PROCESSED="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/employee_order_edges.csv" ^
  --relationships=SHIPPED_VIA="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/order_shipper_edges.csv" ^
  --relationships=CONTAINS="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/order_product_edges.csv" ^
  --relationships=REPORTS_TO="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/employee_reports_to_edges.csv" ^
  --relationships=WROTE="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/customer_review_edges.csv" ^
  --relationships=ABOUT="/home/aetherlens/projects/deepseek_agent/llm_backend/app/graphrag/origin_data/data/neo4j_admin/review_product_edges.csv" ^
  --delimiter="," ^
  --array-delimiter=";" ^
  --skip-bad-relationships=true ^
  --skip-duplicate-nodes=true

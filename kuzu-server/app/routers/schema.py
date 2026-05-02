from fastapi import APIRouter

from app.db import get_db
from app.models import SchemaNodeTable, SchemaRelTable, SchemaResponse

router = APIRouter()


@router.get(
    "/schema",
    response_model=SchemaResponse,
    summary="获取完整数据库 Schema",
    description="返回数据库中所有节点表和边表的完整定义，包含每张表的属性名和类型。"
                "边表额外包含起点表名(src)和终点表名(dst)信息。",
)
async def get_schema():
    """获取完整数据库 Schema

    返回:
    - node_tables: 节点表列表，每个表含 name(表名) 和 properties(属性列表，每项含 name 和 type)
    - rel_tables: 边表列表，每个表含 name(表名)、src(起点表名)、dst(终点表名) 和 properties(属性列表)

    示例:
    ```json
    {
      "node_tables": [
        {"name": "Account", "properties": [{"name": "id", "type": "INT64"}, {"name": "name", "type": "STRING"}]}
      ],
      "rel_tables": [
        {"name": "AccountCreatesPost", "src": "Account", "dst": "PostItem", "properties": [{"name": "since", "type": "INT64"}]}
      ]
    }
    ```
    """
    db = get_db()
    node_tables = []
    for t in db.get_node_tables():
        result = db.execute(f"CALL table_info('{t['name']}') RETURN *")
        props = []
        while result.has_next():
            row = result.get_next()
            props.append({"name": row[1], "type": row[2]})
        node_tables.append(SchemaNodeTable(name=t["name"], properties=props))

    rel_tables = []
    for t in db.get_rel_tables():
        result = db.execute(f"CALL table_info('{t['name']}') RETURN *")
        props = []
        while result.has_next():
            row = result.get_next()
            props.append({"name": row[1], "type": row[2]})
        conn_info = db.execute(f"CALL show_connection('{t['name']}') RETURN *")
        src = dst = ""
        while conn_info.has_next():
            row = conn_info.get_next()
            src = row[0]
            dst = row[1]
        rel_tables.append(SchemaRelTable(name=t["name"], src=src, dst=dst, properties=props))

    return SchemaResponse(node_tables=node_tables, rel_tables=rel_tables)


@router.get(
    "/schema/nodes",
    summary="获取节点表列表",
    description="返回数据库中所有节点表的名称列表（不含属性详情）。"
                "用于快速浏览有哪些节点表，如需属性详情请使用 /schema 接口。",
)
async def get_node_tables():
    """获取节点表列表

    返回:
    - name: 表名
    - type: 固定为 "NODE"
    """
    db = get_db()
    return db.get_node_tables()


@router.get(
    "/schema/edges",
    summary="获取边表列表",
    description="返回数据库中所有边表的名称列表（不含属性详情和连接关系）。"
                "如需完整的起点/终点/属性信息，请使用 /schema 接口。",
)
async def get_rel_tables():
    """获取边表列表

    返回:
    - name: 表名
    - type: 固定为 "REL"
    """
    db = get_db()
    return db.get_rel_tables()

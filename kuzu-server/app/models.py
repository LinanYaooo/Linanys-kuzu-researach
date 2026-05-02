from pydantic import BaseModel, Field
from typing import Any, Optional


class QueryRequest(BaseModel):
    """Cypher 查询请求体"""
    query: str = Field(
        ...,
        description="Cypher 查询语句",
        examples=["MATCH (n:Account) RETURN n.id, n.name LIMIT 10"],
    )
    parameters: Optional[dict[str, Any]] = Field(
        None,
        description="查询参数（预留，当前未使用）",
    )


class QueryResponse(BaseModel):
    """Cypher 查询响应（扁平行数据格式）"""
    results: list[dict[str, Any]] = Field(
        description="查询结果行列表，每行为 {列名: 值} 字典",
    )
    count: int = Field(
        description="结果行数",
    )
    elapsed_ms: float = Field(
        description="服务端执行耗时（毫秒）",
    )


class GraphNode(BaseModel):
    """图谱节点"""
    id: str = Field(description="节点唯一标识（table_offset 格式）")
    label: str = Field(description="节点显示名称，取自 name 或 id 属性")
    group: str = Field(description="节点所属表名，用于按类型着色")
    properties: dict[str, Any] = Field(description="节点全部属性（不含 _id, _label）")


class GraphEdge(BaseModel):
    """图谱边"""
    from_: str = Field(
        description="起点节点标识",
        alias="from",
    )
    to: str = Field(description="终点节点标识")
    label: str = Field(description="边的关系类型名称")
    properties: dict[str, Any] = Field(description="边全部属性（不含 _id, _label, _src, _dst）")

    model_config = {"populate_by_name": True}


class GraphQueryResponse(BaseModel):
    """图谱可视化查询响应（节点+边分离格式）"""
    nodes: list[GraphNode] = Field(description="去重后的节点列表")
    edges: list[GraphEdge] = Field(description="边列表")
    node_count: int = Field(description="节点数量")
    edge_count: int = Field(description="边数量")
    elapsed_ms: float = Field(description="服务端执行耗时（毫秒）")


class HistoryItem(BaseModel):
    """查询历史记录"""
    id: str = Field(description="历史记录唯一标识")
    query: str = Field(description="执行的 Cypher 语句")
    timestamp: float = Field(description="执行时间（Unix 时间戳）")
    result_count: int = Field(description="结果行数")
    elapsed_ms: float = Field(description="执行耗时（毫秒）")


class SchemaNodeTable(BaseModel):
    """节点表定义"""
    name: str = Field(description="节点表名称")
    properties: list[dict[str, str]] = Field(
        description="属性列表，每项含 name(属性名) 和 type(数据类型)",
    )


class SchemaRelTable(BaseModel):
    """边表定义"""
    name: str = Field(description="边表名称")
    src: str = Field(description="起点表名")
    dst: str = Field(description="终点表名")
    properties: list[dict[str, str]] = Field(
        description="属性列表，每项含 name(属性名) 和 type(数据类型)",
    )


class SchemaResponse(BaseModel):
    """完整数据库 Schema"""
    node_tables: list[SchemaNodeTable] = Field(description="节点表列表")
    rel_tables: list[SchemaRelTable] = Field(description="边表列表")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(description="连接状态，ok 表示正常")
    db_path: str = Field(description="数据库文件路径")
    node_count: int = Field(description="节点总数")
    edge_count: int = Field(description="边总数")

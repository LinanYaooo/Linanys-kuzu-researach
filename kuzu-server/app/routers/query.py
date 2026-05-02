import time
import uuid
from collections import deque

from fastapi import APIRouter, HTTPException

from app.db import get_db
from app.models import (
    QueryRequest,
    QueryResponse,
    GraphQueryResponse,
    HistoryItem,
)

router = APIRouter()

# 内存中的查询历史队列，最多保留 100 条
_history: deque[HistoryItem] = deque(maxlen=100)


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="执行 Cypher 查询",
    description="执行 Cypher 查询语句，返回扁平行数据。"
                "支持 MATCH（查询）、CREATE（创建节点/边）、DROP TABLE（删除表）等所有 Cypher 语句。"
                "DDL 语句返回确认信息行，DML/DQL 返回查询结果。"
                "注意：此接口无锁并发，适合读多写少场景；写操作建议使用 /query/safe。",
    responses={400: {"description": "查询语法错误或执行失败"}},
)
async def execute_query(req: QueryRequest):
    """执行 Cypher 查询（并发模式）

    请求体:
    - query: Cypher 查询语句，如 "MATCH (n:Account) RETURN n.id, n.name LIMIT 10"
    - parameters: 可选的查询参数（预留，当前未使用）

    返回:
    - results: 查询结果行列表，每行为 {列名: 值} 字典
    - count: 结果行数
    - elapsed_ms: 服务端执行耗时（毫秒）
    """
    db = get_db()
    start = time.perf_counter()
    try:
        result = db.execute(req.query)
        rows = db.result_to_dicts(result)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _add_history(req.query, len(rows), elapsed_ms)
        return QueryResponse(results=rows, count=len(rows), elapsed_ms=round(elapsed_ms, 2))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/query/safe",
    response_model=QueryResponse,
    summary="执行 Cypher 查询（线程安全）",
    description="加锁串行化执行 Cypher 查询，保证同一时刻只有一个查询在执行。"
                "适用于写操作（CREATE/DROP/DELETE 等）或需要强一致性的场景。"
                "返回格式与 /query 相同，但并发场景下吞吐量较低。",
    responses={400: {"description": "查询语法错误或执行失败"}},
)
async def execute_query_safe(req: QueryRequest):
    """执行 Cypher 查询（串行模式，线程安全）

    与 /query 功能相同，但通过 threading.Lock 串行化执行，
    避免并发写操作导致的数据竞争问题。
    """
    db = get_db()
    start = time.perf_counter()
    try:
        result = db.execute_safe(req.query)
        rows = db.result_to_dicts(result)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _add_history(req.query, len(rows), elapsed_ms)
        return QueryResponse(results=rows, count=len(rows), elapsed_ms=round(elapsed_ms, 2))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/query/graph",
    response_model=GraphQueryResponse,
    summary="执行图谱可视化查询",
    description="执行 Cypher 查询并将结果解析为节点+边分离格式，适配前端 vis-network 图谱可视化。"
                "仅适用于返回 NODE 和 REL 类型列的查询，如 "
                "'MATCH (a)-[e]->(b) RETURN a, e, b LIMIT 25'。"
                "不支持纯标量查询（如 RETURN count(n)）或 DDL 语句。",
    responses={400: {"description": "查询语法错误或结果不含 NODE/REL 列"}},
)
async def execute_graph_query(req: QueryRequest):
    """执行图谱可视化查询

    自动解析 Kuzu 返回的 NODE/REL 内部结构（_id, _label, _src, _dst），
    将节点按 table_offset 去重，边按 _src → _dst 关联，
    输出可直接用于 vis-network 渲染的格式。

    请求体:
    - query: 返回节点和边的 Cypher 查询，如 "MATCH (a:Account)-[e]->(b) RETURN a,e,b LIMIT 25"

    返回:
    - nodes: 节点列表，每个节点含 id(内部键), label(显示名), group(表名), properties(属性字典)
    - edges: 边列表，每条边含 from_(起点键), to(终点键), label(关系名), properties(属性字典)
    - node_count: 节点数
    - edge_count: 边数
    - elapsed_ms: 服务端执行耗时
    """
    db = get_db()
    start = time.perf_counter()
    try:
        result = db.execute(req.query)
        graph_data = db.result_to_graph(result)
        elapsed_ms = (time.perf_counter() - start) * 1000
        node_count = len(graph_data["nodes"])
        edge_count = len(graph_data["edges"])
        _add_history(req.query, node_count + edge_count, elapsed_ms)
        return GraphQueryResponse(
            nodes=graph_data["nodes"],
            edges=graph_data["edges"],
            node_count=node_count,
            edge_count=edge_count,
            elapsed_ms=round(elapsed_ms, 2),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/query/history",
    response_model=list[HistoryItem],
    summary="获取查询历史",
    description="返回服务端内存中保存的最近 100 条查询历史记录，按执行时间倒序排列。"
                "注意：服务器重启后历史记录会清空。前端同时使用 localStorage 做本地持久化。",
)
async def get_history():
    """获取查询历史列表

    返回:
    - id: 历史记录唯一标识
    - query: 执行的 Cypher 语句
    - timestamp: 执行时间（Unix 时间戳）
    - result_count: 结果行数
    - elapsed_ms: 执行耗时（毫秒）
    """
    return list(_history)


@router.delete(
    "/query/history",
    summary="清空查询历史",
    description="清空服务端内存中的全部查询历史记录，不可恢复。",
)
async def clear_history():
    """清空查询历史"""
    _history.clear()
    return {"status": "ok"}


def _add_history(query: str, result_count: int, elapsed_ms: float):
    """添加一条查询历史记录到内存队列"""
    _history.append(HistoryItem(
        id=str(uuid.uuid4())[:8],
        query=query,
        timestamp=time.time(),
        result_count=result_count,
        elapsed_ms=round(elapsed_ms, 2),
    ))
